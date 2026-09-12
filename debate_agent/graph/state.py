"""LangGraph 공유 상태 정의.

핵심: PRO/CON 브랜치가 같은 superstep 에서 동시에 상태를 갱신하므로,
여러 브랜치가 쓰는 키(arguments, critiques, errors, timeline)에는 반드시 리듀서가 필요하다.
리듀서가 없으면 LangGraph 가 InvalidUpdateError 를 던진다.

진영별 dict 구조를 쓰기 때문에 진영을 N개로 늘려도 상태 정의를 바꿀 필요가 없다.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel

from models.schemas import AgentError, Argument, Critique, FinalJudgment, IssueAnalysis


class NodeTrace(BaseModel):
    """노드 실행 구간 기록. PRO/CON 구간이 겹치는지 확인하는 데 사용."""

    node: str
    started_at: float
    ended_at: float
    ok: bool

    @property
    def duration(self) -> float:
        return self.ended_at - self.started_at


def merge_by_side(
    current: dict[str, BaseModel] | None,
    update: dict[str, BaseModel] | None,
) -> dict[str, BaseModel]:
    """진영별 결과를 얕게 병합하는 리듀서."""
    merged = dict(current or {})
    merged.update(update or {})
    return merged


class DebateState(TypedDict, total=False):
    """논쟁 워크플로 전체 상태."""

    # 입력
    question: str

    # 1단계: 사회자 쟁점 분석
    issue: IssueAnalysis | None

    # 2단계: 진영별 논증 (병렬 쓰기 -> 리듀서 필수)
    arguments: Annotated[dict[str, Argument], merge_by_side]

    # 3단계: 진영별 독립 검증 (병렬 쓰기 -> 리듀서 필수)
    critiques: Annotated[dict[str, Critique], merge_by_side]

    # 4단계: 최종 판정
    judgment: FinalJudgment | None

    # 부가 정보
    errors: Annotated[list[AgentError], operator.add]
    timeline: Annotated[list[NodeTrace], operator.add]


def initial_state(question: str) -> DebateState:
    return DebateState(
        question=question.strip(),
        issue=None,
        arguments={},
        critiques={},
        judgment=None,
        errors=[],
        timeline=[],
    )
