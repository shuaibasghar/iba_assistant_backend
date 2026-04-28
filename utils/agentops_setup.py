"""
AgentOps (https://agentops.ai) — traces, costs, and sessions for CrewAI / LangChain.

No-op when AGENTOPS_API_KEY and Settings.agentops_api_key are both unset.
Call init_agentops() once per process before LLM/agent frameworks are used.
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)
_initialized: bool = False


def init_agentops() -> None:
    """Idempotent process-wide setup; safe to call from FastAPI, chat_service, or scripts."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    try:
        import agentops
    except ImportError:
        _log.debug("agentops package not installed; skipping AgentOps")
        return

    from config import get_settings

    s = get_settings()
    key = (
        (getattr(s, "agentops_api_key", None) or "").strip()
        or os.environ.get("AGENTOPS_API_KEY", "").strip()
    )
    if not key:
        return

    os.environ.setdefault("AGENTOPS_API_KEY", key)
    try:
        if getattr(s, "agentops_skip_auto_end_session", False):
            try:
                agentops.init(skip_auto_end_session=True)
            except TypeError:
                agentops.init()
        else:
            agentops.init()
        _log.info("AgentOps initialized (agent tracing enabled)")
    except Exception as exc:
        _log.warning("AgentOps init failed: %s", exc)
