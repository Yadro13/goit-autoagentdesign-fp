"""Потокобезпечний JSON trajectory logger для всіх агентів MAS."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TrajectoryEvent:
    timestamp: str
    run_id: str
    agent_name: str
    node: str
    step: int
    duration_ms: float
    input: dict[str, Any]
    output: dict[str, Any]


class TrajectoryLogger:
    """Append-only logger, який не зберігає secrets або очевидну PII."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._events: list[TrajectoryEvent] = []
        if self.path.exists():
            try:
                for item in json.loads(self.path.read_text(encoding="utf-8")):
                    self._events.append(TrajectoryEvent(**item))
            except (ValueError, TypeError, OSError):
                self._events = []

    def log(
        self,
        *,
        run_id: str,
        agent_name: str,
        node: str,
        step: int,
        duration_ms: float,
        input: dict[str, Any],
        output: dict[str, Any],
    ) -> dict[str, Any]:
        event = TrajectoryEvent(
            timestamp=datetime.now(UTC).isoformat(),
            run_id=run_id,
            agent_name=agent_name,
            node=node,
            step=step,
            duration_ms=round(duration_ms, 3),
            input=_redact(input),
            output=_redact(output),
        )
        with self._lock:
            self._events.append(event)
            self.path.write_text(
                json.dumps([asdict(x) for x in self._events], ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return asdict(event)

    @property
    def events(self) -> list[TrajectoryEvent]:
        return list(self._events)

    def reset(self) -> None:
        """Clear only this generated standalone trajectory artifact."""

        with self._lock:
            self._events = []
            self.path.write_text("[]\n", encoding="utf-8")


SECRET_RE = re.compile(r"\b(?:sk-|AIza|lsv2_pt_)[A-Za-z0-9_-]{8,}")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(
                marker in key.casefold()
                for marker in ("token", "secret", "password", "api_key", "phone", "email")
            )
            else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_RE.sub("[SECRET_REDACTED]", value)
    return value
