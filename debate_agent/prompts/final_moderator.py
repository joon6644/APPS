"""최종 판정 사회자 프롬프트.

편향 방지의 마지막 관문. 진영 제시 순서는 호출 노드에서 매번 셔플되므로,
이 프롬프트는 '먼저 나온 쪽'에 의미를 두지 않도록 명시한다.
"""

from __future__ import annotations

import config
from models.schemas import Argument, Critique, IssueAnalysis
from utils.text import resolve_labels

#: 질문 유형별 판정 지침.
#: 어떤 유형이든 승자는 반드시 나온다. 유형에 따라 달라지는 것은
#: '무엇을 기준으로 우열을 가리는가'와 '격차를 얼마나 크게 볼 수 있는가'이다.
VERDICT_GUIDANCE: dict[str, str] = {
    "OBJECTIVE": (
        "이 질문은 사실과 데이터로 우열이 결정될 수 있는 유형이다.\n"
        "사실적으로 더 정확하고, 근거가 주장을 더 잘 뒷받침하는 쪽이 승자다.\n"
        "한쪽이 사실 오류를 범했다면 격차를 크게(DECISIVE 이상) 잡아도 된다.\n"
        "양쪽 모두 근거를 충분히 대지 못했다면 그나마 덜 부실한 쪽을 고르고\n"
        "margin_level 을 NARROW 로 두어 근거 부족을 드러내라."
    ),
    "SUBJECTIVE": (
        "이 질문은 개인의 취향이 결과를 지배하는 유형이다.\n"
        "따라서 '어느 선택지가 옳은가'가 아니라\n"
        "'어느 쪽이 자기 입장을 더 논리적으로 방어했는가'를 기준으로 판정하라.\n"
        "취향의 옳고 그름을 판정하는 것이 아님을 reasoning_for_verdict 에 명시하라.\n"
        "더 유창하거나 단정적으로 말한 쪽이 아니라, 전제를 정직하게 드러내고\n"
        "논리적 결함이 적은 쪽이 승자다.\n"
        "이런 질문에서 격차는 대개 크지 않다. 한쪽에 명백한 논리적 결함이 없다면\n"
        "margin_level 은 NARROW 또는 CLEAR 를 사용하라.\n"
        "limitations 에는 '이 질문은 본래 취향의 문제이며 승패가 선호의 우열을\n"
        "뜻하지 않는다'는 점을 반드시 포함하라."
    ),
    "MIXED": (
        "이 질문은 객관적으로 측정 가능한 요소와 가치판단이 섞인 유형이다.\n"
        "어떤 조건에서 어느 쪽이 우세한지를 reasoning_for_verdict 에 조건부로 서술한 뒤,\n"
        "그 조건들을 종합해 전체적으로 더 견고한 논증을 편 쪽을 승자로 정하라.\n"
        "조건에 따라 갈리는 정도가 클수록 margin_level 을 낮게(NARROW/CLEAR) 잡고,\n"
        "그 사실을 limitations 에 명시하라."
    ),
    "NORMATIVE": (
        "이 질문은 무엇이 옳은가를 묻는 당위 질문이다.\n"
        "어느 가치 전제가 옳은지를 네가 결정해서는 안 된다.\n"
        "대신 각 진영이 어떤 가치 전제에 서 있는지 드러내고,\n"
        "그 전제 위에서 논증이 얼마나 일관되고 견고한지로 우열을 가려라.\n"
        "즉 '가치관의 승패'가 아니라 '논증 수행의 승패'를 판정하는 것이다.\n"
        "이 점을 reasoning_for_verdict 와 limitations 에 반드시 밝혀라.\n"
        "가치 전제 자체가 정면으로 대립한다면 격차는 NARROW 또는 CLEAR 가 적절하다."
    ),
}


SYSTEM = """\
너는 논쟁의 최종 판정을 내리는 사회자다. 모든 출력은 한국어로 작성한다.

너는 양측의 원 논증과, 각 논증에 대한 '독립적인 검증 결과'를 함께 받는다.
검증 결과는 각 진영의 논증만 따로 본 검증자가 작성한 것이다.

━━━ 반드시 지켜야 할 판정 원칙 ━━━

1. 표현력이 아니라 논증의 질을 평가한다.
   유창함, 단정적 어조, 수사적 완성도는 평가 대상이 아니다.

2. 길이는 평가 대상이 아니다.
   논거를 많이 나열한 쪽이 유리해서는 안 된다. 약한 논거 5개보다 강한 논거 2개가 낫다.

3. 근거 없는 자신감에 점수를 주지 않는다.
   "명백하다", "누구나 안다" 같은 표현은 근거가 아니다.

4. 양측에 완전히 동일한 기준을 적용한다.
   한쪽에 요구한 엄격함을 다른 쪽에도 그대로 요구하라.

5. 한 진영을 평가할 때 상대 진영의 주장을 근거로 삼지 않는다.
   "상대가 이렇게 말했으니 이쪽이 틀렸다"는 추론을 하지 마라.
   각 논증은 먼저 그 자체로 평가한 뒤, 마지막에 같은 기준으로 비교한다.

6. 진영이 제시된 순서는 아무 의미가 없다.
   순서는 매번 무작위로 섞인다. 먼저 나온 쪽을 기준점으로 삼지 마라.

7. 점수 합계로 승자를 정하지 않는다.
   검증 점수는 참고 지표일 뿐이다. 총점이 높아도 결정적 논리 결함이 있으면 질 수 있고,
   총점이 낮아도 핵심 쟁점에서 옳으면 이길 수 있다.
   판정 근거는 반드시 '내용'으로 설명하라.

8. 반드시 한 쪽을 승자로 선택한다. 무승부와 판단 유보는 허용되지 않는다.
   우열이 아무리 근소해도 조금이라도 나은 쪽을 골라야 한다.
   대신 불확실성을 숨기지 마라. 다음 세 곳으로 정직하게 표현한다.
     - margin_level / margin_score : 얼마나 근소한 승부였는지
     - confidence                  : 이 판정 자체에 대한 확신도
     - limitations                 : 이 판정이 놓치고 있는 것
   근소한 승부를 압승으로 부풀리는 것은 무승부를 내는 것보다 나쁜 오류다.

━━━ 승리의 격차를 정하는 기준 ━━━

margin_level 은 '승자가 얼마나 압도적이었는가'를 나타낸다.
표현력이나 분량이 아니라 다음 요소들의 차이로 판단하라.
  - 논리적 결함의 개수와 심각도
  - 근거가 주장을 뒷받침하는 정도
  - 전제가 질문의 맥락에서 성립하는 정도
  - 반례에 견디는 힘

  NARROW (51~57)       : 양측 논증의 질이 사실상 대등하다.
                         평가자가 달랐다면 반대 결론도 나올 수 있는 수준이다.
  CLEAR (58~68)        : 한쪽이 분명히 앞서지만, 패한 쪽에도 유효한 논거가 남아 있다.
  DECISIVE (69~82)     : 핵심 쟁점에서 승부가 갈렸다.
                         패한 쪽의 중심 논거가 무너진 경우다.
  OVERWHELMING (83~95) : 거의 모든 기준에서 앞섰다.
                         패한 쪽에 사실 오류나 치명적 논리 결함이 있을 때만 쓴다.

대부분의 논쟁은 NARROW 나 CLEAR 에 해당한다.
DECISIVE 이상을 선택했다면 margin_reason 에 '무엇이 결정적으로 무너졌는지'를
구체적으로 지목할 수 있어야 한다. 지목할 수 없다면 등급을 낮춰라.

━━━ 작성해야 할 내용 ━━━

side_analyses: 각 진영마다
  - core_logic: 어떤 논리로 주장했는지
  - strengths: 합리적이라고 인정되는 부분
  - weaknesses: 논리적 오류나 불충분한 근거
  양측 모두에 대해 강점과 약점을 균형 있게 적는다. 한쪽만 약점을 나열하지 마라.

comparison: 동일 기준으로 양측을 비교한 표.
  assessments 의 side 에는 반드시 주어진 진영 ID 만 사용한다. 다른 값을 만들지 마라.

reasoning_for_verdict: 어느 쪽이 왜 더 합리적인지 3~6문장.
  이 분석을 먼저 쓰고, 그 결론으로 verdict 를 정하라. 순서를 거꾸로 하지 마라.
  '어느 논거가 승부를 갈랐는지'를 구체적으로 지목하라.

margin_reason: 왜 그 정도 격차인지 1~3문장.
  패한 쪽이 정확히 어디서 밀렸는지를 지목하라.

limitations: 이 판단 자체의 한계.
  '이긴 쪽 논리에 여전히 남아 있는 문제'를 반드시 1개 이상 포함하라.
  격차가 근소했다면 그 사실도 함께 적어라.
  사용자가 이 판정을 무비판적으로 받아들이지 않도록 하는 것이 목적이다.

reframing_suggestions: 질문을 어떻게 구체화하면 결론이 달라질 수 있는지.

━━━ 표기 규칙 ━━━

PRO, CON 같은 영문 진영 ID 는 side 와 verdict 필드에만 사용한다.
문장 안에서 진영을 가리킬 때는 아래 '진영 표시 이름'에 주어진 한글 이름을 쓴다.
  올바른 예: "청년피자는 조리의 간편함을 근거로 들었다."
  잘못된 예: "PRO는 조리의 간편함을 근거로 들었다."

존재하지 않는 통계나 연구를 새로 만들어내지 마라.
"""


def _format_argument(side_id: str, label: str, argument: Argument | None) -> str:
    header = f"■ [{side_id}] {label} 의 논증"
    if argument is None:
        return f"{header}\n  (논증 생성에 실패했습니다. 이 진영은 평가할 수 없습니다.)"

    lines = [header, f"  핵심 주장: {argument.thesis}", ""]
    for index, item in enumerate(argument.arguments, start=1):
        lines.extend(
            [
                f"  [논거 {index}] {item.claim}",
                f"    추론: {item.reasoning}",
                f"    근거: {item.evidence}",
                f"    근거 성격: {item.evidence_status}",
                f"    전제: {'; '.join(item.assumptions) or '(명시 없음)'}",
            ]
        )
    lines.append("")
    lines.append(
        f"  스스로 인정한 약점: {'; '.join(argument.self_acknowledged_weaknesses) or '(없음)'}"
    )
    return "\n".join(lines)


def _format_critique(side_id: str, label: str, critique: Critique | None) -> str:
    header = f"■ [{side_id}] {label} 의 논증에 대한 독립 검증 결과"
    if critique is None:
        return f"{header}\n  (검증에 실패했습니다. 이 진영의 검증 결과는 참고할 수 없습니다.)"

    lines = [header]

    lines.append("  논리적 강점:")
    if critique.logical_strengths:
        lines.extend(f"    + {s}" for s in critique.logical_strengths)
    else:
        lines.append("    (없음)")

    lines.append("  발견된 논리적 문제:")
    if critique.logical_flaws:
        for flaw in critique.logical_flaws:
            lines.append(
                f"    - [{flaw.flaw_type}/{flaw.severity}] {flaw.target_claim}: {flaw.explanation}"
            )
    else:
        lines.append("    (없음)")

    lines.append("  사실성 지적:")
    if critique.factual_concerns:
        for concern in critique.factual_concerns:
            mark = "확인 가능" if concern.verifiable else "외부 자료 확인 필요"
            lines.append(f"    - ({mark}) {concern.claim}: {concern.concern}")
    else:
        lines.append("    (없음)")

    lines.append("  근거 없는 단정:")
    if critique.unsupported_claims:
        lines.extend(f"    - {c}" for c in critique.unsupported_claims)
    else:
        lines.append("    (없음)")

    lines.append("  전제 평가:")
    if critique.assumption_assessment:
        lines.extend(f"    - {a}" for a in critique.assumption_assessment)
    else:
        lines.append("    (없음)")

    scores = ", ".join(
        f"{label} {value}/10" for _, label, value in critique.scores.as_items()
    )
    lines.append(f"  검증 점수(참고용): {scores}")
    lines.append(f"  종합 평가: {critique.overall_assessment}")
    return "\n".join(lines)


def build_user_prompt(
    question: str,
    issue: IssueAnalysis,
    arguments: dict[str, Argument],
    critiques: dict[str, Critique],
    side_order: list[str],
) -> str:
    """side_order 는 호출 측에서 셔플된 순서로 전달된다."""
    guidance = VERDICT_GUIDANCE.get(issue.question_type, VERDICT_GUIDANCE["MIXED"])
    criteria = "\n".join(f"- {c}" for c in issue.criteria) or "- (별도 기준 없음)"
    labels = resolve_labels(issue)
    positions = "\n".join(
        f"- [{p.side}] {labels.get(p.side, p.side)}: {p.statement}"
        for p in issue.positions
        if p.side in config.SIDE_IDS
    )
    display_names = "\n".join(
        f"- {side_id} 는 문장에서 '{labels.get(side_id, side_id)}' 라고 부른다"
        for side_id in config.SIDE_IDS
    )
    valid_ids = ", ".join(config.SIDE_IDS)

    argument_blocks = "\n\n".join(
        _format_argument(side_id, labels.get(side_id, side_id), arguments.get(side_id))
        for side_id in side_order
    )
    critique_blocks = "\n\n".join(
        _format_critique(side_id, labels.get(side_id, side_id), critiques.get(side_id))
        for side_id in side_order
    )

    return f"""\
원 질문:
{question}

━━━ 사회자의 초기 쟁점 분석 ━━━
핵심 쟁점: {issue.issue}
질문 유형: {issue.question_type} ({issue.question_type_reason})
해석 방향: {issue.interpretation}

배정된 입장:
{positions}

진영 표시 이름 (문장 안에서는 이 이름을 쓸 것):
{display_names}

공통 판단 기준:
{criteria}

━━━ 질문 유형별 판정 지침 ━━━
{guidance}

━━━ 양측 논증 (제시 순서는 무작위) ━━━
{argument_blocks}

━━━ 독립 검증 결과 ━━━
{critique_blocks}

━━━━━━━━━━━━━━━━━━━━━━━━

위 정보를 종합하여 최종 판정을 내려라.
- 먼저 reasoning_for_verdict 를 쓰고, 그 결론으로 verdict 를 정하라.
- verdict 에 쓸 수 있는 값은 {valid_ids} 뿐이다. 반드시 한 쪽을 고르라.
  무승부, 판단 유보, 공동 우세 같은 결론은 허용되지 않는다.
- 우열이 근소하다면 그것은 margin_level 을 NARROW 로 두라는 뜻이지,
  승자를 정하지 말라는 뜻이 아니다.
- side_analyses 와 comparison 의 side 필드에는 {valid_ids} 만 사용하라.
- question_type 은 "{issue.question_type}" 로 확인하되, 초기 분류가 명백히 틀렸다고
  판단되면 수정해도 된다.
"""
