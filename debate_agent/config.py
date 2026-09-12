"""프로젝트 전역 설정.

환경변수 기반으로 동작하며, 모델명·API 키는 코드에 하드코딩하지 않는다.
확장 지점: SIDES 리스트에 SideSpec 을 추가하면 그래프 노드가 자동으로 늘어난다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from utils.env import load_environment

load_environment()


# --------------------------------------------------------------------------
# LLM 설정
# --------------------------------------------------------------------------

DEFAULT_MODEL: Final[str] = "gpt-4o-mini"


def get_model_name() -> str:
    """논증/검증/판정에 사용할 모델명."""
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


def get_judge_model_name() -> str:
    """최종 판정 전용 모델. 미지정이면 기본 모델을 그대로 사용한다."""
    return os.getenv("OPENAI_JUDGE_MODEL", get_model_name())


def get_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_temperature() -> float:
    return float(os.getenv("OPENAI_TEMPERATURE", "0.4"))


#: structured output 파싱 실패 시 재시도 횟수
STRUCTURED_OUTPUT_RETRIES: Final[int] = int(os.getenv("STRUCTURED_OUTPUT_RETRIES", "2"))

#: OpenAI SDK 자체 재시도 (rate limit / 일시적 네트워크 오류 백오프)
API_MAX_RETRIES: Final[int] = int(os.getenv("OPENAI_MAX_RETRIES", "3"))


# --------------------------------------------------------------------------
# 논쟁 진영(side) 레지스트리 -- 확장 지점
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SideSpec:
    """하나의 논쟁 진영 정의."""

    id: str
    label: str
    color: str
    #: 사회자가 입장을 배정할 때 쓰는 역할 설명
    role_hint: str


SIDES: Final[tuple[SideSpec, ...]] = (
    SideSpec(
        id="PRO",
        label="찬성",
        color="#2563eb",
        role_hint="질문에 대해 긍정/첫 번째 선택지를 지지하는 입장",
    ),
    SideSpec(
        id="CON",
        label="반대",
        color="#ea580c",
        role_hint="질문에 대해 부정/두 번째 선택지를 지지하는 입장",
    ),
    # 확장 예시: NEUTRAL 진영을 넣으려면 아래 주석을 해제하기만 하면 된다.
    # SideSpec(
    #     id="NEUTRAL",
    #     label="중립",
    #     color="#0f766e",
    #     role_hint="양측 모두 결정적이지 않다는 제3의 입장",
    # ),
)

SIDE_IDS: Final[tuple[str, ...]] = tuple(s.id for s in SIDES)
SIDE_MAP: Final[dict[str, SideSpec]] = {s.id: s for s in SIDES}


def get_side(side_id: str) -> SideSpec:
    return SIDE_MAP[side_id]


# --------------------------------------------------------------------------
# 편향 방지 제약 (모든 진영에 동일 적용)
# --------------------------------------------------------------------------

#: 진영당 논거 개수 상한. 길이/개수로 유불리가 생기지 않도록 양측 동일하게 고정한다.
MAX_ARGUMENTS_PER_SIDE: Final[int] = 4

#: 각 논거 서술 길이 가이드(문자 수). 프롬프트에만 사용되는 소프트 리밋.
ARGUMENT_CHAR_GUIDE: Final[int] = 400


# --------------------------------------------------------------------------
# 입력 검증
# --------------------------------------------------------------------------

MIN_QUESTION_LENGTH: Final[int] = 2
MAX_QUESTION_LENGTH: Final[int] = 500

EXAMPLE_QUESTIONS: Final[tuple[str, ...]] = (
    "짜장면과 짬뽕 중 뭐가 더 맛있어?",
    "재택근무가 사무실 출근보다 생산적인가?",
    "대학교 등록금은 낮춰야 하는가?",
    "운동은 아침에 하는 게 좋은가, 밤에 하는 게 좋은가?",
    "전기차가 내연기관차보다 친환경적인가?",
)


def validate_question(question: str) -> str | None:
    """질문 문자열을 검증한다. 문제가 없으면 None, 있으면 오류 메시지를 반환."""
    text = (question or "").strip()
    if not text:
        return "질문을 입력해 주세요."
    if len(text) < MIN_QUESTION_LENGTH:
        return f"질문이 너무 짧습니다. {MIN_QUESTION_LENGTH}자 이상 입력해 주세요."
    if len(text) > MAX_QUESTION_LENGTH:
        return f"질문이 너무 깁니다. {MAX_QUESTION_LENGTH}자 이하로 입력해 주세요. (현재 {len(text)}자)"
    return None
