"""
CrewAI built-in email path: CrewaiPlatformTools (CrewAI Plus Gmail / integrations).

Requires CrewAI Plus integration and CREWAI_PLATFORM_INTEGRATION_TOKEN.
See: https://docs.crewai.com/en/enterprise/integrations/gmail
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, ConfigDict

from config import get_settings


class EmptyEmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailNotConfiguredTool(BaseTool):
    name: str = "email_not_configured"
    description: str = (
        "Use when the student asks to send an email but the portal has no "
        "CrewAI Plus / Gmail integration configured. Returns a clear message."
    )
    args_schema: type[BaseModel] = EmptyEmailInput

    def _run(self, **_kwargs: Any) -> str:
        return (
            "Outbound email is not enabled: set CREWAI_PLATFORM_INTEGRATION_TOKEN "
            "and connect Gmail (or another supported app) in CrewAI Plus."
        )


@contextmanager
def _crewai_platform_token_env(token: str):
    key = "CREWAI_PLATFORM_INTEGRATION_TOKEN"
    previous = os.environ.get(key)
    os.environ[key] = token
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def get_platform_email_tools() -> list[Any]:
    """
    Return CrewAI platform tools for the configured apps (default: gmail),
    or a single stub tool if the integration token is not set.

    Each call may refetch action schemas from CrewAI Plus (network).
    """
    settings = get_settings()
    token = (settings.crewai_platform_integration_token or "").strip()
    if not token:
        return [EmailNotConfiguredTool()]

    apps = [
        a.strip()
        for a in (settings.crewai_email_apps or "gmail").split(",")
        if a.strip()
    ]
    if not apps:
        apps = ["gmail"]

    try:
        from crewai_tools import CrewaiPlatformTools
    except ImportError:
        return [EmailNotConfiguredTool()]

    try:
        with _crewai_platform_token_env(token):
            tools = CrewaiPlatformTools(apps=apps)
    except Exception:
        return [EmailNotConfiguredTool()]

    if not tools:
        return [EmailNotConfiguredTool()]
    return list(tools)
