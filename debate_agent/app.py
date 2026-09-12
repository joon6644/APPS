"""AI Debate Judge - Streamlit 웹 애플리케이션.

실행:
    streamlit run app.py
브라우저에서 http://localhost:8501 로 접속한다.
"""

from __future__ import annotations

from html import escape
from typing import Any, Callable

import streamlit as st

st.set_page_config(
    page_title="AI Debate Judge",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

import config  # noqa: E402
from graph.state import initial_state  # noqa: E402
from graph.workflow import get_compiled_graph, node_steps  # noqa: E402
from ui import render, styles  # noqa: E402
from utils.llm import MissingAPIKeyError, ensure_api_key  # noqa: E402
from utils.logging import setup_logging  # noqa: E402
from utils.text import default_labels, resolve_labels  # noqa: E402

setup_logging()


# ---------------------------------------------------------------------------
# 세션 상태
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "phase": "input",  # input | running | result
    "question_text": "",
    "pending_question": "",
    "result": None,
    # 이미 그려진 text_area 는 session_state 를 바꿔도 값이 갱신되지 않는다.
    # 키에 nonce 를 붙여 '새 위젯'으로 만들어야 예시 질문 클릭이 입력창에 반영된다.
    "input_nonce": 0,
}


def init_session() -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)


def set_question(text: str) -> None:
    """입력창 내용을 프로그램적으로 교체한다."""
    st.session_state.question_text = text
    st.session_state.input_nonce += 1


def reset_to_input(keep_question: bool = True) -> None:
    st.session_state.phase = "input"
    st.session_state.result = None
    set_question(st.session_state.question_text if keep_question else "")


# ---------------------------------------------------------------------------
# 그래프 실행 (진행 상황 스트리밍)
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _graph():
    """컴파일된 그래프는 rerun 마다 재생성하지 않는다."""
    return get_compiled_graph()


def run_graph(
    question: str, on_node_done: Callable[[str, dict[str, Any]], None]
) -> dict[str, Any]:
    """그래프를 스트리밍 실행하며 노드 완료마다 콜백을 호출한다.

    stream_mode 를 리스트로 주면 (mode, chunk) 튜플이 나온다.
    - "updates": 방금 끝난 노드 이름 -> 진행 표시 갱신
    - "values" : 누적된 전체 상태     -> 최종 결과 확보

    콜백에 누적 상태도 함께 넘긴다. 사회자 노드가 끝나면 진영 표시 라벨이
    정해지므로, 진행 표시를 그때부터 실제 라벨로 바꿔 줄 수 있다.
    """
    graph = _graph()
    final_state: dict[str, Any] = {}

    for mode, chunk in graph.stream(
        initial_state(question), stream_mode=["updates", "values"]
    ):
        if mode == "updates":
            for node_name in chunk:
                on_node_done(node_name, final_state)
        elif mode == "values":
            final_state = chunk

    return final_state


# ---------------------------------------------------------------------------
# 진행 상황 표시
# ---------------------------------------------------------------------------


def steps_html(done: set[str], active: set[str], labels: dict[str, str]) -> str:
    generic = {side.label for side in config.SIDES}
    rows = []
    for name, template, side_id in node_steps():
        if side_id is None:
            text = template
        else:
            label = labels.get(side_id, side_id)
            text = template.format(
                side=f"{label} 측" if label in generic else label
            )

        if name in done:
            state, mark = "done", "✓"
        elif name in active:
            state, mark = "active", "●"
        else:
            state, mark = "pending", "○"
        rows.append(
            f'<div class="step {state}"><span class="mark">{mark}</span>'
            f"<span>{escape(text)}</span></div>"
        )
    return f'<div class="card"><h3>분석 진행 상황</h3><div class="steps">{"".join(rows)}</div></div>'


#: 노드 완료 시 다음으로 활성화될 노드들 (진행 표시용)
def next_active(done: set[str]) -> set[str]:
    order = [name for name, _, _ in node_steps()]
    moderator = order[0]
    debaters = [n for n in order if n.startswith("debate_")]
    critics = [n for n in order if n.startswith("critic_")]
    final = order[-1]

    if moderator not in done:
        return {moderator}
    pending_debaters = {n for n in debaters if n not in done}
    pending_critics = set()
    for critic in critics:
        side = critic.removeprefix("critic_")
        if f"debate_{side}" in done and critic not in done:
            pending_critics.add(critic)
    if pending_debaters or pending_critics:
        return pending_debaters | pending_critics
    if final not in done:
        return {final}
    return set()


# ---------------------------------------------------------------------------
# 화면: 입력
# ---------------------------------------------------------------------------


def view_input() -> None:
    st.markdown(
        """
<div class="hero">
  <h1>AI Debate Judge</h1>
  <p class="quote">"어느 쪽의 논리가 더 합리적인가?"</p>
  <p class="sub">찬반 에이전트가 논증을 세우고, 독립된 검증 에이전트가 각각을 따로 검증한 뒤,
     사회자가 그 결과를 근거로 판정합니다.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1, 3, 1])
    with center:
        typed = st.text_area(
            "질문",
            value=st.session_state.question_text,
            key=f"question_input_{st.session_state.input_nonce}",
            height=110,
            placeholder="예: 재택근무가 사무실 출근보다 생산적인가?",
            label_visibility="collapsed",
        )
        # 사용자가 직접 타이핑한 내용을 정식 상태에 반영
        st.session_state.question_text = typed

        submitted = st.button("⚖  분석 시작", type="primary", use_container_width=True)

        if submitted:
            error = config.validate_question(typed)
            if error:
                st.error(error)
            else:
                st.session_state.pending_question = typed.strip()
                st.session_state.phase = "running"
                st.rerun()

        st.markdown(
            '<p style="text-align:center;color:var(--ink-faint);font-size:.82rem;'
            'margin:1.6rem 0 .5rem">이런 질문을 해보세요</p>',
            unsafe_allow_html=True,
        )
        for index, example in enumerate(config.EXAMPLE_QUESTIONS):
            if st.button(example, key=f"example_{index}", use_container_width=True):
                set_question(example)
                st.rerun()


# ---------------------------------------------------------------------------
# 화면: 실행 중
# ---------------------------------------------------------------------------


def view_running() -> None:
    question = st.session_state.pending_question
    st.markdown(
        f'<div class="card"><h3>분석 중인 질문</h3><p><strong>{escape(question)}</strong></p></div>',
        unsafe_allow_html=True,
    )

    placeholder = st.empty()
    done: set[str] = set()
    labels = default_labels()
    placeholder.markdown(
        steps_html(done, next_active(done), labels), unsafe_allow_html=True
    )

    def on_node_done(node_name: str, partial: dict[str, Any]) -> None:
        nonlocal labels
        done.add(node_name)
        # 사회자가 끝나면 진영 표시 라벨이 정해진다. 그때부터 실제 라벨로 보여준다.
        if partial.get("issue") is not None:
            labels = resolve_labels(partial["issue"])
        placeholder.markdown(
            steps_html(done, next_active(done), labels), unsafe_allow_html=True
        )

    try:
        result = run_graph(question, on_node_done)
    except MissingAPIKeyError as exc:
        placeholder.empty()
        st.error(str(exc))
        if st.button("← 돌아가기"):
            reset_to_input()
            st.rerun()
        return
    except Exception as exc:  # noqa: BLE001 - 어떤 실패도 화면에서 복구 가능해야 한다
        placeholder.empty()
        st.error(f"분석 중 예기치 못한 오류가 발생했습니다.\n\n`{type(exc).__name__}: {exc}`")
        if st.button("← 돌아가기"):
            reset_to_input()
            st.rerun()
        return

    placeholder.markdown(
        steps_html({name for name, _, _ in node_steps()}, set(), labels),
        unsafe_allow_html=True,
    )
    st.session_state.result = result
    st.session_state.phase = "result"
    st.rerun()


# ---------------------------------------------------------------------------
# 화면: 결과
# ---------------------------------------------------------------------------


def view_result() -> None:
    state = st.session_state.result or {}
    question = state.get("question", "")

    st.markdown(
        f"""
<div class="hero" style="padding-bottom:1.2rem">
  <p class="sub" style="margin-bottom:.4rem">분석한 질문</p>
  <h1 style="font-size:1.7rem">{escape(question)}</h1>
</div>
""",
        unsafe_allow_html=True,
    )

    render.render_result(state)

    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
    left, center, right = st.columns([1, 2, 1])
    with center:
        if st.button("＋  새로운 질문 분석하기", type="primary", use_container_width=True):
            reset_to_input(keep_question=False)
            st.rerun()
        if st.button("✎  이 질문을 수정해서 다시 분석", use_container_width=True):
            st.session_state.question_text = question
            reset_to_input(keep_question=True)
            st.rerun()

        st.markdown(
            '<p style="text-align:center;color:var(--ink-faint);font-size:.78rem;'
            'margin-top:1rem">이 분석은 AI 에이전트들이 생성한 것으로, '
            "확정적 사실이나 정답이 아닙니다.</p>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# 엔트리포인트
# ---------------------------------------------------------------------------


def main() -> None:
    init_session()
    st.markdown(styles.inject(), unsafe_allow_html=True)

    try:
        ensure_api_key()
    except MissingAPIKeyError as exc:
        st.error(str(exc))
        st.stop()

    phase = st.session_state.phase
    if phase == "running":
        view_running()
    elif phase == "result":
        view_result()
    else:
        view_input()

    st.markdown(
        f'<p style="text-align:center;color:var(--ink-faint);font-size:.75rem;'
        f'margin-top:2.5rem">모델 {escape(config.get_model_name())} · '
        f"LangGraph 멀티 에이전트 · 결과는 AI 의 분석이며 확정적 사실이 아닙니다</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
