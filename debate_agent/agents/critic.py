"""검증 노드 팩토리.

정보 격리 원칙:
이 노드는 state["arguments"] 에서 '자기 진영의 논증만' 꺼내 프롬프트에 넣는다.
상대 진영의 논증은 프롬프트 빌더에 전달조차 하지 않으므로,
검증자가 상대 주장을 근거로 판단하는 일이 구조적으로 불가능하다.
"""

from __future__ import annotations

from typing import Any, Callable

from agents.base import safe_node
from graph.state import DebateState
from models.schemas import Critique, ScoreCard
from prompts import critic as prompt
from utils.llm import clamp_score, structured_invoke


def node_name(side_id: str) -> str:
    return f"critic_{side_id}"


def _make_fallback(side_id: str) -> Callable[[DebateState, Exception], dict[str, Any]]:
    def _fallback(state: DebateState, exc: Exception) -> dict[str, Any]:
        placeholder = Critique(
            side=side_id,
            logical_strengths=[],
            logical_flaws=[],
            factual_concerns=[],
            unsupported_claims=[],
            assumption_assessment=[],
            scores=ScoreCard(
                logical_consistency=0,
                evidence_quality=0,
                premise_validity=0,
                claim_support=0,
                robustness=0,
                factuality=0,
                relevance=0,
            ),
            overall_assessment=(
                f"검증에 실패했습니다({type(exc).__name__}). "
                "이 점수는 평가 결과가 아니라 검증 불가 표시이므로 판정 근거로 쓰지 마십시오."
            ),
        )
        return {"critiques": {side_id: placeholder}}

    return _fallback


def _normalize(critique: Critique, side_id: str) -> Critique:
    """side 를 고정하고, 점수를 0~10 범위로 보정한다.

    OpenAI strict structured output 은 minimum/maximum 을 지원하지 않아
    스키마 대신 여기서 범위를 강제한다.
    """
    critique.side = side_id
    scores = critique.scores
    for field in ScoreCard.model_fields:
        setattr(scores, field, clamp_score(getattr(scores, field)))
    return critique


def make_critic_node(side_id: str) -> Callable[[DebateState], dict[str, Any]]:
    """지정한 진영의 논증만 검증하는 노드를 만든다."""

    @safe_node(node_name(side_id), side=side_id, fallback=_make_fallback(side_id))
    def _node(state: DebateState) -> dict[str, Any]:
        issue = state["issue"]
        if issue is None:
            raise RuntimeError("쟁점 분석 결과가 없어 검증할 수 없습니다.")

        # ── 정보 격리 지점: 자기 진영 논증만 꺼낸다 ──────────────────
        own_argument = state.get("arguments", {}).get(side_id)
        if own_argument is None:
            raise RuntimeError(f"{side_id} 진영의 논증이 없어 검증할 수 없습니다.")
        # ────────────────────────────────────────────────────────────

        critique = structured_invoke(
            Critique,
            prompt.build_system_prompt(side_id),
            prompt.build_user_prompt(state["question"], issue, own_argument),
            label=node_name(side_id),
        )
        return {"critiques": {side_id: _normalize(critique, side_id)}}

    return _node
