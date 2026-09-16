"""Locally-registered terminal agents beyond the built-in Claude/Codex CLIs.

A user who already runs their own coding agent from their own terminal (a
personal script, another CLI) can register it once here and then pick it in
the Design tab's engine selector just like Claude or Codex. The command is
whatever they typed in when registering it -- it's run through the shell
with the prompt piped over stdin and the strategy's own record directory as
cwd, the same invocation shape design_agent.py already uses for Codex.

Registered agents persist in a small YAML file under ~/.algoterminal/ so they
survive restarts.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from algoterminal.config import HOME_DIR

_CUSTOM_AGENTS_PATH = HOME_DIR / "custom_agents.yaml"


@dataclass(frozen=True)
class CustomAgent:
    name: str
    command: str


def list_custom_agents() -> list[CustomAgent]:
    if not _CUSTOM_AGENTS_PATH.exists():
        return []
    data = yaml.safe_load(_CUSTOM_AGENTS_PATH.read_text(encoding="utf-8")) or []
    return [CustomAgent(name=d["name"], command=d["command"]) for d in data]


def add_custom_agent(agent: CustomAgent) -> None:
    agents = [a for a in list_custom_agents() if a.name != agent.name]
    agents.append(agent)
    _save(agents)


def remove_custom_agent(name: str) -> None:
    _save([a for a in list_custom_agents() if a.name != name])


def _save(agents: list[CustomAgent]) -> None:
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    payload = [{"name": a.name, "command": a.command} for a in agents]
    _CUSTOM_AGENTS_PATH.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
