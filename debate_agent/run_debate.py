"""CLI 디버그 하네스.

웹앱과 동일한 그래프를 터미널에서 실행해 검증한다.

    python run_debate.py "짜장면과 짬뽕 중 뭐가 더 맛있어?"
    python run_debate.py --json "재택근무가 사무실 출근보다 생산적인가?"

--json 을 주면 전체 상태를 JSON 으로 덤프한다.
기본 출력에는 노드 실행 구간 타임라인이 포함되어, 진영별 체인이 실제로
병렬 실행되는지(구간이 겹치는지) 확인할 수 있다.
"""

from __future__ import annotations

import argparse
import builtins
import json
import sys
import time

import config
from graph.state import initial_state
from graph.workflow import get_compiled_graph, node_steps
from models.schemas import (
    EVIDENCE_STATUS_LABELS,
    MARGIN_DESCRIPTIONS,
    MARGIN_LABELS,
    QUESTION_TYPE_LABELS,
)
from utils.llm import MissingAPIKeyError, ensure_api_key
from utils.logging import setup_logging
from utils.text import humanize_sides, resolve_labels

RULE = "━" * 60


def _side_name(side_id: str, labels: dict[str, str]) -> str:
    """문장에 넣을 진영 이름. 일반 라벨(찬성/반대)에만 '측'을 붙인다."""
    label = labels.get(side_id, side_id)
    generic = {s.label for s in config.SIDES}
    return f"{label} 측" if label in generic else label


def _print_report(state: dict) -> None:
    issue = state.get("issue")
    judgment = state.get("judgment")
    labels = resolve_labels(issue)

    # 이 함수의 출력은 전부 LLM 생성 텍스트를 포함하므로, 단일 지점에서
    # 진영 ID(PRO/CON)를 표시 라벨로 바꿔 내보낸다.
    def print(*args, **kwargs):  # noqa: A001 - 의도적인 지역 셰도잉
        builtins.print(
            *(humanize_sides(a, labels) if isinstance(a, str) else a for a in args),
            **kwargs,
        )

    print(f"\n{RULE}\n논쟁 분석 결과\n{RULE}\n")
    print(f"질문\n{state['question']}\n")

    if issue:
        label = QUESTION_TYPE_LABELS.get(issue.question_type, issue.question_type)
        print(f"질문 유형\n{issue.question_type} · {label}")
        print(f"  근거: {issue.question_type_reason}")
        print(f"핵심 쟁점\n{issue.issue}")
        print(f"해석 방향\n{issue.interpretation}")
        if issue.ambiguities:
            print("모호성")
            for item in issue.ambiguities:
                print(f"  - {item}")
        print("공통 판단 기준")
        for item in issue.criteria:
            print(f"  - {item}")
        print()

    if judgment:
        margin_label = MARGIN_LABELS.get(judgment.margin_level, judgment.margin_level)
        win = max(50, min(100, judgment.margin_score))
        winner = config.SIDE_MAP.get(judgment.verdict)
        loser = next((s for s in config.SIDES if s.id != judgment.verdict), None)

        print(f"{RULE}\n최종 판정: {_side_name(judgment.verdict, labels)} 승리  [{margin_label}]"
              f" (신뢰도 {judgment.confidence:.0%})\n{RULE}")
        print(f"\n{judgment.headline}\n")

        if winner and loser:
            width = 40
            filled = int(win / 100 * width)
            print("우세 격차")
            print(f"  {labels.get(winner.id, winner.id)} {win}  |{'█' * filled}{'░' * (width - filled)}|"
                  f"  {100 - win} {labels.get(loser.id, loser.id)}")
            print(f"  {MARGIN_DESCRIPTIONS.get(judgment.margin_level, '')}")
            print(f"  {judgment.margin_reason}")
            print()

        print("판정 이유")
        print(judgment.reasoning_for_verdict)
        print()
    else:
        print(f"{RULE}\n최종 판정: 실패 (판정 에이전트가 응답하지 못했습니다)\n{RULE}")
        print("없는 근거로 승패를 만들어내지 않기 위해 판정을 비워 둡니다.")
        print("아래의 양측 논증과 검증 결과는 그대로 확인하실 수 있습니다.\n")

    for side in config.SIDES:
        argument = state.get("arguments", {}).get(side.id)
        critique = state.get("critiques", {}).get(side.id)
        analysis = next(
            (a for a in (judgment.side_analyses if judgment else []) if a.side == side.id),
            None,
        )

        print(f"{RULE}\n{_side_name(side.id, labels)}\n{RULE}")
        if argument:
            print(f"\n핵심 주장\n{argument.thesis}\n")
            print("주요 논거")
            for index, item in enumerate(argument.arguments, start=1):
                status = EVIDENCE_STATUS_LABELS.get(
                    item.evidence_status, item.evidence_status
                )
                print(f"  {index}. {item.claim}   [{status}]")
                print(f"     추론: {item.reasoning}")
                print(f"     근거: {item.evidence}")
                if item.assumptions:
                    print(f"     전제: {'; '.join(item.assumptions)}")
            if argument.self_acknowledged_weaknesses:
                print("\n스스로 인정한 약점")
                for item in argument.self_acknowledged_weaknesses:
                    print(f"  - {item}")

        if analysis:
            print("\n사회자가 본 강점")
            for item in analysis.strengths or ["(없음)"]:
                print(f"  + {item}")
            print("사회자가 본 약점")
            for item in analysis.weaknesses or ["(없음)"]:
                print(f"  - {item}")

        if critique:
            print("\n검증 결과")
            print(f"  종합: {critique.overall_assessment}")
            if critique.logical_flaws:
                print("  발견된 논리적 문제")
                for flaw in critique.logical_flaws:
                    print(f"    ⚠ [{flaw.severity}] {flaw.target_claim}")
                    print(f"       {flaw.explanation}")
            if critique.factual_concerns:
                print("  사실성 지적")
                for concern in critique.factual_concerns:
                    mark = "확인 가능" if concern.verifiable else "검증 불가(외부 자료 필요)"
                    print(f"    ⚠ ({mark}) {concern.claim}: {concern.concern}")
            scores = ", ".join(
                f"{label} {value}" for _, label, value in critique.scores.as_items()
            )
            print(f"  점수(참고): {scores}")
        print()

    if judgment and judgment.comparison:
        print(f"{RULE}\n기준별 비교\n{RULE}")
        for row in judgment.comparison:
            detail = "  ".join(
                f"{labels.get(a.side, a.side)} {a.score}/10"
                for a in row.assessments
                if a.side in config.SIDE_MAP
            )
            print(f"  {row.criterion}: {detail}")
            print(f"     {row.note}")
        print()

        totals = {
            sid: c.scores.total() for sid, c in state.get("critiques", {}).items()
        }
        if len(totals) >= 2:
            summary = " / ".join(
                f"{labels.get(sid, sid)} {total}"
                for sid, total in totals.items()
                if sid in config.SIDE_MAP
            )
            print(f"  검증 점수 합계(70점 만점, 참고): {summary}")
            leader = max(totals, key=lambda sid: totals[sid])
            if leader != judgment.verdict and totals[leader] != totals.get(judgment.verdict):
                print("  ※ 점수 합계가 높은 쪽과 판정이 엇갈렸습니다."
                      " 이 시스템은 점수 합계로 승자를 정하지 않습니다.")
            print()

    if judgment:
        if judgment.limitations:
            print(f"{RULE}\n이 판단의 한계\n{RULE}")
            for item in judgment.limitations:
                print(f"  - {item}")
            print()
        if judgment.reframing_suggestions:
            print("질문을 이렇게 바꾸면 결론이 달라질 수 있습니다")
            for item in judgment.reframing_suggestions:
                print(f"  - {item}")
            print()

    errors = state.get("errors", [])
    if errors:
        print(f"{RULE}\n발생한 오류 (그래프는 폴백으로 계속 진행됨)\n{RULE}")
        for error in errors:
            print(f"  ✖ {error.node} ({error.side}): {error.message}")
        print()


def _print_timeline(state: dict, wall_clock: float) -> None:
    timeline = sorted(state.get("timeline", []), key=lambda t: t.started_at)
    if not timeline:
        return

    origin = timeline[0].started_at
    total = max(t.ended_at for t in timeline) - origin
    width = 46

    print(f"{RULE}\n노드 실행 타임라인 (구간이 겹치면 병렬 실행)\n{RULE}")
    for trace in timeline:
        start_offset = trace.started_at - origin
        start_col = int(start_offset / total * width) if total > 0 else 0
        bar_len = max(1, int(trace.duration / total * width)) if total > 0 else 1
        bar = " " * start_col + ("█" if trace.ok else "▒") * bar_len
        flag = "" if trace.ok else "  (실패)"
        print(f"  {trace.node:<18} |{bar:<{width}}| {trace.duration:5.2f}s{flag}")

    sequential = sum(t.duration for t in timeline)
    print(f"\n  순차 실행 시 합계: {sequential:.2f}s")
    print(f"  실제 소요 시간   : {wall_clock:.2f}s")
    if sequential > 0:
        print(f"  병렬화 효과      : {sequential / wall_clock:.2f}x")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Debate Judge CLI 하네스")
    parser.add_argument("question", help="분석할 질문")
    parser.add_argument("--json", action="store_true", help="전체 상태를 JSON 으로 덤프")
    parser.add_argument("--quiet", action="store_true", help="노드 로그 숨김")
    args = parser.parse_args()

    setup_logging("WARNING" if args.quiet else "INFO")

    error = config.validate_question(args.question)
    if error:
        print(f"입력 오류: {error}", file=sys.stderr)
        return 2

    try:
        ensure_api_key()
    except MissingAPIKeyError as exc:
        print(f"설정 오류: {exc}", file=sys.stderr)
        return 2

    graph = get_compiled_graph()
    started = time.perf_counter()
    final_state = graph.invoke(initial_state(args.question))
    wall_clock = time.perf_counter() - started

    if args.json:
        dumpable = {
            "question": final_state["question"],
            "issue": final_state["issue"].model_dump() if final_state.get("issue") else None,
            "arguments": {
                k: v.model_dump() for k, v in final_state.get("arguments", {}).items()
            },
            "critiques": {
                k: v.model_dump() for k, v in final_state.get("critiques", {}).items()
            },
            "judgment": (
                final_state["judgment"].model_dump() if final_state.get("judgment") else None
            ),
            "errors": [e.model_dump() for e in final_state.get("errors", [])],
        }
        print(json.dumps(dumpable, ensure_ascii=False, indent=2))
    else:
        _print_report(final_state)
        _print_timeline(final_state, wall_clock)
        print(f"등록된 노드: {', '.join(name for name, _, _ in node_steps())}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
