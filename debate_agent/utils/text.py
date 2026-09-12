"""표시용 텍스트 정리.

진영 ID(PRO/CON)는 상태 키와 스키마의 side 필드에서만 쓰이는 내부 식별자다.
화면에는 사회자가 질문에 맞춰 붙인 표시 라벨을 쓴다.
  - "대학 등록금은 낮춰야 하는가?"        -> 찬성 / 반대
  - "청년피자와 처갓집 치킨 중 뭐가 나을까?" -> 청년피자 / 처갓집 치킨

LLM 이 서술문 안에서 "PRO는 ...", "CON의 논거" 처럼 내부 ID 를 그대로 쓰는 경우가 있어,
프롬프트로 막는 것과 별개로 표시 직전에 한 번 더 보정한다.
"""

from __future__ import annotations

import re
from typing import Any

import config

#: 서술문 안의 진영 ID 와, 바로 뒤에 붙은 조사를 함께 잡는다.
#: - 한글 조사가 붙은 "PRO는", "CON의" 도 매칭되도록 \b 대신 전후방 탐색을 쓴다.
#: - 영문자 인접은 제외해 PROFIT, CONTEXT 같은 단어를 건드리지 않는다.
#: - 언더스코어 인접도 제외해 debate_CON, critic_PRO 같은 식별자를 보존한다.
_SIDE_ID_PATTERN = re.compile(
    r"(?<![A-Za-z_])("
    + "|".join(re.escape(s.id) for s in config.SIDES)
    + r")(?![A-Za-z_])([은는이가을를과와])?"
)

#: 받침 유무에 따라 형태가 달라지는 조사 (받침 있음, 받침 없음)
_PARTICLE_PAIRS: dict[str, tuple[str, str]] = {
    "은": ("은", "는"),
    "는": ("은", "는"),
    "이": ("이", "가"),
    "가": ("이", "가"),
    "을": ("을", "를"),
    "를": ("을", "를"),
    "과": ("과", "와"),
    "와": ("과", "와"),
}


def _fix_particle(label: str, particle: str | None) -> str:
    """치환된 라벨에 맞게 한국어 조사를 고른다.

    'PRO는' -> '찬성은', 'PRO는' -> '청년피자는' 처럼 받침에 따라 형태가 달라진다.
    라벨 끝이 한글이 아니면(예: SSD) 판별할 수 없으므로 원래 조사를 그대로 둔다.
    """
    if not particle:
        return ""
    pair = _PARTICLE_PAIRS.get(particle)
    if not pair or not label:
        return particle or ""

    last = label[-1]
    if not ("가" <= last <= "힣"):
        return particle

    has_final = (ord(last) - 0xAC00) % 28 != 0
    return pair[0] if has_final else pair[1]


def default_labels() -> dict[str, str]:
    """사회자 분석이 없을 때 쓰는 기본 라벨 (찬성/반대)."""
    return {side.id: side.label for side in config.SIDES}


def resolve_labels(issue: Any | None) -> dict[str, str]:
    """IssueAnalysis 에서 진영별 표시 라벨을 뽑는다.

    사회자가 라벨을 만들지 못했거나 분석 자체가 없으면 기본 라벨로 대체한다.
    """
    labels = default_labels()
    positions = getattr(issue, "positions", None) or []
    for position in positions:
        side_id = getattr(position, "side", None)
        label = (getattr(position, "label", "") or "").strip()
        if side_id in labels and label:
            labels[side_id] = label
    return labels


def humanize_sides(text: str, labels: dict[str, str] | None = None) -> str:
    """서술문 속 진영 ID 를 표시 라벨로 바꾼다. ("PRO는" -> "청년피자는")"""
    if not text:
        return text

    resolved = labels or default_labels()

    def _replace(match: re.Match[str]) -> str:
        side_id, particle = match.group(1), match.group(2)
        label = resolved.get(side_id)
        if label is None:
            return match.group(0)
        return label + _fix_particle(label, particle)

    return _SIDE_ID_PATTERN.sub(_replace, text)
