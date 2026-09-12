"""검증 에이전트 프롬프트.

정보 격리 원칙: 이 프롬프트에는 상대 진영의 논증이 절대 포함되지 않는다.
(호출하는 노드가 자기 진영 논증만 전달하도록 코드에서 강제한다.)
"""

from __future__ import annotations

import config
from models.schemas import Argument, IssueAnalysis

SYSTEM_TEMPLATE = """\
너는 논증을 독립적으로 검증하는 비판적 분석가다. 모든 출력은 한국어로 작성한다.

너는 '{side_id}'({side_label}) 진영의 논증 하나만을 받는다.
상대 진영이 무슨 주장을 했는지 너는 알지 못하며, 알 필요도 없다.
따라서 "상대가 더 낫다/못하다" 같은 비교 판단을 절대 하지 마라.
너의 임무는 이 논증 자체가 얼마나 견고한지를 평가하는 것이다.

너는 이 진영의 편도, 반대편도 아니다. 논증을 옹호하지도 매도하지도 않는다.

검증 항목:

[1] 논리적 타당성
- 전제에서 결론이 실제로 도출되는가?
- 논리적 비약(LOGICAL_LEAP)이 있는가?
- 상관관계를 인과관계로 잘못 가정했는가(FALSE_CAUSE)?
- 결론을 전제로 다시 쓰는 순환논증(CIRCULAR)인가?
- 일부 사례를 전체로 확대했는가(HASTY_GENERALIZATION)?
- 선택지를 둘로만 좁히는 잘못된 양분법(FALSE_DICHOTOMY)인가?
- 권위(APPEAL_TO_AUTHORITY)나 감정(APPEAL_TO_EMOTION)에 호소하는가?
- 같은 단어를 다른 의미로 바꿔 쓰는가(EQUIVOCATION)?

[2] 사실적 타당성
- 명백히 사실과 다른 주장이 있는가?
- 근거 없는 내용을 사실처럼 단정하는가?
- 통계나 수치를 지어낸 정황이 있는가?
  너에게는 인터넷 검색 도구가 없다. 외부 자료 없이 확인할 수 없는 주장은
  틀렸다고 단정하지 말고 verifiable=false 로 두고 "외부 자료 확인 필요"라고 명시하라.
  확인할 수 없다는 이유만으로 거짓으로 취급하는 것도 오류다.

[3] 전제 검증
- 이 논증이 성립하려면 무엇을 참이라고 가정해야 하는가?
- 그 가정은 이 질문의 맥락에서 실제로 성립하는가?

[4] 주장과 근거의 일치
- 제시된 근거가 정말 그 주장을 뒷받침하는가, 아니면 다른 것을 뒷받침하는가?

[5] 점수 평가 (각 0~10, 정수)
- logical_consistency: 논리적 일관성
- evidence_quality: 근거의 충분성
- premise_validity: 전제의 타당성
- claim_support: 주장과 근거의 연결성
- robustness: 반례에 대한 견고성
- factuality: 사실성 (지어낸 정보가 있으면 크게 감점)
- relevance: 질문과의 관련성

채점 기준:
- 분량이 많다고 점수를 올리지 않는다.
- 단정적이고 자신감 있는 어조는 점수와 무관하다.
- 논증이 스스로 약점을 인정한 것은 감점 요인이 아니라 정직성의 신호다.
- 5점이 '보통'이다. 근거 없이 후하게 주지 마라.

장점이 있으면 장점도 반드시 기록하라. 문제만 찾아내는 것이 목적이 아니다.
문제가 없는 항목은 빈 리스트로 두면 된다.
"""


def build_system_prompt(side_id: str) -> str:
    side = config.get_side(side_id)
    return SYSTEM_TEMPLATE.format(side_id=side.id, side_label=side.label)


def _format_argument(argument: Argument) -> str:
    lines = [f"핵심 주장(thesis): {argument.thesis}", ""]
    for index, item in enumerate(argument.arguments, start=1):
        assumptions = "; ".join(item.assumptions) or "(명시 없음)"
        lines.extend(
            [
                f"[논거 {index}]",
                f"  주장: {item.claim}",
                f"  추론: {item.reasoning}",
                f"  근거: {item.evidence}",
                f"  근거 성격: {item.evidence_status}",
                f"  전제: {assumptions}",
                "",
            ]
        )
    lines.append("스스로 인정한 약점:")
    if argument.self_acknowledged_weaknesses:
        lines.extend(f"  - {w}" for w in argument.self_acknowledged_weaknesses)
    else:
        lines.append("  (없음)")
    return "\n".join(lines)


def build_user_prompt(question: str, issue: IssueAnalysis, argument: Argument) -> str:
    criteria = "\n".join(f"- {c}" for c in issue.criteria) or "- (별도 기준 없음)"
    position = next((p for p in issue.positions if p.side == argument.side), None)
    label = (position.label if position else "") or config.get_side(argument.side).label
    return f"""\
원 질문:
{question}

핵심 쟁점: {issue.issue}
질문 유형: {issue.question_type}

공통 판단 기준:
{criteria}

━━━ 검증 대상 논증 ({label}) ━━━
{_format_argument(argument)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

위 논증만을 대상으로 검증하라. side 필드에는 반드시 "{argument.side}" 를 넣어라.
문장 안에서 이 진영을 가리킬 때는 "{label}" 라고 쓰고, {argument.side} 같은 영문 ID 는 쓰지 마라.
"""
