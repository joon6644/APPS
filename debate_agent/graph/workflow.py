"""LangGraph 워크플로 조립.

구조:
    START -> moderator
                |
        ┌───────┴───────┐        superstep 2 (병렬)
        v               v
    debate_PRO      debate_CON
        v               v        superstep 3 (병렬)
    critic_PRO      critic_CON
        └───────┬───────┘        join: 양쪽 완료 후 1회 실행
                v
        final_moderator -> END

노드와 엣지는 config.SIDES 를 순회하며 생성되므로, 진영을 추가해도 이 파일은 바뀌지 않는다.
LangGraph 는 같은 superstep 의 노드를 동시에 실행하므로 진영별 체인이 실제로 병렬로 돈다.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

import config
from agents.critic import make_critic_node, node_name as critic_node_name
from agents.debater import make_debater_node, node_name as debate_node_name
from agents.final_moderator import NODE_NAME as FINAL_NODE, final_moderator_node
from agents.moderator import NODE_NAME as MODERATOR_NODE, moderator_node
from graph.state import DebateState

def node_steps() -> list[tuple[str, str, str | None]]:
    """진행 표시용 (노드명, 설명 템플릿, 진영 ID) 목록. 그래프 구조와 동일한 순서.

    설명에 진영이 들어가는 단계는 `{side}` 자리표시자를 둔다. 진영의 표시 라벨은
    사회자가 질문에 맞춰 정하므로(찬성/반대 또는 청년피자/처갓집 치킨) 여기서 고정하지 않는다.
    """
    steps: list[tuple[str, str, str | None]] = [
        (MODERATOR_NODE, "질문의 쟁점 분석", None)
    ]
    for side in config.SIDES:
        steps.append((debate_node_name(side.id), "{side} 논증 생성", side.id))
    for side in config.SIDES:
        steps.append((critic_node_name(side.id), "{side} 논증 검증", side.id))
    steps.append((FINAL_NODE, "최종 판정", None))
    return steps


def node_labels() -> list[tuple[str, str]]:
    """기본 라벨(찬성/반대)을 적용한 (노드명, 설명) 목록."""
    return [
        (name, template.format(side=f"{config.SIDE_MAP[side_id].label} 측") if side_id else template)
        for name, template, side_id in node_steps()
    ]


def build_graph() -> StateGraph:
    graph = StateGraph(DebateState)

    graph.add_node(MODERATOR_NODE, moderator_node)
    graph.add_node(FINAL_NODE, final_moderator_node)
    graph.add_edge(START, MODERATOR_NODE)

    for side in config.SIDES:
        debate_name = debate_node_name(side.id)
        critic_name = critic_node_name(side.id)

        graph.add_node(debate_name, make_debater_node(side.id))
        graph.add_node(critic_name, make_critic_node(side.id))

        # fan-out: 사회자 -> 각 진영 (동시 실행)
        graph.add_edge(MODERATOR_NODE, debate_name)
        # 진영별 체인: 논증 -> 그 진영 전용 검증
        graph.add_edge(debate_name, critic_name)
        # fan-in: 모든 검증이 끝나야 최종 판정이 1회 실행된다
        graph.add_edge(critic_name, FINAL_NODE)

    graph.add_edge(FINAL_NODE, END)
    return graph


@lru_cache(maxsize=1)
def get_compiled_graph():
    """컴파일된 그래프(싱글턴). Streamlit rerun 마다 재생성되지 않도록 캐싱한다."""
    return build_graph().compile()
