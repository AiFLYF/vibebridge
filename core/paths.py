"""Path resolution for VibeBridge. Code and user data are kept strictly separate."""
import os
from pathlib import Path

ENV_VAR = "VIBEBRIDGE_HOME"


def home() -> Path:
    """User data root. Never inside the skill directory, so skill upgrades cannot destroy data."""
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".vibebridge"


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


LAYOUT = {
    "version":      "version.json",
    "config":       "config.json",
    "profile":      "profile.json",
    "observations": "memory/observations.jsonl",
    "candidates":   "memory/candidates.json",
    "verified":     "memory/verified.json",
    "conflicts":    "memory/conflicts.json",
    "strategies":   "memory/strategies.json",
    "sessions":     "sessions/index.json",
    "projects":     "projects/projects.json",
    "experiments":  "experiments/experiments.json",
    "milestones":   "milestones/milestones.json",
    "growth":       "growth/state.json",
    "analytics":    "analytics/analytics.json",
}

DIRS = [
    "memory", "sessions", "projects", "experiments", "milestones",
    "growth", "analytics", "reports", "reports/history", "backups", "logs",
    "exports",
]


def p(key: str) -> Path:
    return home() / LAYOUT[key]


def d(name: str) -> Path:
    return home() / name


def session_file(session_id: str, ts: str) -> Path:
    # sessions/YYYY/MM/session_id.json
    y, m = ts[0:4], ts[5:7]
    return home() / "sessions" / y / m / f"{session_id}.json"
