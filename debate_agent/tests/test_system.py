"""시스템 불변식 테스트 (LLM 호출 없음 -> API 비용 0).

이 프로젝트가 '토론 챗봇'이 아니라 '논증 검증 시스템'이 되게 하는 핵심 설계 주장을
코드로 검증한다. 프롬프트를 고치다 보면 쉽게 깨지는 것들이므로 반드시 유지할 것.

실행:
    python tests/test_system.py
"""

from __future__ import annotations

import importlib
import random
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from models.schemas import (  # noqa: E402
    Argument,
    ArgumentItem,
    Critique,
    IssueAnalysis,
    PositionSpec,
    ScoreCard,
)

_failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  -- {detail}" if detail and not condition else ""
    print(f"[{status}] {name}{suffix}")
    if not condition:
        _failures.append(name)


def section(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 56 - len(title)))


# ---------------------------------------------------------------------------
# 테스트 픽스처
# ---------------------------------------------------------------------------

#: 진영별 고유 표식. 정보 격리 검증에 쓰이므로 서로 겹치지 않아야 하고,
#: UI 에 내부 ID 가 새어나오는지 확인하는 테스트를 위해 "PRO"/"CON" 문자열을 포함하지 않는다.
SECRET = {"PRO": "첫째진영_고유표식_XYZZY", "CON": "둘째진영_고유표식_PLUGH"}


def make_argument(side: str, marker: str) -> Argument:
    return Argument(
        side=side,
        thesis=f"{marker} 라는 주장이다",
        arguments=[
            ArgumentItem(
                claim=marker,
                reasoning=f"{marker} 때문이다",
                evidence=marker,
                evidence_status="COMMON_KNOWLEDGE",
                assumptions=[marker],
            )
        ],
        self_acknowledged_weaknesses=[marker],
    )


def make_critique(side: str) -> Critique:
    return Critique(
        side=side,
        logical_strengths=["강점 1"],
        logical_flaws=[],
        factual_concerns=[],
        unsupported_claims=[],
        assumption_assessment=["전제 평가"],
        scores=ScoreCard(
            logical_consistency=7,
            evidence_quality=6,
            premise_validity=7,
            claim_support=6,
            robustness=5,
            factuality=8,
            relevance=9,
        ),
        overall_assessment="종합 평가",
    )


def make_issue(labels: dict[str, str] | None = None) -> IssueAnalysis:
    resolved = labels or {s.id: s.label for s in config.SIDES}
    return IssueAnalysis(
        issue="테스트 쟁점",
        question_type="SUBJECTIVE",
        question_type_reason="테스트",
        positions=[
            PositionSpec(
                side=s.id,
                label=resolved.get(s.id, s.label),
                statement=f"{s.id} 입장",
            )
            for s in config.SIDES
        ],
        criteria=["기준1", "기준2"],
        ambiguities=[],
        interpretation="테스트 해석",
    )


# ---------------------------------------------------------------------------
# 1. 정보 격리 - 이 시스템의 가장 중요한 불변식
# ---------------------------------------------------------------------------


def test_information_isolation() -> None:
    section("정보 격리: Critic 은 자기 진영 논증만 본다")

    from agents.critic import make_critic_node
    from prompts import critic as critic_prompt

    issue = make_issue()
    arguments = {side: make_argument(side, SECRET[side]) for side in ("PRO", "CON")}

    # 프롬프트 레벨
    for side, other in (("PRO", "CON"), ("CON", "PRO")):
        text = critic_prompt.build_user_prompt("질문", issue, arguments[side])
        check(f"{side} Critic 프롬프트에 자기 논증 포함", SECRET[side] in text)
        check(
            f"{side} Critic 프롬프트에 상대({other}) 논증 없음",
            SECRET[other] not in text,
            "상대 논증이 검증 프롬프트로 새어 들어감",
        )

    # 노드 레벨: 실제 호출 인자를 가로채 확인
    for side, other in (("PRO", "CON"), ("CON", "PRO")):
        captured: dict[str, str] = {}

        def fake_invoke(schema, system_prompt, user_prompt, **kwargs):
            captured["text"] = system_prompt + user_prompt
            return make_critique(side)

        state = {
            "question": "질문",
            "issue": issue,
            "arguments": arguments,
            "critiques": {},
        }
        with patch("agents.critic.structured_invoke", fake_invoke):
            make_critic_node(side)(state)  # type: ignore[arg-type]

        check(f"{side} Critic 노드에 자기 논증 전달됨", SECRET[side] in captured["text"])
        check(
            f"{side} Critic 노드에 상대({other}) 논증 전달 안 됨",
            SECRET[other] not in captured["text"],
        )


def test_final_moderator_sees_both() -> None:
    section("최종 판정에서만 양측 정보가 합쳐진다")

    from prompts import final_moderator as final_prompt

    issue = make_issue()
    arguments = {side: make_argument(side, SECRET[side]) for side in ("PRO", "CON")}
    critiques = {side: make_critique(side) for side in ("PRO", "CON")}

    text = final_prompt.build_user_prompt(
        "질문", issue, arguments, critiques, ["PRO", "CON"]
    )
    check("최종 판정에 PRO 논증 포함", SECRET["PRO"] in text)
    check("최종 판정에 CON 논증 포함", SECRET["CON"] in text)

    # 순서 셔플이 프롬프트에 실제로 반영되는가 (위치 편향 방지)
    pro_first = final_prompt.build_user_prompt(
        "질문", issue, arguments, critiques, ["PRO", "CON"]
    )
    con_first = final_prompt.build_user_prompt(
        "질문", issue, arguments, critiques, ["CON", "PRO"]
    )
    check(
        "진영 순서가 프롬프트에 실제로 반영됨",
        pro_first.index(SECRET["PRO"]) < pro_first.index(SECRET["CON"])
        and con_first.index(SECRET["CON"]) < con_first.index(SECRET["PRO"]),
    )

    seen = set()
    for seed in range(30):
        random.seed(seed)
        order = list(config.SIDE_IDS)
        random.shuffle(order)
        seen.add(tuple(order))
    random.seed()
    check("셔플이 두 순서를 모두 생성", len(seen) == 2, str(seen))


# ---------------------------------------------------------------------------
# 2. 편향 방지 장치
# ---------------------------------------------------------------------------


def test_bias_guards() -> None:
    section("편향 방지: 길이/진영 ID/점수 보정")

    from agents.base import is_known_side, normalize_side
    from agents.debater import _normalize as normalize_argument
    from utils.llm import clamp_score

    over_long = make_argument("PRO", "x")
    over_long.arguments = over_long.arguments * 10
    check(
        "논거 개수 상한으로 길이 편향 차단",
        len(normalize_argument(over_long, "PRO").arguments)
        == config.MAX_ARGUMENTS_PER_SIDE,
    )
    check("side 필드 강제 고정", normalize_argument(make_argument("WRONG", "y"), "CON").side == "CON")

    check("존재하지 않는 진영 -> 기본값", normalize_side("NOTE", "PRO") == "PRO")
    check("소문자 진영 보정", normalize_side("pro", "CON") == "PRO")
    check("한글 라벨 보정", normalize_side("찬성", "CON") == "PRO")
    check("None -> 기본값", normalize_side(None, "CON") == "CON")
    check("is_known_side 방어", not is_known_side("NOTE") and is_known_side("PRO"))

    check("점수 상한 clamp", clamp_score(99) == 10)
    check("점수 하한 clamp", clamp_score(-5) == 0)
    check("None -> 0", clamp_score(None) == 0)
    check("파싱 불가 -> 0", clamp_score("abc") == 0)
    check("실수 반올림", clamp_score(7.6) == 8)


# ---------------------------------------------------------------------------
# 3. 확장성: 진영 추가 시 그래프가 자동으로 늘어나는가
# ---------------------------------------------------------------------------


def test_extensibility() -> None:
    section("확장성: config.SIDES 에 진영을 추가하면 그래프가 자동 확장")

    import graph.workflow as wf

    original = (config.SIDES, config.SIDE_IDS, config.SIDE_MAP)
    neutral = config.SideSpec(
        id="NEUTRAL",
        label="중립",
        color="#0f766e",
        role_hint="양측 모두 결정적이지 않다는 제3의 입장",
    )
    try:
        config.SIDES = (*original[0], neutral)
        config.SIDE_IDS = tuple(s.id for s in config.SIDES)
        config.SIDE_MAP = {s.id: s for s in config.SIDES}
        importlib.reload(wf)

        nodes = set(wf.build_graph().compile().get_graph().nodes) - {"__start__", "__end__"}
        expected = {
            "moderator",
            "final_moderator",
            "debate_PRO",
            "debate_CON",
            "debate_NEUTRAL",
            "critic_PRO",
            "critic_CON",
            "critic_NEUTRAL",
        }
        check("3진영 노드 자동 생성", nodes == expected, f"actual={sorted(nodes)}")
        check("진행 표시 라벨도 8개", len(wf.node_labels()) == 8)
    finally:
        config.SIDES, config.SIDE_IDS, config.SIDE_MAP = original
        importlib.reload(wf)

    nodes = set(wf.build_graph().compile().get_graph().nodes) - {"__start__", "__end__"}
    check(
        "복원 후 2진영 그래프",
        nodes
        == {"moderator", "final_moderator", "debate_PRO", "debate_CON", "critic_PRO", "critic_CON"},
    )


# ---------------------------------------------------------------------------
# 4. 그래프 구조: 병렬 실행과 조인
# ---------------------------------------------------------------------------


def test_graph_topology() -> None:
    section("그래프 구조: 병렬 fan-out 과 단일 fan-in")

    from graph.workflow import build_graph

    compiled = build_graph().compile()
    edges = {(e.source, e.target) for e in compiled.get_graph().edges}

    for side in config.SIDE_IDS:
        check(f"moderator -> debate_{side}", ("moderator", f"debate_{side}") in edges)
        check(f"debate_{side} -> critic_{side}", (f"debate_{side}", f"critic_{side}") in edges)
        check(f"critic_{side} -> final_moderator", (f"critic_{side}", "final_moderator") in edges)

    cross = [
        (a, b)
        for a, b in edges
        if a.startswith("debate_")
        and b.startswith("critic_")
        and a.removeprefix("debate_") != b.removeprefix("critic_")
    ]
    check("진영 간 교차 엣지 없음", not cross, f"교차 엣지 발견: {cross}")


# ---------------------------------------------------------------------------
# 5. 오류 처리: 에이전트가 실패해도 그래프는 끝까지 간다
# ---------------------------------------------------------------------------


def test_error_resilience() -> None:
    section("오류 처리: 전 노드 실패 시에도 그래프 완주")

    from graph.state import initial_state
    from graph.workflow import build_graph
    from utils.llm import StructuredOutputError

    def always_fail(*args, **kwargs):
        raise StructuredOutputError("의도적으로 발생시킨 테스트 실패")

    targets = [
        "agents.moderator.structured_invoke",
        "agents.debater.structured_invoke",
        "agents.critic.structured_invoke",
        "agents.final_moderator.structured_invoke",
    ]
    patches = [patch(t, always_fail) for t in targets]
    for p in patches:
        p.start()
    try:
        state = build_graph().compile().invoke(initial_state("테스트 질문입니다"))
    finally:
        for p in patches:
            p.stop()

    expected_errors = 2 + 2 * len(config.SIDE_IDS)
    check("그래프가 끝까지 실행됨", state is not None)
    check(
        "모든 노드 실패가 기록됨",
        len(state.get("errors", [])) == expected_errors,
        f"actual={len(state.get('errors', []))}, expected={expected_errors}",
    )
    check("양측 논증 폴백 생성", set(state.get("arguments", {})) == set(config.SIDE_IDS))
    check("양측 검증 폴백 생성", set(state.get("critiques", {})) == set(config.SIDE_IDS))

    check(
        "판정 실패 시 승자를 지어내지 않음",
        state.get("judgment") is None,
        "판정 에이전트가 실패했는데 승자가 만들어졌음",
    )


def test_forced_verdict_and_margin() -> None:
    section("승자 강제와 격차 표현")

    from agents.final_moderator import _normalize, _score_leader
    from models.schemas import MARGIN_BANDS, ComparisonRow, FinalJudgment, SideAnalysis

    def make_judgment(**overrides) -> FinalJudgment:
        payload = dict(
            question_type="SUBJECTIVE",
            reasoning_for_verdict="분석",
            verdict="PRO",
            margin_level="NARROW",
            margin_score=55,
            margin_reason="근소한 차이",
            confidence=0.6,
            headline="요약",
            side_analyses=[
                SideAnalysis(side=s, core_logic="논리", strengths=[], weaknesses=[])
                for s in ("PRO", "CON")
            ],
            comparison=[],
            limitations=["한계"],
            reframing_suggestions=[],
        )
        payload.update(overrides)
        return FinalJudgment(**payload)

    # 스키마가 무승부를 아예 허용하지 않는가
    import pydantic

    for bad in ("DRAW", "UNDECIDED", "TIE"):
        try:
            make_judgment(verdict=bad)
            rejected = False
        except pydantic.ValidationError:
            rejected = True
        check(f"스키마가 verdict={bad} 를 거부", rejected)

    # 모델이 어떻게든 이상한 값을 냈을 때도 승자는 나와야 한다
    j = make_judgment()
    j.verdict = "DRAW"  # type: ignore[assignment]
    normalized = _normalize(j, fallback_side="CON")
    check("잘못된 verdict 는 대체 승자로 보정", normalized.verdict == "CON")
    check("보정된 verdict 도 진영 ID", normalized.verdict in config.SIDE_IDS)

    # 대체 승자는 임의가 아니라 검증 점수 합계 기준
    high = make_critique("PRO")
    high.scores.logical_consistency = 10
    high.scores.evidence_quality = 10
    low = make_critique("CON")
    low.scores.logical_consistency = 1
    low.scores.evidence_quality = 1
    check("대체 승자는 점수 합계가 높은 쪽", _score_leader({"PRO": high, "CON": low}) == "PRO")
    check("반대 경우도 동일", _score_leader({"PRO": low, "CON": high}) == "CON")
    check("검증 결과가 없어도 승자 반환", _score_leader({}) in config.SIDE_IDS)

    # 등급과 수치가 어긋나면 등급 기준으로 보정
    for level, (low_bound, high_bound) in MARGIN_BANDS.items():
        over = _normalize(make_judgment(margin_level=level, margin_score=99), "PRO")
        under = _normalize(make_judgment(margin_level=level, margin_score=0), "PRO")
        check(
            f"{level} 격차 상한 보정",
            over.margin_score == high_bound,
            f"actual={over.margin_score}, expected={high_bound}",
        )
        check(
            f"{level} 격차 하한 보정",
            under.margin_score == low_bound,
            f"actual={under.margin_score}, expected={low_bound}",
        )

    check(
        "모든 격차 수치가 50 초과 (승자가 항상 우세)",
        all(low > 50 for low, _ in MARGIN_BANDS.values()),
    )

    # confidence 범위 보정
    check("confidence 상한", _normalize(make_judgment(confidence=9.9), "PRO").confidence == 1.0)
    check("confidence 하한", _normalize(make_judgment(confidence=-3.0), "PRO").confidence == 0.0)


def test_prompt_forbids_draw() -> None:
    section("판정 프롬프트가 무승부를 금지하는가")

    from prompts import final_moderator as final_prompt

    issue = make_issue()
    arguments = {s: make_argument(s, SECRET[s]) for s in ("PRO", "CON")}
    critiques = {s: make_critique(s) for s in ("PRO", "CON")}

    check("시스템 프롬프트가 무승부 금지를 명시", "무승부와 판단 유보는 허용되지 않는다" in final_prompt.SYSTEM)
    check("시스템 프롬프트에 격차 등급 기준 포함", "OVERWHELMING" in final_prompt.SYSTEM)
    check(
        "근소한 승부를 부풀리지 말라는 지시 포함",
        "부풀리는" in final_prompt.SYSTEM,
    )

    for question_type in ("OBJECTIVE", "SUBJECTIVE", "MIXED", "NORMATIVE"):
        issue.question_type = question_type  # type: ignore[assignment]
        text = final_prompt.build_user_prompt(
            "질문", issue, arguments, critiques, ["PRO", "CON"]
        )
        check(f"{question_type} 지침에 DRAW 없음", "DRAW" not in text)
        check(f"{question_type} 지침에 UNDECIDED 없음", "UNDECIDED" not in text)
        check(f"{question_type} 에서 승자 강제 문구 존재", "반드시 한 쪽을 고르라" in text)


def test_side_id_humanization() -> None:
    section("서술문 속 진영 ID 를 표시 라벨로 보정")

    from utils.text import humanize_sides

    # 기본 라벨 (찬반형 질문)
    cases = [
        ("PRO는 근거를 제시했다", "찬성은 근거를 제시했다"),
        ("CON의 논거가 약하다", "반대의 논거가 약하다"),
        ("PRO, CON 모두 부족하다", "찬성, 반대 모두 부족하다"),
        ("(PRO) 우세", "(찬성) 우세"),
    ]
    for raw, expected in cases:
        check(f"기본 라벨: {raw!r}", humanize_sides(raw) == expected, humanize_sides(raw))

    # 동적 라벨 (선택지 비교형 질문) + 한국어 조사 보정
    food = {"PRO": "청년피자", "CON": "처갓집 치킨"}
    dynamic = [
        ("PRO는 가성비가 좋다", "청년피자는 가성비가 좋다"),
        ("CON는 양이 많다", "처갓집 치킨은 양이 많다"),
        ("PRO가 우세하다", "청년피자가 우세하다"),
        ("CON가 밀렸다", "처갓집 치킨이 밀렸다"),
        ("PRO를 선택했다", "청년피자를 선택했다"),
    ]
    for raw, expected in dynamic:
        got = humanize_sides(raw, food)
        check(f"동적 라벨: {raw!r}", got == expected, got)

    # 라벨 끝이 한글이 아니면 조사를 건드리지 않는다
    check(
        "영문 라벨은 조사 유지",
        humanize_sides("PRO는 빠르다", {"PRO": "SSD", "CON": "HDD"}) == "SSD는 빠르다",
    )

    # 영문 단어 내부의 우연한 일치는 건드리지 않아야 한다
    for untouched in ("PROFIT", "PROCESS", "CONTEXT", "CONTROL", "APPROACH"):
        check(f"영문 단어 {untouched} 는 그대로", humanize_sides(untouched) == untouched)

    # 노드 이름 같은 식별자도 보존해야 한다 (오류 메시지에 등장)
    for identifier in ("debate_CON", "critic_PRO", "debate_PRO 실패"):
        expected = identifier
        check(
            f"식별자 {identifier!r} 보존",
            humanize_sides(identifier) == expected,
            humanize_sides(identifier),
        )

    check("빈 문자열 안전", humanize_sides("") == "")


def test_dynamic_side_labels() -> None:
    section("질문에 맞는 진영 라벨")

    from agents.moderator import MAX_LABEL_LENGTH, _clean_label, _normalize
    from models.schemas import IssueAnalysis, PositionSpec
    from utils.text import default_labels, resolve_labels

    # 라벨 정리
    check("빈 라벨은 기본값", _clean_label("", "찬성") == "찬성")
    check("공백만 있으면 기본값", _clean_label("   ", "반대") == "반대")
    check("'측' 꼬리말 제거", _clean_label("청년피자 측", "찬성") == "청년피자")
    check("'진영' 꼬리말 제거", _clean_label("처갓집 치킨 진영", "반대") == "처갓집 치킨")
    check("공백 없는 '측' 제거", _clean_label("찬성측", "찬성") == "찬성")
    check(
        "긴 라벨은 잘림",
        len(_clean_label("가" * 40, "찬성")) == MAX_LABEL_LENGTH,
        _clean_label("가" * 40, "찬성"),
    )
    check("정상 라벨 보존", _clean_label("청년피자", "찬성") == "청년피자")

    def build(labels):
        return IssueAnalysis(
            issue="쟁점",
            question_type="SUBJECTIVE",
            question_type_reason="r",
            positions=[
                PositionSpec(side=sid, label=lab, statement="입장")
                for sid, lab in labels
            ],
            criteria=[],
            ambiguities=[],
            interpretation="해석",
        )

    # 정상 케이스
    normalized = _normalize(build([("PRO", "청년피자"), ("CON", "처갓집 치킨")]))
    labels = resolve_labels(normalized)
    check("선택지 라벨 유지", labels == {"PRO": "청년피자", "CON": "처갓집 치킨"}, str(labels))

    # 라벨이 겹치면 구분이 안 되므로 기본 라벨로 되돌린다
    dup = _normalize(build([("PRO", "피자"), ("CON", "피자")]))
    check(
        "중복 라벨은 기본값으로 복구",
        resolve_labels(dup) == default_labels(),
        str(resolve_labels(dup)),
    )

    # 라벨이 비면 기본값
    empty = _normalize(build([("PRO", ""), ("CON", "")]))
    check("빈 라벨은 기본값으로", resolve_labels(empty) == default_labels())

    # 진영이 누락되어도 채워진다
    partial = _normalize(build([("PRO", "SSD")]))
    resolved = resolve_labels(partial)
    check("누락 진영 라벨 보충", set(resolved) == set(config.SIDE_IDS), str(resolved))
    check("있는 라벨은 유지", resolved["PRO"] == "SSD")

    # 분석이 없으면 기본 라벨
    check("issue 가 None 이면 기본 라벨", resolve_labels(None) == default_labels())


def test_css_gauges() -> None:
    """게이지 막대 회귀 테스트.

    .score-fill 은 <span> 이고 부모 .score-track 이 flex 컨테이너가 아니다.
    span 은 기본이 inline 이라 display:block 이 없으면 width/height 가 무시되어
    막대가 전혀 차오르지 않는다. 실제로 발생했던 버그라 규칙을 고정해 둔다.
    """
    section("게이지 막대 CSS")

    import re

    from ui import styles

    css = styles.inject()

    def rule_body(selector: str) -> str:
        match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
        return match.group(1) if match else ""

    fill = rule_body(".score-fill")
    check(".score-fill 규칙 존재", bool(fill))
    check(
        ".score-fill 에 display:block (막대가 차오르려면 필수)",
        "display: block" in fill or "display:block" in fill,
        fill.strip(),
    )
    check(".score-fill 에 height 지정", "height" in fill)

    track = rule_body(".score-track")
    check(".score-track 에 overflow:hidden (둥근 끝 처리)", "overflow: hidden" in track)

    # 진영 라벨이 길어져도 잘리지 않고 줄임표로 처리되어야 한다
    tag = rule_body(".score-tag")
    check(".score-tag 가 긴 라벨을 줄임표 처리", "text-overflow" in tag, tag.strip())

    # margin/conf 게이지는 div 라 블록이지만, 폭 계산 규칙은 있어야 한다
    check(".margin-fill 에 height", "height" in rule_body(".margin-fill"))
    check(".conf-fill 에 height", "height" in rule_body(".conf-fill"))

    # CSS 에 미치환 토큰이 남지 않아야 한다
    check("CSS 토큰 치환 완료", "__PRO_COLOR__" not in css and "__CON_COLOR__" not in css)


def test_input_validation() -> None:
    section("입력 검증")

    check("빈 질문 거부", config.validate_question("") is not None)
    check("공백만 거부", config.validate_question("   ") is not None)
    check("1자 거부", config.validate_question("가") is not None)
    check(
        f"{config.MAX_QUESTION_LENGTH + 1}자 거부",
        config.validate_question("가" * (config.MAX_QUESTION_LENGTH + 1)) is not None,
    )
    check("정상 질문 통과", config.validate_question("재택근무가 생산적인가?") is None)


# ---------------------------------------------------------------------------
# 6. UI 렌더링 (합성 상태 -> API 호출 없음)
# ---------------------------------------------------------------------------


def test_ui_rendering() -> None:
    section("UI 렌더링 (Streamlit AppTest)")

    from streamlit.testing.v1 import AppTest

    from models.schemas import ComparisonRow, FinalJudgment, SideAnalysis, SideAssessment

    def make_state(question: str, labels: dict[str, str] | None = None) -> dict:
        return {
        "question": question,
        "issue": make_issue(labels),
        "arguments": {s: make_argument(s, SECRET[s]) for s in ("PRO", "CON")},
        "critiques": {s: make_critique(s) for s in ("PRO", "CON")},
        "judgment": FinalJudgment(
            question_type="MIXED",
            # LLM 이 서술문에 원시 진영 ID 를 쓰는 상황을 재현한다.
            # 화면에는 표시 라벨로 보정되어 나와야 한다.
            reasoning_for_verdict="PRO는 전제를 드러냈고 CON의 논거는 일반화에 그쳤다",
            verdict="PRO",
            margin_level="CLEAR",
            margin_score=63,
            margin_reason="상대의 핵심 논거는 전제가 성립하지 않았다",
            confidence=0.7,
            headline="전제를 더 정직하게 드러낸 쪽이 앞섰다",
            side_analyses=[
                SideAnalysis(
                    side=s,
                    core_logic=f"{SECRET[s]} 를 축으로 한 핵심 논리",
                    strengths=["강점"],
                    weaknesses=["약점"],
                )
                for s in ("PRO", "CON")
            ],
            comparison=[
                ComparisonRow(
                    criterion="논리성",
                    assessments=[
                        SideAssessment(side="PRO", score=7, comment="코멘트"),
                        SideAssessment(side="CON", score=8, comment="코멘트"),
                    ],
                    note="비교 설명",
                )
            ],
            limitations=["이 판단의 한계"],
            reframing_suggestions=["이렇게 바꿔보세요"],
        ),
        "errors": [],
        "timeline": [],
        }

    state = make_state("재택근무가 사무실 출근보다 생산적인가?")
    app_path = str(PROJECT_ROOT / "app.py")

    # 입력 화면
    at = AppTest.from_file(app_path, default_timeout=60).run()
    check("입력 화면 예외 없음", not at.exception, str(at.exception))
    check("입력창 1개", len(at.text_area) == 1)
    check("분석 시작 버튼", any("분석 시작" in b.label for b in at.button))
    check("예시 질문 버튼", sum(1 for b in at.button if b.key and b.key.startswith("example_")) >= 3)

    # 빈 질문 제출
    submit = next(b for b in at.button if "분석 시작" in b.label)
    submit.click().run()
    check("빈 질문 제출 시 오류", len(at.error) > 0)
    check("빈 질문 시 실행 안 함", at.session_state["phase"] == "input")

    # 예시 질문 클릭이 입력창에 반영되는가
    at2 = AppTest.from_file(app_path, default_timeout=60).run()
    example = next(b for b in at2.button if b.key == "example_0")
    label = example.label
    example.click().run()
    check("예시 클릭이 입력창에 반영됨", at2.session_state["question_text"] == label)

    # 결과 화면
    at3 = AppTest.from_file(app_path, default_timeout=120)
    at3.session_state["phase"] = "result"
    at3.session_state["result"] = state
    at3.run()

    check("결과 화면 예외 없음", not at3.exception, str(at3.exception))
    # 주입된 <style> 블록은 사용자에게 보이지 않으므로 표시 내용 검사에서 제외한다.
    body = " ".join(m.value for m in at3.markdown if "<style>" not in m.value)
    for label, needle in [
        ("질문 표시", state["question"]),
        ("FINAL VERDICT 카드", "Final Verdict"),
        ("승자를 찬성/반대로 표기", "찬성 측 승리"),
        ("격차 등급 배지", "우세승"),
        ("격차 게이지", "우세 격차"),
        ("격차 사유", state["judgment"].margin_reason),
        ("신뢰도 표시", "판정 신뢰도"),
        ("찬성 측 카드", "찬성 측"),
        ("반대 측 카드", "반대 측"),
        ("찬성 논증 본문", SECRET["PRO"]),
        ("반대 논증 본문", SECRET["CON"]),
        ("점수 비교", "검증 점수 비교"),
        ("점수 합계 표시", "/ 70"),
        ("점수 면책 문구", "객관적 측정값이 아니며"),
        ("판정 근거 섹션", "왜 이 결론에 이르렀는가"),
        ("한계 섹션", "다만 이 판단에도 한계가 있습니다"),
        ("기준별 비교", "기준별 비교"),
        ("서술문 속 진영 ID 가 라벨로 보정됨", "찬성은 전제를 드러냈고"),
    ]:
        check(label, needle in body)

    # 내부 진영 ID 는 상태 키로만 쓰이고 화면에는 표시 라벨만 나와야 한다.
    check("결과 화면에 원시 ID 'PRO' 노출 없음", "PRO" not in body, "내부 ID 가 UI 에 노출됨")
    check("결과 화면에 원시 ID 'CON' 노출 없음", "CON" not in body)

    # --- 선택지 비교형 질문: 라벨이 실제 선택지 이름으로 바뀌는가 -------------
    food_state = make_state(
        "청년피자와 처갓집 슈프림양념치킨 중 저녁으로 뭐가 나을까?",
        {"PRO": "청년피자", "CON": "처갓집 치킨"},
    )
    at4 = AppTest.from_file(app_path, default_timeout=120)
    at4.session_state["phase"] = "result"
    at4.session_state["result"] = food_state
    at4.run()

    check("선택지 비교 결과 화면 예외 없음", not at4.exception, str(at4.exception))
    food_body = " ".join(m.value for m in at4.markdown if "<style>" not in m.value)

    check("승자를 선택지 이름으로 표기", "청년피자 승리" in food_body)
    check("패자 라벨도 선택지 이름", "처갓집 치킨" in food_body)
    check("고유 라벨에는 '측'을 붙이지 않음", "청년피자 측" not in food_body)
    check(
        "찬성/반대 표기가 사라짐",
        "찬성" not in food_body and "반대" not in food_body,
        "선택지 비교 질문인데 찬성/반대가 남아 있음",
    )
    check("서술문도 선택지 이름으로 보정", "청년피자는 전제를 드러냈고" in food_body)
    check("승자의 입장 문장 표시", "verdict-position" in food_body)
    check("검증 익스팬더 라벨도 선택지 이름", any("청년피자" in e.label for e in at4.expander))
    check("무승부 표기 없음", "무승부" not in body and "판단 유보" not in body)

    check("검증 결과 익스팬더 2개", len(at3.expander) == 2, f"actual={len(at3.expander)}")
    check("새 질문 버튼", any("새로운 질문" in b.label for b in at3.button))

    next(b for b in at3.button if "새로운 질문" in b.label).click().run()
    check("새 질문 클릭 시 입력 화면 복귀", at3.session_state["phase"] == "input")
    check("결과 초기화", at3.session_state["result"] is None)


# ---------------------------------------------------------------------------


def main() -> int:
    from utils.logging import setup_logging

    setup_logging("CRITICAL")

    test_information_isolation()
    test_final_moderator_sees_both()
    test_bias_guards()
    test_extensibility()
    test_graph_topology()
    test_error_resilience()
    test_forced_verdict_and_margin()
    test_prompt_forbids_draw()
    test_side_id_humanization()
    test_dynamic_side_labels()
    test_css_gauges()
    test_input_validation()
    test_ui_rendering()

    print()
    if _failures:
        print(f"✖ 실패 {len(_failures)}건: {_failures}")
        return 1
    print("✓ 모든 테스트 통과 (LLM 호출 없음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
