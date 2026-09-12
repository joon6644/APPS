"""LLM 호출 공통 레이어.

모든 에이전트는 이 모듈을 통해서만 LLM 을 호출한다.
- 모델/키는 환경변수 기반 (config.py)
- structured output 파싱 실패 시 오류 내용을 붙여 제한된 횟수만큼 재시도
- API 오류는 OpenAI SDK 의 백오프(max_retries)에 1차로 위임
"""

from __future__ import annotations

import time
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

import config
from utils.logging import get_logger

logger = get_logger("llm")

TModel = TypeVar("TModel", bound=BaseModel)


class MissingAPIKeyError(RuntimeError):
    """OPENAI_API_KEY 가 설정되지 않은 경우."""


class StructuredOutputError(RuntimeError):
    """재시도 후에도 구조화 출력 파싱에 실패한 경우."""


def ensure_api_key() -> str:
    key = config.get_api_key()
    if not key:
        raise MissingAPIKeyError(
            "OPENAI_API_KEY 를 찾을 수 없습니다. "
            "C:\\Workspace\\APPS\\.env 에 OPENAI_API_KEY=... 를 설정해 주세요."
        )
    return key


def get_llm(model: str | None = None, temperature: float | None = None) -> BaseChatModel:
    """ChatOpenAI 인스턴스를 생성한다. 모델명은 환경변수 기반."""
    # 지연 import: API 키가 없는 상태에서 모듈 import 만으로 실패하지 않도록.
    from langchain_openai import ChatOpenAI

    api_key = ensure_api_key()
    model_name = model or config.get_model_name()

    kwargs: dict = {
        "model": model_name,
        "api_key": api_key,
        "max_retries": config.API_MAX_RETRIES,
        "timeout": 90,
    }
    # gpt-5 계열 추론 모델은 temperature 를 지원하지 않는다.
    if not _is_reasoning_model(model_name):
        kwargs["temperature"] = (
            config.get_temperature() if temperature is None else temperature
        )

    return ChatOpenAI(**kwargs)


def _is_reasoning_model(model_name: str) -> bool:
    lowered = model_name.lower()
    return lowered.startswith(("o1", "o3", "o4", "gpt-5"))


def structured_invoke(
    schema: type[TModel],
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float | None = None,
    retries: int | None = None,
    label: str = "llm",
) -> TModel:
    """구조화 출력을 강제하여 LLM 을 호출한다.

    파싱/검증 실패 시 실패 사유를 대화에 덧붙여 재시도하고,
    끝내 실패하면 StructuredOutputError 를 던진다(호출 측에서 폴백 처리).
    """
    max_retries = config.STRUCTURED_OUTPUT_RETRIES if retries is None else retries
    llm = get_llm(model=model, temperature=temperature)
    structured = llm.with_structured_output(schema, method="json_schema")

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        started = time.perf_counter()
        try:
            result = structured.invoke(messages)
            elapsed = time.perf_counter() - started
            logger.info(
                "%s: %s 응답 성공 (attempt %d, %.2fs)",
                label,
                schema.__name__,
                attempt + 1,
                elapsed,
            )
            if not isinstance(result, schema):  # 방어적 검증
                raise StructuredOutputError(
                    f"예상 타입 {schema.__name__} 이 아닌 {type(result)!r} 를 받았습니다."
                )
            return result
        except Exception as exc:  # noqa: BLE001 - 재시도 대상 폭넓게 수집
            last_error = exc
            elapsed = time.perf_counter() - started
            logger.warning(
                "%s: %s 파싱/호출 실패 (attempt %d/%d, %.2fs): %s",
                label,
                schema.__name__,
                attempt + 1,
                max_retries + 1,
                elapsed,
                _short(exc),
            )
            if attempt >= max_retries:
                break
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
                AIMessage(content="(직전 응답이 형식 요구사항을 충족하지 못했습니다.)"),
                HumanMessage(
                    content=(
                        "직전 응답이 다음 이유로 거부되었습니다:\n"
                        f"{_short(last_error)}\n\n"
                        "요구된 JSON 스키마를 정확히 지켜 모든 필수 필드를 채워 다시 답하세요. "
                        "설명이나 코드블록 없이 스키마에 맞는 값만 생성하세요."
                    )
                ),
            ]

    raise StructuredOutputError(
        f"{schema.__name__} 생성에 {max_retries + 1}회 모두 실패했습니다: {_short(last_error)}"
    ) from last_error


def _short(exc: Exception | None, limit: int = 300) -> str:
    if exc is None:
        return "알 수 없는 오류"
    text = f"{type(exc).__name__}: {exc}"
    return text if len(text) <= limit else text[:limit] + "..."


def clamp_score(value: int | float | None, low: int = 0, high: int = 10) -> int:
    """LLM 이 반환한 점수를 유효 범위로 보정한다.

    OpenAI strict structured output 은 minimum/maximum 제약을 지원하지 않으므로
    스키마가 아니라 여기서 범위를 강제한다.
    """
    if value is None:
        return low
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))
