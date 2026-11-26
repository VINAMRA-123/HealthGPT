"""Offline tests for the LangSmith helpers. Nothing is sent anywhere."""

import pytest

from app.ai import tracing

ENV_NAMES = (
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_API_KEY",
    "LANGCHAIN_API_KEY",
    "LANGSMITH_PROJECT",
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        # setenv then delenv registers the variable so it is restored later
        monkeypatch.setenv(name, "x")
        monkeypatch.delenv(name)

    return monkeypatch


def test_tracing_is_off_by_default_and_project_has_a_default(clean_env):
    assert tracing.configure_tracing() is False
    assert tracing.tracing_enabled() is False

    import os

    assert os.environ["LANGSMITH_PROJECT"] == "healthgpt"


def test_tracing_without_api_key_is_switched_off(clean_env):
    import os

    clean_env.setenv("LANGSMITH_TRACING", "true")

    assert tracing.configure_tracing() is False
    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert tracing.tracing_enabled() is False


def test_tracing_with_key_is_enabled(clean_env):
    pytest.importorskip("langsmith")

    clean_env.setenv("LANGSMITH_TRACING", "true")
    clean_env.setenv("LANGSMITH_API_KEY", "lsv2_test_key")

    assert tracing.configure_tracing() is True
    assert tracing.tracing_enabled() is True


def test_legacy_langchain_variable_also_requests_tracing(clean_env):
    clean_env.setenv("LANGCHAIN_TRACING_V2", "true")

    assert tracing.tracing_requested() is True


def test_traceable_is_a_passthrough_without_langsmith(monkeypatch):
    monkeypatch.setattr(tracing, "_langsmith_traceable", None)

    def work(x):
        return x * 2

    decorated = tracing.traceable(name="work", run_type="chain")(work)

    assert decorated is work
    assert decorated(21) == 42

    # must not raise either
    tracing.annotate_run({"a": 1})


def test_traceable_still_runs_the_function_when_tracing_is_off():
    @tracing.traceable(name="double", run_type="chain")
    def double(x):
        return x * 2

    assert double(4) == 8


def test_anonymous_id_is_stable_short_and_not_the_raw_id():
    user = "6f1c2c1e-1111-4222-8333-444455556666"

    first = tracing.anonymous_id(user)

    assert first == tracing.anonymous_id(user)
    assert len(first) == 12
    assert user not in first
    assert first != tracing.anonymous_id("someone-else")


def test_graph_run_config_for_a_sql_question():
    config = tracing.graph_run_config(
        user_id="user-1",
        thread_id="thread-9",
        intent="daily_nutrition",
        streaming=True,
    )

    assert config["run_name"] == "healthgpt_chat"
    assert "intent:daily_nutrition" in config["tags"]
    assert "path:sql" in config["tags"]
    assert "path:llm" not in config["tags"]
    assert config["metadata"]["thread_id"] == "thread-9"
    assert config["metadata"]["streaming"] is True
    assert "user-1" not in str(config)


def test_graph_run_config_for_an_llm_question():
    config = tracing.graph_run_config(user_id="u", intent="llm")

    assert "path:llm" in config["tags"]
    assert "thread_id" not in config["metadata"]
