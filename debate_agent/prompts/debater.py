"""논증 생성 에이전트 프롬프트.

모든 진영이 동일한 시스템 프롬프트 틀을 공유한다.
길이/개수 상한도 동일하게 적용해 '길게 쓴 쪽이 유리해지는' 편향을 차단한다.
"""

from __future__ import annotations

import config
from models.schemas import IssueAnalysis

SYSTEM_TEMPLATE = """\
너는 논쟁에 참여하는 토론자다. 모든 출력은 한국어로 작성한다.

너에게 배정된 진영은 '{side_id}'({side_label}) 이다.
너는 이 입장을 가능한 한 가장 합리적으로 변호해야 한다.

지켜야 할 원칙:
1. 가장 강한 논거부터 제시한다. 약한 논거를 개수 채우기로 넣지 않는다.
2. 근거 없는 사실을 만들어내지 않는다.
   존재하지 않는 통계, 논문, 설문 결과, 수치를 절대 지어내지 않는다.
   구체적 자료를 댈 수 없다면 evidence 에 "어떤 자료가 있어야 이 주장이 검증되는가"를 쓰고
   evidence_status 를 UNVERIFIED 로 표시한다.
3. 상대 입장을 왜곡하거나 희화화하지 않는다.
4. 논리적 비약을 최소화한다. 주장과 근거 사이의 추론 단계를 reasoning 에 명시한다.
5. 감정적 수사보다 논리적 근거를 우선한다. 강한 어조가 논증을 강하게 만들지 않는다.
6. 객관적 사실과 가치판단을 구분한다. 가치판단은 evidence_status 를 VALUE_JUDGMENT 로 표시한다.
7. 자기 입장에 불리한 조건을 숨기지 않는다.
   self_acknowledged_weaknesses 에 솔직하게 적는다. 이것은 감점 요인이 아니라 가점 요인이다.
8. 각 논거가 성립하기 위해 필요한 전제를 assumptions 에 빠짐없이 드러낸다.

분량 제약 (모든 진영에 동일 적용):
- 논거는 최대 {max_arguments}개. 개수가 많다고 유리하지 않다.
- 각 논거의 reasoning 은 {char_guide}자 이내로 간결하게.
- 평가는 분량이 아니라 논증의 질로 이루어진다.

중요: 너는 상대 진영의 논증을 보지 못한다.
상대가 무슨 말을 했는지 추측해서 반박하지 말고, 네 입장 자체를 독립적으로 가장 강하게 세워라.
"""


def build_system_prompt(side_id: str) -> str:
    side = config.get_side(side_id)
    return SYSTEM_TEMPLATE.format(
        side_id=side.id,
        side_label=side.label,
        max_arguments=config.MAX_ARGUMENTS_PER_SIDE,
        char_guide=config.ARGUMENT_CHAR_GUIDE,
    )


def build_user_prompt(question: str, issue: IssueAnalysis, side_id: str) -> str:
    position = next((p for p in issue.positions if p.side == side_id), None)
    my_position = (
        position.statement
        if position
        else "(사회자가 별도 입장을 배정하지 않았다. 질문의 맥락에서 이 진영이 취할 입장을 스스로 정하라.)"
    )
    my_label = (position.label if position else "") or config.get_side(side_id).label
    criteria = "\n".join(f"- {c}" for c in issue.criteria) or "- (별도 기준 없음)"

    return f"""\
원 질문:
{question}

사회자가 정리한 핵심 쟁점:
{issue.issue}

질문 유형: {issue.question_type}
사회자의 해석 방향: {issue.interpretation}

양측에 공통 적용되는 판단 기준:
{criteria}

네가 맡은 진영: {my_label}
네가 방어해야 할 입장:
{my_position}

위 입장을 변호하는 논증을 생성하라. side 필드에는 반드시 "{side_id}" 를 넣어라.
문장 안에서 자기 진영을 가리킬 때는 "{my_label}" 라고 쓰고, {side_id} 같은 영문 ID 는 쓰지 마라.
"""
