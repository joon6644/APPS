"""논증 생성 노드 팩토리.

진영마다 별도 파일을 두지 않고 팩토리로 생성한다.
config.SIDES 에 진영을 추가하면 노드가 자동으로 늘어난다.
"""

from __future__ import annotations

from typing import Any, Callable

import config
from agents.base import safe_node
from graph.state import DebateState
from models.schemas import Argument, ArgumentItem
from prompts import debater as prompt
from utils.llm import structured_invoke


def node_name(side_id: str) -> str:
    return f"debate_{side_id}"


def _make_fallback(side_id: str) -> Callable[[DebateState, Exception], dict[str, Any]]:
    def _fallback(state: DebateState, exc: Exception) -> dict[str, Any]:
        placeholder = Argument(
            side=side_id,
            thesis="(논증 생성에 실패했습니다.)",
            arguments=[
                ArgumentItem(
                    claim="논증을 생성하지 못했습니다.",
                    reasoning=f"에이전트 실행 중 오류가 발생했습니다: {type(exc).__name__}",
                    evidence="해당 없음",
                    evidence_status="UNVERIFIED",
                    assumptions=[],
                )
            ],
            self_acknowledged_weaknesses=[
                "이 진영의 논증은 생성되지 않았으므로 판정에서 불리하게 평가되어서는 안 됩니다."
            ],
        )
        return {"arguments": {side_id: placeholder}}

    return _fallback


def _normalize(argument: Argument, side_id: str) -> Argument:
    """side 필드를 강제 고정하고, 논거 개수 상한을 적용한다.

    개수 상한은 편향 방지 장치다. 한 진영이 더 많은 논거를 내서 유리해지지 않도록
    모든 진영에 동일한 상한을 코드에서 적용한다.
    """
    argument.side = side_id
    if len(argument.arguments) > config.MAX_ARGUMENTS_PER_SIDE:
        argument.arguments = argument.arguments[: config.MAX_ARGUMENTS_PER_SIDE]
    return argument


def make_debater_node(side_id: str) -> Callable[[DebateState], dict[str, Any]]:
    """지정한 진영의 논증 생성 노드를 만든다."""

    @safe_node(node_name(side_id), side=side_id, fallback=_make_fallback(side_id))
    def _node(state: DebateState) -> dict[str, Any]:
        issue = state["issue"]
        if issue is None:
            raise RuntimeError("쟁점 분석 결과가 없어 논증을 생성할 수 없습니다.")

        argument = structured_invoke(
            Argument,
            prompt.build_system_prompt(side_id),
            prompt.build_user_prompt(state["question"], issue, side_id),
            label=node_name(side_id),
        )
        return {"arguments": {side_id: _normalize(argument, side_id)}}

    return _node
