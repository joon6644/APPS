"""에이전트 구조화 출력 스키마.

OpenAI json_schema(strict) 제약을 지킨다:
  - minimum/maximum 등 수치 제약 키워드 금지 -> 점수는 제약 없는 int 로 받고 파이썬에서 clamp
  - 자유 키 dict 금지 -> 리스트로 평탄화 (예: positions: list[PositionSpec])
  - 필드 default 금지 -> 모든 필드를 required 로 두고 빈 값 허용
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# 공통 리터럴
# --------------------------------------------------------------------------

QuestionType = Literal["OBJECTIVE", "SUBJECTIVE", "MIXED", "NORMATIVE"]

EvidenceStatus = Literal[
    "VERIFIABLE_FACT",  # 외부 자료로 검증 가능한 사실 주장
    "COMMON_KNOWLEDGE",  # 널리 통용되는 상식/경험칙
    "VALUE_JUDGMENT",  # 가치판단 (참/거짓 대상 아님)
    "UNVERIFIED",  # 근거를 댈 수 없는 미검증 주장
]

Severity = Literal["LOW", "MEDIUM", "HIGH"]

FlawType = Literal[
    "LOGICAL_LEAP",  # 논리적 비약
    "FALSE_CAUSE",  # 잘못된 인과 가정
    "CIRCULAR",  # 순환논증
    "HASTY_GENERALIZATION",  # 성급한 일반화
    "FALSE_DICHOTOMY",  # 잘못된 양분법
    "APPEAL_TO_AUTHORITY",  # 권위에 호소
    "APPEAL_TO_EMOTION",  # 감정에 호소
    "EQUIVOCATION",  # 개념 혼용
    "IRRELEVANT",  # 질문과 무관
    "UNSUPPORTED_PREMISE",  # 뒷받침되지 않은 전제
    "OTHER",
]

#: 최종 판정은 반드시 한 진영을 선택한다. 무승부/판단유보는 허용하지 않는다.
#: 불확실성은 verdict 가 아니라 margin_level / confidence / limitations 로 표현한다.
Verdict = Literal["PRO", "CON"]

#: 승리의 격차. "얼마나 압도적으로 이겼는가"
MarginLevel = Literal["NARROW", "CLEAR", "DECISIVE", "OVERWHELMING"]


FLAW_TYPE_LABELS: dict[str, str] = {
    "LOGICAL_LEAP": "논리적 비약",
    "FALSE_CAUSE": "잘못된 인과 가정",
    "CIRCULAR": "순환논증",
    "HASTY_GENERALIZATION": "성급한 일반화",
    "FALSE_DICHOTOMY": "잘못된 양분법",
    "APPEAL_TO_AUTHORITY": "권위에 호소",
    "APPEAL_TO_EMOTION": "감정에 호소",
    "EQUIVOCATION": "개념 혼용",
    "IRRELEVANT": "질문과 무관",
    "UNSUPPORTED_PREMISE": "뒷받침되지 않은 전제",
    "OTHER": "기타",
}

EVIDENCE_STATUS_LABELS: dict[str, str] = {
    "VERIFIABLE_FACT": "검증 가능 사실",
    "COMMON_KNOWLEDGE": "일반 상식",
    "VALUE_JUDGMENT": "가치판단",
    "UNVERIFIED": "미검증",
}

QUESTION_TYPE_LABELS: dict[str, str] = {
    "OBJECTIVE": "객관적 사실 판단",
    "SUBJECTIVE": "주관적 선호 판단",
    "MIXED": "객관적 요소 + 가치판단",
    "NORMATIVE": "규범적 가치판단",
}

MARGIN_LABELS: dict[str, str] = {
    "NARROW": "신승",
    "CLEAR": "우세승",
    "DECISIVE": "완승",
    "OVERWHELMING": "압승",
}

#: margin_level 별 margin_score 허용 구간. LLM 이 등급과 수치를 어긋나게 내는 경우를 보정한다.
MARGIN_BANDS: dict[str, tuple[int, int]] = {
    "NARROW": (51, 57),
    "CLEAR": (58, 68),
    "DECISIVE": (69, 82),
    "OVERWHELMING": (83, 95),
}

MARGIN_DESCRIPTIONS: dict[str, str] = {
    "NARROW": "근소한 차이로 갈렸습니다. 반대 결론도 충분히 가능합니다.",
    "CLEAR": "분명한 차이가 있었지만 패한 쪽에도 유효한 논거가 있었습니다.",
    "DECISIVE": "핵심 쟁점에서 승부가 갈렸습니다.",
    "OVERWHELMING": "논증의 질에서 거의 모든 기준에 걸쳐 앞섰습니다.",
}

SCORE_FIELD_LABELS: dict[str, str] = {
    "logical_consistency": "논리적 일관성",
    "evidence_quality": "근거의 충분성",
    "premise_validity": "전제의 타당성",
    "claim_support": "주장-근거 연결",
    "robustness": "반례 견고성",
    "factuality": "사실성",
    "relevance": "질문 관련성",
}


# --------------------------------------------------------------------------
# 1단계: 사회자의 쟁점 분석
# --------------------------------------------------------------------------


class PositionSpec(BaseModel):
    """진영별로 배정된 입장. (strict 모드 제약으로 dict 대신 리스트 원소로 표현)"""

    side: str = Field(description="진영 ID. 예: PRO, CON")
    label: str = Field(
        description=(
            "이 진영을 화면에 표시할 짧은 이름. 12자 이내. "
            "'A와 B 중 뭐가 나은가' 형태의 선택지 비교 질문이면 그 선택지의 이름을 쓴다 "
            "(예: '청년피자', '처갓집 치킨'). "
            "'~해야 하는가' 형태의 찬반 질문이면 '찬성', '반대' 를 쓴다. "
            "양쪽 라벨은 서로 확실히 구분되어야 한다."
        )
    )
    statement: str = Field(description="이 진영이 방어해야 할 입장을 한 문장으로 서술")


class IssueAnalysis(BaseModel):
    """사용자 질문에 대한 논쟁 구조 정의."""

    issue: str = Field(description="이 논쟁의 핵심 쟁점을 한 문장으로 정리")
    question_type: QuestionType = Field(
        description=(
            "질문 유형. OBJECTIVE=사실로 우열이 정해짐, SUBJECTIVE=개인 취향이 지배적, "
            "MIXED=객관적 요소와 가치판단이 섞임, NORMATIVE=당위/가치에 대한 물음"
        )
    )
    question_type_reason: str = Field(description="그 유형으로 분류한 이유")
    positions: list[PositionSpec] = Field(description="각 진영에 배정된 입장 목록")
    criteria: list[str] = Field(description="양측을 동일하게 평가할 판단 기준 3~5개")
    ambiguities: list[str] = Field(
        description="질문에 내재된 모호성. 없으면 빈 리스트"
    )
    interpretation: str = Field(
        description="모호성을 어떤 방향으로 해석하고 논쟁을 진행할지에 대한 결정"
    )


# --------------------------------------------------------------------------
# 2단계: 진영별 논증
# --------------------------------------------------------------------------


class ArgumentItem(BaseModel):
    """하나의 논거."""

    claim: str = Field(description="주장 한 문장")
    reasoning: str = Field(description="그 주장이 왜 성립하는지에 대한 추론 과정")
    evidence: str = Field(
        description=(
            "근거. 지어낸 통계/논문/수치를 절대 쓰지 말 것. "
            "제시할 구체적 자료가 없으면 어떤 종류의 근거가 필요한지를 서술한다."
        )
    )
    evidence_status: EvidenceStatus = Field(
        description="이 근거의 성격. 확인 불가능한 수치를 댔다면 반드시 UNVERIFIED"
    )
    assumptions: list[str] = Field(description="이 논거가 성립하기 위해 필요한 전제")


class Argument(BaseModel):
    """한 진영의 전체 논증."""

    side: str = Field(description="진영 ID")
    thesis: str = Field(description="이 진영의 핵심 주장을 한 문장으로")
    arguments: list[ArgumentItem] = Field(description="논거 목록")
    self_acknowledged_weaknesses: list[str] = Field(
        description="스스로 인정하는 자기 입장의 약점이나 성립하지 않는 조건"
    )


# --------------------------------------------------------------------------
# 3단계: 진영별 독립 검증
# --------------------------------------------------------------------------


class Finding(BaseModel):
    """검증에서 발견된 문제 하나."""

    flaw_type: FlawType = Field(description="문제 유형")
    target_claim: str = Field(description="문제가 발견된 주장(원문 인용 또는 요약)")
    explanation: str = Field(description="왜 문제인지에 대한 설명")
    severity: Severity = Field(description="이 문제가 논증 전체에 미치는 영향의 크기")


class FactualConcern(BaseModel):
    """사실성 관련 지적."""

    claim: str = Field(description="문제가 되는 사실 주장")
    concern: str = Field(description="어떤 점이 문제인지")
    verifiable: bool = Field(
        description=(
            "외부 자료 없이 판단 가능한가. 판단 불가능하면 false 로 두고 "
            "concern 에 '외부 자료 확인 필요'라고 명시한다."
        )
    )


class ScoreCard(BaseModel):
    """0~10 점 내부 평가 지표. (범위 제약은 파이썬에서 clamp)"""

    logical_consistency: int = Field(description="논리적 일관성 0~10")
    evidence_quality: int = Field(description="근거의 충분성 0~10")
    premise_validity: int = Field(description="전제의 타당성 0~10")
    claim_support: int = Field(description="주장과 근거의 연결성 0~10")
    robustness: int = Field(description="반례에 대한 견고성 0~10")
    factuality: int = Field(description="사실성 0~10")
    relevance: int = Field(description="질문과의 관련성 0~10")

    def as_items(self) -> list[tuple[str, str, int]]:
        """(필드명, 한글 라벨, 점수) 목록."""
        return [
            (key, label, getattr(self, key))
            for key, label in SCORE_FIELD_LABELS.items()
        ]

    def total(self) -> int:
        """검증 점수 합계 (최대 70).

        참고용 지표일 뿐이며 승패를 결정하지 않는다.
        합계가 높은 쪽이 패할 수도 있으며, 그 경우 UI 가 그 사실을 명시한다.
        """
        return sum(getattr(self, key) for key in SCORE_FIELD_LABELS)


class Critique(BaseModel):
    """한 진영 논증에 대한 독립 검증 결과."""

    side: str = Field(description="검증 대상 진영 ID")
    logical_strengths: list[str] = Field(description="논리적으로 타당한 부분")
    logical_flaws: list[Finding] = Field(description="발견된 논리적 문제. 없으면 빈 리스트")
    factual_concerns: list[FactualConcern] = Field(description="사실성 관련 지적")
    unsupported_claims: list[str] = Field(description="근거 없이 단정한 주장")
    assumption_assessment: list[str] = Field(
        description="논증이 의존하는 전제와 그 전제의 타당성 평가"
    )
    scores: ScoreCard = Field(description="내부 평가 점수")
    overall_assessment: str = Field(description="이 논증 전체에 대한 종합 평가")


# --------------------------------------------------------------------------
# 4단계: 최종 판정
# --------------------------------------------------------------------------


class SideAnalysis(BaseModel):
    """최종 사회자가 정리한 진영별 분석."""

    side: str = Field(description="진영 ID")
    core_logic: str = Field(description="이 진영이 어떤 논리로 주장했는지")
    strengths: list[str] = Field(description="합리적이라고 인정되는 부분")
    weaknesses: list[str] = Field(description="논리적 오류나 불충분한 근거")


class ComparisonRow(BaseModel):
    """동일 기준에 대한 진영별 비교 한 줄."""

    criterion: str = Field(description="비교 기준 이름")
    assessments: list[SideAssessment] = Field(description="진영별 평가")
    note: str = Field(description="이 기준에서의 비교 설명")


class SideAssessment(BaseModel):
    side: str = Field(description="진영 ID")
    score: int = Field(description="이 기준에 대한 0~10 평가")
    comment: str = Field(description="짧은 평가 코멘트")


class FinalJudgment(BaseModel):
    """최종 판정 결과.

    필드 순서가 곧 생성 순서다. 결론(verdict)보다 근거(reasoning_for_verdict)를 먼저 쓰게 해서,
    사후 합리화가 아니라 추론의 결과로 승자가 나오도록 유도한다.
    """

    question_type: QuestionType = Field(description="사회자가 최종 확인한 질문 유형")
    reasoning_for_verdict: str = Field(
        description=(
            "어느 쪽이 왜 더 합리적인지에 대한 3~6문장 분석. "
            "결론을 정하기 전에 이 분석을 먼저 작성한다. "
            "어느 논거가 승부를 갈랐는지 구체적으로 지목할 것."
        )
    )
    verdict: Verdict = Field(
        description=(
            "위 분석의 결론으로서 더 합리적인 논증을 제시한 진영 ID. "
            "반드시 한 쪽을 선택해야 하며 무승부는 허용되지 않는다. "
            "우열이 근소하더라도 조금이라도 나은 쪽을 고르고, "
            "그 근소함은 verdict 가 아니라 margin_level 로 표현한다."
        )
    )
    margin_level: MarginLevel = Field(
        description=(
            "승리의 격차. "
            "NARROW=거의 대등해 반대 결론도 가능한 수준, "
            "CLEAR=분명히 앞서지만 패한 쪽에도 유효한 논거가 있음, "
            "DECISIVE=핵심 쟁점에서 확실히 갈림, "
            "OVERWHELMING=거의 모든 기준에서 압도. "
            "질문이 주관적이거나 양측 근거가 모두 빈약하면 NARROW 를 선택하라. "
            "OVERWHELMING 은 패한 쪽 논증에 치명적 결함이 있을 때만 사용한다."
        )
    )
    margin_score: int = Field(
        description=(
            "승자가 가져간 우세를 0~100 정수로 표현. 50 은 완전 대등, 100 은 완전한 압도. "
            "NARROW 는 51~57, CLEAR 는 58~68, DECISIVE 는 69~82, OVERWHELMING 은 83~95 를 쓴다."
        )
    )
    margin_reason: str = Field(
        description="왜 이 정도 격차인지 1~3문장. 패한 쪽이 어디서 밀렸는지를 구체적으로 설명"
    )
    confidence: float = Field(description="이 판정 자체에 대한 확신도 0.0~1.0")
    headline: str = Field(description="판정을 한 문장으로 요약")
    side_analyses: list[SideAnalysis] = Field(description="진영별 분석")
    comparison: list[ComparisonRow] = Field(description="기준별 비교표")
    limitations: list[str] = Field(
        description=(
            "이 판단 자체의 한계. 승자가 있더라도 그 논리에 남아 있는 문제를 반드시 포함한다. "
            "격차가 NARROW 이거나 질문이 주관적이라면, "
            "원래 승패를 가리기 어려운 질문이었다는 점을 명시한다."
        )
    )
    reframing_suggestions: list[str] = Field(
        description="질문을 어떻게 구체화하면 결론이 달라질 수 있는지에 대한 제안"
    )


# 전방 참조 해소
ComparisonRow.model_rebuild()


# --------------------------------------------------------------------------
# 오류 기록
# --------------------------------------------------------------------------


class AgentError(BaseModel):
    """노드 실행 중 발생한 오류 (그래프는 계속 진행)."""

    node: str
    side: str
    message: str
