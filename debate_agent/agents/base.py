"""노드 공통 인프라: 오류 격리, 실행 시간 기록, 진영 ID 정규화."""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any

import config
from graph.state import DebateState, NodeTrace
from models.schemas import AgentError
from utils.logging import get_logger

logger = get_logger("node")


NodeFunc = Callable[[DebateState], dict[str, Any]]
FallbackFunc = Callable[[DebateState, Exception], dict[str, Any]]


def safe_node(
    node_name: str,
    side: str = "-",
    fallback: FallbackFunc | None = None,
) -> Callable[[NodeFunc], NodeFunc]:
    """노드 예외를 상태로 흡수하는 데코레이터.

    에이전트 하나가 실패해도 그래프가 끝까지 진행되도록 예외를 errors 에 기록하고,
    fallback 이 주어지면 그 결과를 대신 상태에 반영한다.
    실행 구간(NodeTrace)도 함께 기록해 병렬 실행 여부를 사후에 확인할 수 있게 한다.
    """

    def decorator(func: NodeFunc) -> NodeFunc:
        @wraps(func)
        def wrapper(state: DebateState) -> dict[str, Any]:
            started = time.time()
            logger.info("▶ %s 시작", node_name)
            try:
                result = func(state)
                ended = time.time()
                logger.info("■ %s 완료 (%.2fs)", node_name, ended - started)
                result["timeline"] = [
                    *result.get("timeline", []),
                    NodeTrace(node=node_name, started_at=started, ended_at=ended, ok=True),
                ]
                return result
            except Exception as exc:  # noqa: BLE001 - 전체 중단 방지가 목적
                ended = time.time()
                logger.error("✖ %s 실패 (%.2fs): %s", node_name, ended - started, exc)
                result = fallback(state, exc) if fallback else {}
                result["errors"] = [
                    *result.get("errors", []),
                    AgentError(
                        node=node_name,
                        side=side,
                        message=f"{type(exc).__name__}: {exc}",
                    ),
                ]
                result["timeline"] = [
                    *result.get("timeline", []),
                    NodeTrace(node=node_name, started_at=started, ended_at=ended, ok=False),
                ]
                return result

        return wrapper

    return decorator


def normalize_side(value: str | None, default: str) -> str:
    """LLM 이 반환한 진영 ID 를 레지스트리에 존재하는 값으로 보정한다.

    모델이 'NOTE' 같은 존재하지 않는 진영을 만들어내는 경우가 있어 방어가 필요하다.
    """
    if not value:
        return default
    candidate = value.strip().upper()
    if candidate in config.SIDE_IDS:
        return candidate
    # 라벨("찬성")로 답한 경우도 수용
    for side in config.SIDES:
        if candidate == side.label:
            return side.id
    return default


def is_known_side(value: str | None) -> bool:
    return bool(value) and value.strip().upper() in config.SIDE_IDS
