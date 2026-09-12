""".env 파일 탐색 및 로드.

이 프로젝트의 .env 는 프로젝트 루트(debate_agent/)가 아니라 상위 폴더(APPS/)에 있다.
두 위치를 순서대로 탐색하여 처음 발견한 파일을 로드한다.
API 키 값은 절대 로그에 남기지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SEARCH_PATHS = (
    PROJECT_ROOT / ".env",
    PROJECT_ROOT.parent / ".env",
)

_loaded: bool = False
_loaded_path: Path | None = None


def load_environment(force: bool = False) -> Path | None:
    """.env 를 한 번만 로드하고, 사용된 경로를 반환한다."""
    global _loaded, _loaded_path
    if _loaded and not force:
        return _loaded_path

    for candidate in _SEARCH_PATHS:
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            _loaded_path = candidate
            break

    _loaded = True
    return _loaded_path


def get_env_path() -> Path | None:
    """로드에 사용된 .env 경로 (없으면 None)."""
    return _loaded_path
