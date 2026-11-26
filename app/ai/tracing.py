"""LangSmith observability for HealthGPT.

LangGraph reports every graph run and node to LangSmith by itself once the
environment variables below are set. This module adds the pieces LangGraph
cannot see:

* ``traceable``      - a safe decorator (a no-op when LangSmith is missing/off)
* ``annotate_run``   - attach extra metadata to the run that is executing now
* ``graph_run_config`` - names, tags and metadata for one chat request, so runs
  can be filtered by intent (``intent:daily_nutrition``) and grouped into
  conversations (``thread_id``)

Tracing is OFF unless you opt in:

    LANGSMITH_TRACING=true
    LANGSMITH_API_KEY=...
    LANGSMITH_PROJECT=healthgpt          # optional, this is the default

Privacy: traces contain chat messages and meal data. Set
``LANGSMITH_HIDE_INPUTS=true`` and ``LANGSMITH_HIDE_OUTPUTS=true`` to upload
only run structure, timing, token counts and errors. User ids are never sent
raw; they are replaced by a short one-way hash.
"""

import hashlib
import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)

try:  # langsmith ships with langchain-core, but never let it break the API
    from langsmith import traceable as _langsmith_traceable
except Exception:  # pragma: no cover - depends on the environment
    _langsmith_traceable = None

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _api_key() -> str | None:
    return os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")


def tracing_requested() -> bool:
    """True when the environment asks for tracing (new or legacy variable)."""
    return _flag("LANGSMITH_TRACING") or _flag("LANGCHAIN_TRACING_V2")


def tracing_enabled() -> bool:
    """True when traces will really be sent to LangSmith."""
    return (
        _langsmith_traceable is not None
        and tracing_requested()
        and bool(_api_key())
    )


def _disable_tracing() -> None:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"


def configure_tracing() -> bool:
    """Call once at start-up. Returns True when tracing is active.

    A half-configured setup (tracing requested but no API key) is switched off
    here, otherwise every chat request would log authentication errors.
    """
    os.environ.setdefault("LANGSMITH_PROJECT", "healthgpt")

    if not tracing_requested():
        logger.info("LangSmith tracing is off (set LANGSMITH_TRACING=true).")
        return False

    if _langsmith_traceable is None:
        logger.warning(
            "LANGSMITH_TRACING is set but the langsmith package is not "
            "installed. Tracing is disabled."
        )
        _disable_tracing()
        return False

    if not _api_key():
        logger.warning(
            "LANGSMITH_TRACING is set but LANGSMITH_API_KEY is missing. "
            "Tracing is disabled."
        )
        _disable_tracing()
        return False

    logger.info(
        "LangSmith tracing enabled (project=%s).",
        os.getenv("LANGSMITH_PROJECT"),
    )
    return True


def traceable(**kwargs: Any) -> Callable[[Callable], Callable]:
    """``langsmith.traceable`` that degrades to a plain pass-through.

    Always call it with keyword arguments:
    ``@traceable(name="x", run_type="llm")``.
    """
    if _langsmith_traceable is None:

        def passthrough(function: Callable) -> Callable:
            return function

        return passthrough

    return _langsmith_traceable(**kwargs)


def annotate_run(metadata: dict[str, Any]) -> None:
    """Add metadata to the run currently executing. Never raises."""
    if _langsmith_traceable is None:
        return

    try:
        from langsmith.run_helpers import get_current_run_tree

        run = get_current_run_tree()

        if run is not None:
            run.add_metadata(metadata)
    except Exception:
        logger.debug("Could not annotate LangSmith run", exc_info=True)


def anonymous_id(user_id: Any) -> str:
    """Stable, non-reversible id so traces never contain a raw user id."""
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]


def graph_run_config(
    *,
    user_id: Any,
    thread_id: Any = None,
    intent: str | None = None,
    streaming: bool = False,
) -> dict[str, Any]:
    """Run name, tags and metadata for one chat request (LangGraph config)."""
    tags = ["healthgpt", f"env:{os.getenv('APP_ENV', 'development')}"]
    metadata: dict[str, Any] = {
        "user_hash": anonymous_id(user_id),
        "streaming": streaming,
    }

    if intent:
        tags.append(f"intent:{intent}")
        # "path:sql" means the question was answered without calling an LLM.
        tags.append("path:llm" if intent == "llm" else "path:sql")
        metadata["intent"] = intent

    if thread_id is not None:
        # LangSmith groups runs that share "thread_id" into one conversation.
        metadata["thread_id"] = str(thread_id)

    return {
        "run_name": "healthgpt_chat",
        "tags": tags,
        "metadata": metadata,
    }
