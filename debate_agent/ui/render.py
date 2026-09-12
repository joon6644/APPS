"""결과 렌더링 컴포넌트.

Streamlit 위젯을 raw HTML 로 감쌀 수 없으므로 각 카드는 완결된 HTML 블록으로 만들고,
레이아웃(컬럼/익스팬더)만 Streamlit 위젯에 맡긴다.
사용자에게 표시되는 모든 텍스트는 _t() 를 거친다 (진영 ID -> 표시 라벨 + HTML 이스케이프).

진영의 표시 라벨은 고정값이 아니라 사회자가 질문에 맞춰 붙인 이름이다.
("찬성/반대" 또는 "청년피자/처갓집 치킨") 진입점은 render_result() 하나이며,
여기서 라벨을 한 번 확정한 뒤 하위 렌더러들이 공유한다.
"""

from __future__ import annotations

from html import escape

import streamlit as st

import config
from models.schemas import (
    EVIDENCE_STATUS_LABELS,
    FLAW_TYPE_LABELS,
    MARGIN_DESCRIPTIONS,
    MARGIN_LABELS,
    QUESTION_TYPE_LABELS,
    Argument,
    Critique,
    FinalJudgment,
    IssueAnalysis,
    SideAnalysis,
)
from utils.text import default_labels, humanize_sides, resolve_labels

_EVIDENCE_BADGE_CLASS = {
    "VERIFIABLE_FACT": "fact",
    "COMMON_KNOWLEDGE": "",
    "VALUE_JUDGMENT": "value",
    "UNVERIFIED": "unverified",
}

#: 현재 렌더링 중인 논쟁의 진영 표시 라벨.
#: Streamlit 은 상호작용마다 스크립트를 처음부터 한 번씩 실행하므로(세션당 단일 스레드),
#: render_result() 진입 시 한 번 설정하면 그 실행 동안 일관되게 유지된다.
#: 40여 곳의 호출부에 라벨 인자를 끼워 넣는 대신 이 방식을 택했다.
_LABELS: dict[str, str] = default_labels()


def _label(side_id: str) -> str:
    """진영의 표시 라벨. (예: "찬성", "청년피자")"""
    return _LABELS.get(side_id, side_id)


def _side_name(side_id: str) -> str:
    """문장에 넣을 진영 이름.

    '찬성'/'반대' 같은 일반 라벨에는 '측'을 붙여 "찬성 측"으로,
    '청년피자' 같은 고유 라벨은 그대로 쓴다. ("청년피자 측"은 어색하다)
    """
    label = _label(side_id)
    generic = {side.label for side in config.SIDES}
    return f"{label} 측" if label in generic else label


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def _t(value: str) -> str:
    """LLM 이 생성한 텍스트를 화면용으로 변환한다.

    내부 진영 ID 를 표시 라벨로 바꾼 뒤 HTML 이스케이프한다.
    이 모듈의 모든 사용자 표시 텍스트는 이 함수를 거친다.
    """
    return escape(humanize_sides(value, _LABELS))


def _bullets(items: list[str], css_class: str = "") -> str:
    if not items:
        return '<p class="muted">해당 없음</p>'
    li = "".join(f'<li class="{css_class}">{_t(item)}</li>' for item in items)
    return f'<ul class="tight">{li}</ul>'


# ---------------------------------------------------------------------------
# 최종 판정 카드
# ---------------------------------------------------------------------------


def render_verdict(
    judgment: FinalJudgment,
    issue: IssueAnalysis | None,
    critiques: dict[str, Critique] | None = None,
) -> None:
    winner = config.SIDE_MAP.get(judgment.verdict)
    loser = next((s for s in config.SIDES if s.id != judgment.verdict), None)
    winner_name = _side_name(judgment.verdict) if winner else judgment.verdict
    winner_short = _label(judgment.verdict) if winner else judgment.verdict
    winner_color = winner.color if winner else "#0f172a"
    loser_short = _label(loser.id) if loser else ""
    loser_color = loser.color if loser else "#94a3b8"

    margin_label = MARGIN_LABELS.get(judgment.margin_level, judgment.margin_level)
    margin_desc = MARGIN_DESCRIPTIONS.get(judgment.margin_level, "")
    win = max(50, min(100, judgment.margin_score))
    lose = 100 - win

    confidence = max(0.0, min(1.0, judgment.confidence))
    question_type = judgment.question_type or (issue.question_type if issue else "MIXED")
    type_label = QUESTION_TYPE_LABELS.get(question_type, question_type)

    # 승자가 무엇을 주장했는지 판정 바로 아래에 보여준다.
    # 선택지 비교 질문("A vs B")에서 라벨만으로는 부족할 수 있기 때문이다.
    statement = next(
        (
            p.statement
            for p in (getattr(issue, "positions", None) or [])
            if p.side == judgment.verdict
        ),
        "",
    )
    statement_block = (
        f'<div class="verdict-position">{_t(statement)}</div>' if statement else ""
    )

    _html(
        f"""
<div class="verdict">
  <div class="eyebrow">Final Verdict</div>
  <div class="result" style="color:{winner_color}">{_t(winner_name)} 승리</div>
  <div class="margin-tag" style="background:{winner_color}">{_t(margin_label)}</div>
  {statement_block}
  <div class="headline">{_t(judgment.headline)}</div>

  <div class="margin-box">
    <div class="margin-head">
      <span style="color:{winner_color};font-weight:700">{_t(winner_short)} {win}</span>
      <span class="margin-mid">우세 격차</span>
      <span style="color:{loser_color};font-weight:700">{lose} {_t(loser_short)}</span>
    </div>
    <div class="margin-track">
      <div class="margin-fill" style="width:{win}%;background:{winner_color}"></div>
      <div class="margin-fill" style="width:{lose}%;background:{loser_color};opacity:.35"></div>
      <div class="margin-center"></div>
    </div>
    <div class="margin-desc">{_t(margin_desc)}</div>
    <div class="margin-reason">{_t(judgment.margin_reason)}</div>
  </div>

  <div><span class="badge type">{_t(question_type)} · {_t(type_label)}</span></div>
  <div class="conf">
    <div class="conf-label"><span>판정 신뢰도</span><span>{confidence:.0%}</span></div>
    <div class="conf-track"><div class="conf-fill" style="width:{confidence * 100:.0f}%"></div></div>
  </div>
</div>
"""
    )

    _render_score_divergence(judgment, critiques or {})


def _render_score_divergence(
    judgment: FinalJudgment, critiques: dict[str, Critique]
) -> None:
    """검증 점수 합계와 판정이 엇갈리면 그 사실을 숨기지 않고 알린다.

    이 시스템은 점수 합계로 승자를 정하지 않으므로 이런 역전이 일어날 수 있다.
    감추면 오히려 판정을 신뢰할 수 없게 되므로 명시적으로 드러낸다.
    """
    totals = {
        side.id: critiques[side.id].scores.total()
        for side in config.SIDES
        if side.id in critiques
    }
    if len(totals) < 2:
        return

    leader = max(totals, key=lambda sid: totals[sid])
    if leader == judgment.verdict or totals[leader] == totals.get(judgment.verdict):
        return

    detail = " / ".join(f"{_label(sid)} {total}점" for sid, total in totals.items())
    _html(
        f"""
<div class="card divergence">
  <h3>검증 점수와 판정이 엇갈렸습니다</h3>
  <p style="font-size:.92rem;margin-bottom:.5rem">
    검증 점수 합계는 <strong>{_t(_side_name(leader))}</strong>이 높지만
    (70점 만점 · {_t(detail)}),
    사회자는 <strong>{_t(_side_name(judgment.verdict))}</strong>을 승자로 판정했습니다.
  </p>
  <p style="font-size:.86rem;color:var(--ink-soft);margin:0">
    이 시스템은 점수 합계로 승자를 정하지 않습니다. 총점이 높아도 핵심 쟁점에서
    결정적 결함이 있으면 질 수 있습니다. 판정 근거는 아래 &lsquo;사회자의 최종 판단&rsquo;에 있습니다.
  </p>
</div>
"""
    )


def render_issue(issue: IssueAnalysis) -> None:
    criteria = "".join(f'<span class="badge">{_t(c)}</span>' for c in issue.criteria)
    ambiguity_block = ""
    if issue.ambiguities:
        ambiguity_block = (
            '<h3 style="margin-top:1.1rem">질문에 내재된 모호성</h3>'
            + _bullets(issue.ambiguities)
        )
    _html(
        f"""
<div class="card">
  <h3>사회자의 쟁점 분석</h3>
  <p><strong>{_t(issue.issue)}</strong></p>
  <p style="font-size:.9rem;color:var(--ink-soft)">{_t(issue.interpretation)}</p>
  <h3 style="margin-top:1.1rem">양측 공통 판단 기준</h3>
  <div>{criteria}</div>
  {ambiguity_block}
</div>
"""
    )


def render_reasoning(judgment: FinalJudgment) -> None:
    _html(
        f"""
<div class="card">
  <h3>판정 이유</h3>
  <p>{_t(judgment.reasoning_for_verdict)}</p>
</div>
"""
    )


# ---------------------------------------------------------------------------
# 진영 카드
# ---------------------------------------------------------------------------


def _argument_block(argument: Argument | None) -> str:
    if argument is None:
        return '<p class="muted">논증이 생성되지 않았습니다.</p>'

    parts = [f'<div class="thesis">{_t(argument.thesis)}</div>', "<h4>주요 논거</h4>"]
    if not argument.arguments:
        parts.append('<p class="muted">제시된 논거가 없습니다.</p>')
    for index, item in enumerate(argument.arguments, start=1):
        badge_class = _EVIDENCE_BADGE_CLASS.get(item.evidence_status, "")
        badge_label = EVIDENCE_STATUS_LABELS.get(item.evidence_status, item.evidence_status)
        assumptions = (
            f'<div><span class="k">전제</span> {_t("; ".join(item.assumptions))}</div>'
            if item.assumptions
            else ""
        )
        parts.append(
            f"""
<div class="arg">
  <div class="arg-claim"><span class="num">{index}.</span>{_t(item.claim)}
    <span class="badge {badge_class}">{_t(badge_label)}</span></div>
  <div class="arg-body">
    <div><span class="k">추론</span> {_t(item.reasoning)}</div>
    <div><span class="k">근거</span> {_t(item.evidence)}</div>
    {assumptions}
  </div>
</div>"""
        )

    parts.append("<h4>스스로 인정한 약점</h4>")
    parts.append(_bullets(argument.self_acknowledged_weaknesses))
    return "".join(parts)


def render_side_card(
    side_id: str,
    argument: Argument | None,
    analysis: SideAnalysis | None,
    position: str = "",
) -> None:
    side = config.SIDE_MAP[side_id]
    analysis_block = ""
    if analysis is not None:
        analysis_block = (
            "<h4>사회자가 본 강점</h4>"
            + _bullets(analysis.strengths, "good")
            + "<h4>사회자가 본 약점</h4>"
            + _bullets(analysis.weaknesses, "bad")
        )

    _html(
        f"""
<div class="side" style="--accent:{side.color}">
  <div class="side-name">{_t(_side_name(side_id))}</div>
  <div class="side-role">{_t(position)}</div>
  {_argument_block(argument)}
  {analysis_block}
</div>
"""
    )


# ---------------------------------------------------------------------------
# 검증 결과
# ---------------------------------------------------------------------------


def render_critique(side_id: str, critique: Critique | None) -> None:
    with st.expander(f"🔍 {_side_name(side_id)} 논증 검증 결과 보기", expanded=False):
        if critique is None:
            st.info("검증 결과가 생성되지 않았습니다.")
            return

        parts = [
            f'<div class="card" style="margin:0">',
            "<h3>종합 평가</h3>",
            f"<p>{_t(critique.overall_assessment)}</p>",
            "<h3 style='margin-top:1.2rem'>논리적 강점</h3>",
            _bullets(critique.logical_strengths, "good"),
            "<h3 style='margin-top:1.2rem'>발견된 논리적 문제</h3>",
        ]

        if critique.logical_flaws:
            for flaw in critique.logical_flaws:
                severity_class = flaw.severity.lower()
                label = FLAW_TYPE_LABELS.get(flaw.flaw_type, flaw.flaw_type)
                parts.append(
                    f"""
<div class="finding {severity_class}">
  <div class="ftype">⚠ {_t(label)} · 심각도 {_t(flaw.severity)}</div>
  <div class="ftarget">{_t(flaw.target_claim)}</div>
  <div class="fexp">{_t(flaw.explanation)}</div>
</div>"""
                )
        else:
            parts.append('<p class="muted">발견된 논리적 오류가 없습니다.</p>')

        parts.append("<h3 style='margin-top:1.2rem'>사실성 점검</h3>")
        if critique.factual_concerns:
            for concern in critique.factual_concerns:
                mark = "확인 가능" if concern.verifiable else "검증 불가 · 외부 자료 확인 필요"
                css = "low" if concern.verifiable else ""
                parts.append(
                    f"""
<div class="finding {css}">
  <div class="ftype">{_t(mark)}</div>
  <div class="ftarget">{_t(concern.claim)}</div>
  <div class="fexp">{_t(concern.concern)}</div>
</div>"""
                )
        else:
            parts.append('<p class="muted">지적된 사실성 문제가 없습니다.</p>')

        parts.append("<h3 style='margin-top:1.2rem'>근거 없이 단정한 주장</h3>")
        parts.append(_bullets(critique.unsupported_claims, "bad"))
        parts.append("<h3 style='margin-top:1.2rem'>전제 평가</h3>")
        parts.append(_bullets(critique.assumption_assessment))
        parts.append("</div>")

        _html("".join(parts))


# ---------------------------------------------------------------------------
# 점수 비교
# ---------------------------------------------------------------------------


def render_scores(critiques: dict[str, Critique]) -> None:
    available = {sid: c for sid, c in critiques.items() if c is not None}
    if not available:
        return

    rows = []
    field_labels = next(iter(available.values())).scores.as_items()
    for field, label, _ in field_labels:
        lines = []
        for side in config.SIDES:
            critique = available.get(side.id)
            if critique is None:
                continue
            value = getattr(critique.scores, field)
            lines.append(
                f"""
<div class="score-line">
  <span class="score-tag" style="color:{side.color}">{_t(_label(side.id))}</span>
  <span class="score-track"><span class="score-fill"
        style="width:{value * 10}%;background:{side.color}"></span></span>
  <span class="score-val">{value}/10</span>
</div>"""
            )
        rows.append(
            f"""
<div class="score-row">
  <div class="score-name">{_t(label)}</div>
  <div class="score-bars">{"".join(lines)}</div>
</div>"""
        )

    totals = "".join(
        f'<span class="badge" style="color:{side.color};border-color:{side.color}33">'
        f"{_t(_label(side.id))} {available[side.id].scores.total()} / 70</span>"
        for side in config.SIDES
        if side.id in available
    )

    _html(
        f"""
<div class="card">
  <h3>검증 점수 비교</h3>
  {"".join(rows)}
  <div class="score-total">
    <span class="score-total-label">합계</span>{totals}
  </div>
  <div class="disclaimer">
    이 점수는 각 진영의 논증을 <strong>독립적으로</strong> 검증한 AI 가 매긴 보조 지표입니다.
    객관적 측정값이 아니며, 최종 판정은 점수 합계가 아니라 논증의 내용으로 결정됩니다.
  </div>
</div>
"""
    )


def render_comparison(judgment: FinalJudgment) -> None:
    if not judgment.comparison:
        return

    rows = []
    for row in judgment.comparison:
        tags = "".join(
            f'<span class="badge" style="color:{config.SIDE_MAP[a.side].color};'
            f'border-color:{config.SIDE_MAP[a.side].color}33">'
            f"{_t(_label(a.side))} {a.score}/10</span>"
            for a in row.assessments
            if a.side in config.SIDE_MAP
        )
        rows.append(
            f"""
<div class="cmp">
  <div class="cmp-head"><span class="cmp-name">{_t(row.criterion)}</span>{tags}</div>
  <div class="cmp-note">{_t(row.note)}</div>
</div>"""
        )

    _html(f'<div class="card"><h3>기준별 비교</h3>{"".join(rows)}</div>')


# ---------------------------------------------------------------------------
# 사회자의 최종 판단
# ---------------------------------------------------------------------------


def render_final_analysis(judgment: FinalJudgment) -> None:
    limitations = _bullets(judgment.limitations)
    reframing = (
        "<h3 style='margin-top:1.4rem'>질문을 이렇게 바꾸면 결론이 달라질 수 있습니다</h3>"
        + _bullets(judgment.reframing_suggestions)
        if judgment.reframing_suggestions
        else ""
    )

    core_blocks = "".join(
        f"""
<div style="margin-bottom:1rem">
  <div style="font-weight:700;color:{config.SIDE_MAP[a.side].color};margin-bottom:.25rem">
    {_t(_side_name(a.side))}의 핵심 논리
  </div>
  <p style="font-size:.92rem;color:var(--ink-soft);margin:0">{_t(a.core_logic)}</p>
</div>"""
        for a in judgment.side_analyses
        if a.side in config.SIDE_MAP
    )

    _html(
        f"""
<div class="card">
  <h3>사회자의 최종 판단</h3>
  {core_blocks}
  <div class="split">
    <div class="split-title">✓ 왜 이 결론에 이르렀는가</div>
    <p style="font-size:.94rem;margin:0">{_t(judgment.reasoning_for_verdict)}</p>
  </div>
  <div class="split limit">
    <div class="split-title">⚠ 다만 이 판단에도 한계가 있습니다</div>
    {limitations}
  </div>
  {reframing}
</div>
"""
    )


def render_no_judgment() -> None:
    """판정 에이전트가 실패한 경우.

    승자를 임의로 만들어내지 않고, 판정이 없다는 사실을 분명히 알린다.
    """
    _html(
        """
<div class="verdict">
  <div class="eyebrow">Final Verdict</div>
  <div class="result" style="color:var(--ink-faint)">판정 실패</div>
  <div class="headline">
    최종 판정 에이전트가 응답하지 못했습니다.
    없는 근거로 승패를 만들어내지 않기 위해 판정을 비워 둡니다.
    아래의 양측 논증과 검증 결과는 정상이므로 직접 비교해 보실 수 있습니다.
  </div>
</div>
"""
    )


def render_errors(errors: list) -> None:
    if not errors:
        return

    def _where(error) -> str:
        side = config.SIDE_MAP.get(error.side)
        return _side_name(error.side) if side else "공통"

    lines = "\n".join(f"- **{_where(e)}** · {e.node}: {e.message}" for e in errors)
    st.warning(
        "일부 에이전트가 실패했지만 폴백으로 분석을 계속했습니다. "
        "아래 결과에는 누락된 부분이 있을 수 있습니다.\n\n" + lines
    )


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def render_result(state: dict) -> None:
    """분석 결과 전체를 그린다.

    이 함수가 진영 표시 라벨을 확정하므로, 결과 렌더링은 반드시 여기를 통해야 한다.
    """
    global _LABELS

    issue = state.get("issue")
    judgment = state.get("judgment")
    arguments = state.get("arguments", {})
    critiques = state.get("critiques", {})

    _LABELS = resolve_labels(issue)

    render_errors(state.get("errors", []))

    if judgment is not None:
        render_verdict(judgment, issue, critiques)
        render_reasoning(judgment)
    else:
        render_no_judgment()

    if issue is not None:
        render_issue(issue)

    _html(
        '<h3 style="font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;'
        'color:var(--ink-faint);margin:1.8rem 0 .8rem">양측 논증 비교</h3>'
    )

    analyses = {a.side: a for a in (judgment.side_analyses if judgment else [])}
    positions = {
        p.side: p.statement for p in (getattr(issue, "positions", None) or [])
    }

    columns = st.columns(len(config.SIDES), gap="medium")
    for column, side in zip(columns, config.SIDES):
        with column:
            render_side_card(
                side.id,
                arguments.get(side.id),
                analyses.get(side.id),
                positions.get(side.id, side.role_hint),
            )
            render_critique(side.id, critiques.get(side.id))

    _html("<div style='height:1.2rem'></div>")
    render_scores(critiques)

    if judgment is not None:
        render_comparison(judgment)
        render_final_analysis(judgment)
