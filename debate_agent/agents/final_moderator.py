"""최종 판정 노드.

편향 방지 조치:
  - 진영 제시 순서를 매 실행마다 무작위로 섞어 위치 편향을 제거한다.
  - 판정 결과의 진영 ID 를 레지스트리 기준으로 정규화한다(모델이 없는 진영을 만들어내는 경우 방어).
  - 점수는 참고 지표로만 프롬프트에 들어가고, 판정 스키마에는 총점 필드가 없다.
"""

from __future__ import annotations

import random
from typing import Any

import config
from agents.base import is_known_side, normalize_side, safe_node
from graph.state import DebateState
from models.schemas import MARGIN_BANDS, Critique, FinalJudgment, SideAnalysis
from prompts import final_moderator as prompt
from utils.llm import clamp_score, structured_invoke

NODE_NAME = "final_moderator"

VALID_VERDICTS = set(config.SIDE_IDS)


def _fallback(state: DebateState, exc: Exception) -> dict[str, Any]:
    """판정 에이전트가 실패한 경우.

    승자를 지어내지 않는다. 판정 없이 양측 논증과 검증 결과만 보여주고,
    결과 화면이 실패 사실을 명시하도록 judgment 를 비워 둔다.
    없는 근거로 승패를 만들어내는 것은 이 시스템이 하지 말아야 할 일이다.
    """
    return {"judgment": None}


def _score_leader(critiques: dict[str, Critique]) -> str:
    """검증 점수 합계가 가장 높은 진영. verdict 파싱 실패 시의 결정적 대체값."""
    best = config.SIDE_IDS[0]
    best_total = -1
    for side_id in config.SIDE_IDS:
        critique = critiques.get(side_id)
        total = critique.scores.total() if critique else -1
        if total > best_total:
            best, best_total = side_id, total
    return best


def _normalize(judgment: FinalJudgment, fallback_side: str) -> FinalJudgment:
    verdict = (judgment.verdict or "").strip().upper()
    if verdict not in VALID_VERDICTS:
        # 모델이 DRAW 같은 값을 내놓은 경우에도 승자는 나와야 한다.
        # 임의로 고르지 않고 검증 점수 합계가 높은 쪽으로 결정한다.
        verdict = fallback_side
    judgment.verdict = verdict  # type: ignore[assignment]

    judgment.confidence = max(0.0, min(1.0, float(judgment.confidence or 0.0)))

    # 격차 등급과 수치가 어긋나면 등급 쪽을 기준으로 수치를 보정한다.
    low, high = MARGIN_BANDS.get(judgment.margin_level, MARGIN_BANDS["NARROW"])
    judgment.margin_score = max(low, min(high, int(judgment.margin_score or low)))

    # 진영별 분석: ID 보정 + 진영당 1개로 정리 + 누락 진영 채우기
    analyses: dict[str, SideAnalysis] = {}
    for index, analysis in enumerate(judgment.side_analyses):
        default_id = config.SIDE_IDS[min(index, len(config.SIDE_IDS) - 1)]
        analysis.side = normalize_side(analysis.side, default_id)
        analyses.setdefault(analysis.side, analysis)
    for side in config.SIDES:
        if side.id not in analyses:
            analyses[side.id] = SideAnalysis(
                side=side.id,
                core_logic="(사회자가 이 진영에 대한 분석을 생성하지 않았습니다.)",
                strengths=[],
                weaknesses=[],
            )
    judgment.side_analyses = [analyses[s.id] for s in config.SIDES]

    # 비교표: 알 수 없는 진영(예: 모델이 지어낸 "NOTE")은 버리고 점수를 보정
    for row in judgment.comparison:
        kept = []
        for assessment in row.assessments:
            if not is_known_side(assessment.side):
                continue
            assessment.side = assessment.side.strip().upper()
            assessment.score = clamp_score(assessment.score)
            kept.append(assessment)
        row.assessments = kept
    judgment.comparison = [row for row in judgment.comparison if row.assessments]

    return judgment


@safe_node(NODE_NAME, fallback=_fallback)
def final_moderator_node(state: DebateState) -> dict[str, Any]:
    issue = state["issue"]
    if issue is None:
        raise RuntimeError("쟁점 분석 결과가 없어 판정할 수 없습니다.")

    # 위치 편향 제거: 진영 제시 순서를 매번 무작위로 섞는다.
    side_order = list(config.SIDE_IDS)
    random.shuffle(side_order)

    critiques = state.get("critiques", {})
    judgment = structured_invoke(
        FinalJudgment,
        prompt.SYSTEM,
        prompt.build_user_prompt(
            question=state["question"],
            issue=issue,
            arguments=state.get("arguments", {}),
            critiques=critiques,
            side_order=side_order,
        ),
        model=config.get_judge_model_name(),
        label=NODE_NAME,
    )
    return {"judgment": _normalize(judgment, _score_leader(critiques))}
