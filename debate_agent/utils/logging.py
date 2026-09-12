"""로깅 설정.

노드 시작/종료 시각을 남겨 PRO/CON 브랜치가 실제로 병렬 실행되는지 확인할 수 있게 한다.
"""

from __future__ import annotations

import logging
import os
import sys

_configured = False


def setup_logging(level: str | None = None) -> None:
    global _configured
    if _configured:
        return

    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)-22s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger("debate")
    root.setLevel(log_level)
    root.addHandler(handler)
    root.propagate = False

    # 의존 라이브러리의 수다스러운 로그는 억제
    for noisy in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"debate.{name}")
