"""Безпечна конфігурація standalone reference implementation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime-параметри; secrets читаються лише з environment."""

    project_root: Path = PROJECT_ROOT
    openai_model: str = "gpt-5.4-mini"
    agent_db_path: Path = Path("agent_state.db")
    safeops_db_path: Path = Path("safeops.db")
    chroma_db_path: Path = Path("chroma_db")
    trajectory_path: Path = Path("trajectory.json")
    max_steps: int = 10
    timeout_seconds: float = 120.0
    repeat_limit: int = 3
    rate_limit_calls: int = 30
    rate_limit_window_seconds: int = 60

    @property
    def data_dir(self) -> Path:
        return self.project_root

    @property
    def checkpoint_path(self) -> Path:
        return self.agent_db_path

    @property
    def chroma_path(self) -> Path:
        return self.chroma_db_path

    @property
    def agent_timeout_sec(self) -> float:
        return self.timeout_seconds

    @property
    def rate_limit_window_sec(self) -> int:
        return self.rate_limit_window_seconds

    def ensure_directories(self) -> None:
        for path in (
            self.agent_db_path,
            self.safeops_db_path,
            self.chroma_db_path,
            self.trajectory_path,
        ):
            target = path if path.suffix == "" else path.parent
            target.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        local_env = PROJECT_ROOT / ".env.local"
        selected_env = env_file or (local_env if local_env.exists() else PROJECT_ROOT / ".env")
        load_dotenv(selected_env, override=False)
        root = PROJECT_ROOT
        return cls(
            project_root=root,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            agent_db_path=_resolve(root, os.getenv("AGENT_DB_PATH", "agent_state.db")),
            safeops_db_path=_resolve(root, os.getenv("SAFEOPS_DB_PATH", "safeops.db")),
            chroma_db_path=_resolve(root, os.getenv("CHROMA_DB_PATH", "chroma_db")),
            trajectory_path=_resolve(root, os.getenv("TRAJECTORY_PATH", "trajectory.json")),
            rate_limit_calls=int(os.getenv("RATE_LIMIT_CALLS", "30")),
            rate_limit_window_seconds=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
        )


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def get_settings() -> Settings:
    """Create settings lazily so tests can isolate paths through environment."""

    return Settings.from_env()
