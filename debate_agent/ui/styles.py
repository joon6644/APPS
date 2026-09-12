"""Streamlit 커스텀 CSS.

Streamlit 기본 위젯을 raw HTML 로 감쌀 수는 없으므로,
각 카드는 '하나의 완결된 HTML 블록'으로 렌더링하고 레이아웃만 st.columns 에 맡긴다.
"""

from __future__ import annotations

import config

CSS = """
<style>
:root {
    --ink:        #0f172a;
    --ink-soft:   #475569;
    --ink-faint:  #94a3b8;
    --line:       #e2e8f0;
    --surface:    #ffffff;
    --canvas:     #f8fafc;
    --pro:        __PRO_COLOR__;
    --con:        __CON_COLOR__;
    --good:       #15803d;
    --warn:       #b45309;
    --bad:        #b91c1c;
    --radius:     14px;
}

/* ── 기본 레이아웃 ─────────────────────────────────────────── */
#MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }

.stApp { background: var(--canvas); }

.block-container {
    max-width: 1120px;
    padding-top: 2.2rem;
    padding-bottom: 4rem;
}

/* 좁은 화면에서 PRO/CON 컬럼이 세로로 쌓이도록 */
@media (max-width: 860px) {
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    [data-testid="stColumn"] { min-width: 100% !important; }
}

/* ── 히어로 ────────────────────────────────────────────────── */
.hero { text-align: center; padding: 1.4rem 0 2.2rem; }
.hero h1 {
    font-size: 2.6rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    margin: 0 0 .55rem;
    color: var(--ink);
}
.hero .quote {
    font-size: 1.05rem;
    color: var(--ink-soft);
    margin: 0 0 .35rem;
}
.hero .sub { font-size: .9rem; color: var(--ink-faint); margin: 0; }

/* ── 카드 공통 ─────────────────────────────────────────────── */
.card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 1.3rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, .05);
}
.card h3 {
    font-size: .8rem;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--ink-faint);
    margin: 0 0 .8rem;
}
.card p { color: var(--ink); line-height: 1.75; margin: 0 0 .6rem; }
.card p:last-child { margin-bottom: 0; }

/* ── 최종 판정 카드 ────────────────────────────────────────── */
.verdict {
    background: linear-gradient(160deg, #ffffff 0%, #f1f5f9 100%);
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 2.1rem 1.5rem 1.8rem;
    text-align: center;
    margin-bottom: 1rem;
    box-shadow: 0 4px 20px rgba(15, 23, 42, .07);
}
.verdict .eyebrow {
    font-size: .72rem; font-weight: 700; letter-spacing: .22em;
    color: var(--ink-faint); text-transform: uppercase;
}
.verdict .result {
    font-size: 2.5rem; font-weight: 800; letter-spacing: -.02em;
    margin: .7rem 0 .55rem; line-height: 1.15;
}
/* 승자가 무엇을 주장했는지 한 줄로 */
.verdict .verdict-position {
    font-size: .93rem;
    font-weight: 600;
    color: var(--ink);
    max-width: 560px;
    margin: 0 auto .7rem;
    line-height: 1.6;
}
.verdict .headline {
    font-size: 1.02rem; color: var(--ink-soft);
    max-width: 640px; margin: 0 auto 1.2rem; line-height: 1.65;
}

/* ── 승리 격차 ─────────────────────────────────────────────── */
.margin-tag {
    display: inline-block;
    padding: .28rem .85rem;
    border-radius: 99px;
    color: #fff;
    font-size: .82rem;
    font-weight: 700;
    letter-spacing: .02em;
    margin-bottom: .9rem;
}
.margin-box {
    max-width: 470px;
    margin: 0 auto 1.3rem;
    padding: .95rem 1.1rem;
    background: rgba(255, 255, 255, .75);
    border: 1px solid var(--line);
    border-radius: 12px;
}
.margin-head {
    display: flex; justify-content: space-between; align-items: baseline;
    font-size: .95rem; margin-bottom: .45rem;
}
.margin-mid {
    font-size: .7rem; color: var(--ink-faint);
    letter-spacing: .12em; text-transform: uppercase;
}
.margin-track {
    position: relative;
    display: flex;
    height: 11px;
    border-radius: 99px;
    overflow: hidden;
    background: #e2e8f0;
}
.margin-fill { height: 100%; }
.margin-center {
    position: absolute; left: 50%; top: -2px; bottom: -2px;
    width: 2px; background: var(--ink); opacity: .45;
}
.margin-desc {
    font-size: .82rem; color: var(--ink-soft);
    margin-top: .6rem; line-height: 1.55;
}
.margin-reason {
    font-size: .84rem; color: var(--ink);
    margin-top: .45rem; line-height: 1.6;
    padding-top: .45rem; border-top: 1px dashed var(--line);
}

.divergence { border-left: 4px solid var(--warn); }

.score-total {
    display: flex; align-items: center; gap: .5rem;
    margin-top: .9rem; padding-top: .75rem;
    border-top: 1px solid var(--line);
}
.score-total-label {
    width: 110px; flex-shrink: 0;
    font-size: .84rem; font-weight: 700; color: var(--ink);
}

.conf { max-width: 330px; margin: 0 auto; }
.conf-label {
    display: flex; justify-content: space-between;
    font-size: .74rem; color: var(--ink-faint); margin-bottom: .32rem;
}
.conf-track {
    height: 7px; background: #e2e8f0;
    border-radius: 99px; overflow: hidden;
}
.conf-fill { height: 100%; background: var(--ink); border-radius: 99px; }

/* ── 배지 ──────────────────────────────────────────────────── */
.badge {
    display: inline-block;
    padding: .24rem .6rem;
    border-radius: 99px;
    font-size: .72rem;
    font-weight: 600;
    border: 1px solid var(--line);
    background: #f1f5f9;
    color: var(--ink-soft);
    margin: 0 .3rem .3rem 0;
}
.badge.type { background: #eef2ff; border-color: #c7d2fe; color: #4338ca; }
.badge.unverified { background: #fef3c7; border-color: #fde68a; color: #92400e; }
.badge.value { background: #f3e8ff; border-color: #e9d5ff; color: #6b21a8; }
.badge.fact  { background: #dcfce7; border-color: #bbf7d0; color: #166534; }

/* ── 진영 카드 ─────────────────────────────────────────────── */
.side {
    background: var(--surface);
    border: 1px solid var(--line);
    border-top: 4px solid var(--accent);
    border-radius: var(--radius);
    padding: 1.3rem 1.4rem;
    height: 100%;
    box-shadow: 0 1px 3px rgba(15, 23, 42, .05);
}
.side .side-name {
    font-size: 1.15rem; font-weight: 800; color: var(--accent);
    margin: 0 0 .15rem; letter-spacing: -.01em;
}
.side .side-role { font-size: .78rem; color: var(--ink-faint); margin: 0 0 1rem; }
.side .thesis {
    font-size: 1.02rem; font-weight: 600; color: var(--ink);
    line-height: 1.6; margin: 0 0 1.2rem;
    padding-left: .8rem; border-left: 3px solid var(--accent);
}
.side h4 {
    font-size: .74rem; font-weight: 700; letter-spacing: .09em;
    text-transform: uppercase; color: var(--ink-faint);
    margin: 1.3rem 0 .6rem; padding-bottom: .3rem;
    border-bottom: 1px solid var(--line);
}
.side h4:first-of-type { margin-top: 0; }

.arg { margin-bottom: 1rem; }
.arg-claim {
    font-weight: 650; color: var(--ink); line-height: 1.55;
    margin-bottom: .35rem; font-size: .95rem;
}
.arg-claim .num {
    display: inline-block; min-width: 1.4rem;
    color: var(--accent); font-weight: 800;
}
.arg-body { font-size: .88rem; color: var(--ink-soft); line-height: 1.68; margin-left: 1.4rem; }
.arg-body .k { color: var(--ink-faint); font-weight: 600; }

ul.tight { margin: 0; padding-left: 1.15rem; }
ul.tight li { color: var(--ink-soft); line-height: 1.65; margin-bottom: .35rem; font-size: .9rem; }
ul.tight li::marker { color: var(--ink-faint); }
ul.tight li.good::marker { color: var(--good); }
ul.tight li.bad::marker  { color: var(--bad); }
.muted { color: var(--ink-faint); font-size: .88rem; font-style: italic; }

/* ── 검증 결과 ─────────────────────────────────────────────── */
.finding {
    border-left: 3px solid var(--warn);
    background: #fffbeb;
    padding: .6rem .8rem;
    border-radius: 0 8px 8px 0;
    margin-bottom: .6rem;
}
.finding.high { border-left-color: var(--bad); background: #fef2f2; }
.finding.low  { border-left-color: var(--ink-faint); background: #f8fafc; }
.finding .ftype {
    font-size: .7rem; font-weight: 700; letter-spacing: .05em;
    color: var(--warn); text-transform: uppercase;
}
.finding.high .ftype { color: var(--bad); }
.finding.low .ftype  { color: var(--ink-faint); }
.finding .ftarget { font-size: .9rem; font-weight: 600; color: var(--ink); margin: .2rem 0; line-height: 1.5; }
.finding .fexp { font-size: .86rem; color: var(--ink-soft); line-height: 1.6; }

/* ── 점수 비교 ─────────────────────────────────────────────── */
.score-row { display: flex; align-items: center; gap: .7rem; margin-bottom: .55rem; }
.score-name { width: 110px; flex-shrink: 0; font-size: .84rem; color: var(--ink-soft); }
.score-bars { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.score-line { display: flex; align-items: center; gap: .5rem; }
.score-tag {
    width: 78px; flex-shrink: 0;
    font-size: .74rem; font-weight: 700;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.score-track {
    flex: 1; height: 8px;
    background: #eef2f6; border-radius: 99px; overflow: hidden;
}
/* display:block 필수. span 은 기본이 inline 이라 width/height 가 무시되어 막대가 차오르지 않는다.
   부모(.score-track)가 flex 컨테이너가 아니므로 자동 블록화도 일어나지 않는다. */
.score-fill { display: block; height: 100%; border-radius: 99px; }
.score-val { width: 34px; text-align: right; font-size: .76rem; color: var(--ink-soft); font-variant-numeric: tabular-nums; }

.disclaimer {
    font-size: .78rem; color: var(--ink-faint);
    background: #f1f5f9; border-radius: 8px;
    padding: .55rem .75rem; margin-top: .9rem; line-height: 1.55;
}

/* ── 판정 근거 / 한계 ──────────────────────────────────────── */
.split { border-left: 4px solid var(--good); padding-left: 1rem; margin-bottom: 1.3rem; }
.split.limit { border-left-color: var(--warn); }
.split .split-title { font-size: .95rem; font-weight: 700; color: var(--ink); margin-bottom: .5rem; }

/* ── 진행 상황 ─────────────────────────────────────────────── */
.steps { padding: .3rem 0; }
.step { display: flex; align-items: center; gap: .7rem; padding: .42rem 0; font-size: .95rem; }
.step .mark { width: 1.3rem; text-align: center; font-size: 1rem; }
.step.done    { color: var(--good); }
.step.active  { color: var(--ink); font-weight: 600; }
.step.pending { color: var(--ink-faint); }
.step.failed  { color: var(--bad); }

/* ── 기준별 비교표 ─────────────────────────────────────────── */
.cmp { margin-bottom: .9rem; padding-bottom: .9rem; border-bottom: 1px solid var(--line); }
.cmp:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
.cmp-head { display: flex; align-items: baseline; gap: .8rem; flex-wrap: wrap; margin-bottom: .3rem; }
.cmp-name { font-weight: 650; color: var(--ink); font-size: .95rem; }
.cmp-note { font-size: .87rem; color: var(--ink-soft); line-height: 1.6; }

/* ── 버튼 ──────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 10px;
    border: 1px solid var(--line);
    font-weight: 600;
    transition: all .15s ease;
}
.stButton > button:hover { border-color: var(--ink-faint); color: var(--ink); }
.stButton > button[kind="primary"] {
    background: var(--ink); border-color: var(--ink); color: #fff;
}
.stButton > button[kind="primary"]:hover { background: #1e293b; border-color: #1e293b; }

div[data-testid="stTextArea"] textarea {
    border-radius: 12px;
    font-size: 1rem;
}
</style>
"""


def inject() -> str:
    """진영 색상을 주입한 CSS 문자열.

    CSS 에 `100%` 같은 리터럴이 많아 %-포매팅은 쓸 수 없다. 토큰 치환을 사용한다.
    """
    pro = config.SIDES[0].color if config.SIDES else "#2563eb"
    con = config.SIDES[1].color if len(config.SIDES) > 1 else "#ea580c"
    return CSS.replace("__PRO_COLOR__", pro).replace("__CON_COLOR__", con)
