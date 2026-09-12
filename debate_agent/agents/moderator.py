"""1차 사회자 노드: 질문을 받아 논쟁 구조를 설계한다."""

from __future__ import annotations

from typing import Any

import config
from agents.base import normalize_side, safe_node
from graph.state import DebateState
from models.schemas import IssueAnalysis, PositionSpec
from prompts import moderator as prompt
from utils.llm import structured_invoke

NODE_NAME = "moderator"


def _fallback(state: DebateState, exc: Exception) -> dict[str, Any]:
    """사회자 실패 시에도 논쟁은 진행되어야 한다. 기본 대립 구도로 대체한다."""
    question = state["question"]
    return {
        "issue": IssueAnalysis(
            issue=question,
            question_type="MIXED",
            question_type_reason="쟁점 분석에 실패하여 기본값으로 분류했습니다.",
            positions=[
                PositionSpec(
                    side=side.id,
                    label=side.label,
                    statement=f"'{question}'에 대해 {side.role_hint}",
                )
                for side in config.SIDES
            ],
            criteria=["논리적 타당성", "근거의 충분성", "질문과의 관련성"],
            ambiguities=[],
            interpretation="쟁점 분석 단계가 실패하여 질문을 문자 그대로 해석합니다.",
        )
    }


#: 표시 라벨 최대 길이. 점수 막대의 진영 태그 폭에 맞춘 값.
MAX_LABEL_LENGTH = 12


def _clean_label(raw: str, fallback: str) -> str:
    """표시 라벨을 정리한다.

    - 비어 있으면 기본 라벨(찬성/반대)로 대체
    - 모델이 습관적으로 붙이는 꼬리말('측', '진영')을 떼어냄
    - 너무 길면 잘라냄
    """
    label = (raw or "").strip()
    for suffix in (" 측", "측", " 진영", "진영"):
        if label.endswith(suffix) and len(label) > len(suffix):
            label = label[: -len(suffix)].strip()
    if not label:
        return fallback
    if len(label) > MAX_LABEL_LENGTH:
        label = label[:MAX_LABEL_LENGTH].rstrip()
    return label or fallback


def _normalize(analysis: IssueAnalysis) -> IssueAnalysis:
    """진영 ID 와 표시 라벨을 보정하고, 누락된 진영에 기본값을 채운다."""
    seen: dict[str, PositionSpec] = {}
    for index, position in enumerate(analysis.positions):
        default_id = config.SIDE_IDS[min(index, len(config.SIDE_IDS) - 1)]
        side_id = normalize_side(position.side, default_id)
        if side_id in seen:
            continue
        seen[side_id] = PositionSpec(
            side=side_id,
            label=_clean_label(position.label, config.get_side(side_id).label),
            statement=position.statement,
        )

    for side in config.SIDES:
        if side.id not in seen:
            seen[side.id] = PositionSpec(
                side=side.id,
                label=side.label,
                statement=f"{analysis.issue}에 대해 {side.role_hint}",
            )

    # 라벨이 서로 겹치면 구분이 되지 않으므로 기본 라벨로 되돌린다.
    labels = [seen[s.id].label for s in config.SIDES]
    if len(set(labels)) < len(labels):
        for side in config.SIDES:
            seen[side.id].label = side.label

    analysis.positions = [seen[s.id] for s in config.SIDES]
    return analysis


@safe_node(NODE_NAME, fallback=_fallback)
def moderator_node(state: DebateState) -> dict[str, Any]:
    question = state["question"]
    analysis = structured_invoke(
        IssueAnalysis,
        prompt.SYSTEM,
        prompt.build_user_prompt(question),
        label=NODE_NAME,
    )
    return {"issue": _normalize(analysis)}
