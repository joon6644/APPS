# AI Debate Judge 실행 스크립트
#
# run.bat 이 이 파일을 호출합니다. 직접 실행해도 됩니다.
#   .\run.ps1                     웹앱 실행 (기본)
#   .\run.ps1 -Test               시스템 테스트 실행 (LLM 호출 없음)
#   .\run.ps1 -Ask "질문"         터미널에서 한 번만 분석
#
# 어느 모드든 가상환경 준비는 이 스크립트가 알아서 합니다.
#
# 한글 메시지는 여기에 둡니다. 배치 파일(.bat)은 cmd.exe 의 코드페이지 문제로
# 한글을 안정적으로 처리하지 못하기 때문입니다.

param(
    [switch]$Test,
    [string]$Ask
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path (Split-Path -Parent $root) ".venv"
$py = Join-Path $venv "Scripts\python.exe"

$Host.UI.RawUI.WindowTitle = "AI Debate Judge"

function Write-Step($text) { Write-Host "  $text" -ForegroundColor Cyan }
function Write-Fail($text) { Write-Host "  [오류] $text" -ForegroundColor Red }

Write-Host ""
Write-Host "  ==========================================" -ForegroundColor DarkGray
Write-Host "    AI Debate Judge" -ForegroundColor White
Write-Host "  ==========================================" -ForegroundColor DarkGray
Write-Host ""

# --- .env 확인 -------------------------------------------------------
$envHere = Join-Path $root ".env"
$envParent = Join-Path (Split-Path -Parent $root) ".env"

if (-not (Test-Path $envHere) -and -not (Test-Path $envParent)) {
    Write-Fail ".env 파일을 찾을 수 없습니다."
    Write-Host ""
    Write-Host "  아래 위치 중 한 곳에 .env 파일을 만들고" -ForegroundColor Yellow
    Write-Host "  OPENAI_API_KEY=sk-... 를 적어 주세요." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "    $envHere" -ForegroundColor DarkGray
    Write-Host "    $envParent" -ForegroundColor DarkGray
    Write-Host ""
    exit 1
}

# --- 가상환경 확인 및 최초 1회 설치 ----------------------------------
if (-not (Test-Path $py)) {
    Write-Step "처음 실행입니다. 실행 환경을 준비합니다..."
    Write-Host "  몇 분 정도 걸릴 수 있습니다." -ForegroundColor DarkGray
    Write-Host ""

    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $systemPython) {
        Write-Fail "Python 을 찾을 수 없습니다."
        Write-Host "  https://www.python.org 에서 Python 3.10 이상을 설치해 주세요." -ForegroundColor Yellow
        Write-Host '  설치할 때 "Add Python to PATH" 를 꼭 체크하세요.' -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }

    Write-Step "[1/2] 가상환경 생성 중..."
    & python -m venv $venv
    if (-not (Test-Path $py)) {
        Write-Fail "가상환경 생성에 실패했습니다."
        exit 1
    }

    Write-Step "[2/2] 필요한 패키지 설치 중..."
    & $py -m pip install --upgrade pip --quiet
    & $py -m pip install -r (Join-Path $root "requirements.txt") --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "패키지 설치에 실패했습니다. 인터넷 연결을 확인해 주세요."
        exit 1
    }

    Write-Host ""
    Write-Step "준비 완료!"
    Write-Host ""
}

$env:PYTHONIOENCODING = "utf-8"

# --- 테스트 모드 -----------------------------------------------------
if ($Test) {
    Write-Step "시스템 테스트를 실행합니다 (LLM 호출 없음)."
    Write-Host ""
    & $py (Join-Path $root "tests\test_system.py")
    exit $LASTEXITCODE
}

# --- CLI 분석 모드 ---------------------------------------------------
if ($Ask) {
    Write-Step "터미널에서 분석합니다."
    Write-Host "  질문: $Ask" -ForegroundColor White
    Write-Host ""
    & $py (Join-Path $root "run_debate.py") $Ask
    exit $LASTEXITCODE
}

# --- 이미 실행 중이면 브라우저만 열고 끝낸다 --------------------------
$url = "http://localhost:8501"
$alreadyRunning = $null -ne (
    Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
)

if ($alreadyRunning) {
    Write-Step "이미 실행 중입니다. 브라우저를 엽니다."
    Write-Host "  주소: " -NoNewline
    Write-Host $url -ForegroundColor Green
    Write-Host ""
    Start-Process $url
    exit 0
}

# --- 실행 ------------------------------------------------------------
Write-Host "  주소: " -NoNewline
Write-Host $url -ForegroundColor Green
Write-Host ""
Write-Host "  * 서버가 준비되면 브라우저가 자동으로 열립니다." -ForegroundColor DarkGray
Write-Host "  * 이 창은 서버 창입니다. 닫으면 웹앱도 함께 종료됩니다." -ForegroundColor DarkGray
Write-Host "  * 종료하려면 이 창에서 Ctrl+C 를 누르세요." -ForegroundColor DarkGray
Write-Host ""
Write-Host "  ------------------------------------------" -ForegroundColor DarkGray

# Streamlit 은 headless 로 띄운다(최초 실행 시 이메일 입력 프롬프트 방지).
# 대신 서버가 응답하기 시작하면 별도 작업이 브라우저를 연다.
$opener = Start-Job -ArgumentList $url -ScriptBlock {
    param($target)
    for ($i = 0; $i -lt 120; $i++) {
        try {
            Invoke-WebRequest -Uri $target -UseBasicParsing -TimeoutSec 2 | Out-Null
            Start-Process $target
            return
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
}

try {
    & $py -m streamlit run (Join-Path $root "app.py")
} finally {
    Stop-Job $opener -ErrorAction SilentlyContinue
    Remove-Job $opener -Force -ErrorAction SilentlyContinue
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Fail "실행 중 문제가 발생했습니다. 위 메시지를 확인해 주세요."
    exit 1
}
