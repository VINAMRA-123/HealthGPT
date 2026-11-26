"""Behaviour tests for the Gemini workflow, using a fake Gemini client.

They protect the model-fallback and tool-calling logic that LangSmith tracing
was wrapped around. No network and no API key are needed.
"""

from types import SimpleNamespace

import httpx
import pytest
from google.genai import types

from app.ai import chat_workflow


def text_chunk(text, usage=None):
    part = types.Part.from_text(text=text)

    return SimpleNamespace(
        text=text,
        candidates=[
            SimpleNamespace(content=types.Content(role="model", parts=[part]))
        ],
        usage_metadata=usage,
    )


def call_chunk(name, args):
    part = types.Part.from_function_call(name=name, args=args)

    return SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(content=types.Content(role="model", parts=[part]))
        ],
        usage_metadata=None,
    )


class FakeModels:
    def __init__(self, behaviours):
        self.behaviours = list(behaviours)
        self.models_called = []

    def generate_content_stream(self, model, contents, config):
        self.models_called.append(model)
        behaviour = self.behaviours.pop(0)

        if isinstance(behaviour, Exception):
            raise behaviour

        return behaviour()


class FakeClient:
    def __init__(self, behaviours):
        self.models = FakeModels(behaviours)


@pytest.fixture
def run_workflow(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def run(behaviours, *, tool_executor=None, on_token=None, models=("m1", "m2")):
        fake = FakeClient(behaviours)
        monkeypatch.setattr(
            chat_workflow.genai, "Client", lambda api_key: fake
        )

        state = {
            "contents": [],
            "system_instruction": "system",
            "tools": [],
            "model_names": list(models),
            "tool_executor": tool_executor or (lambda tool_name, arguments: {}),
        }

        if on_token is not None:
            state["on_token"] = on_token

        workflow = chat_workflow.build_chat_workflow()
        return fake, workflow.invoke(state)

    return run


def test_answers_from_the_first_model_and_streams_tokens(run_workflow):
    tokens = []

    fake, result = run_workflow(
        [lambda: iter([text_chunk("Hello "), text_chunk("there")])],
        on_token=tokens.append,
    )

    assert result["answer"] == "Hello there"
    assert result["model"] == "m1"
    assert tokens == ["Hello ", "there"]
    assert fake.models.models_called == ["m1"]


def test_falls_back_to_the_next_model_when_nothing_was_streamed(run_workflow):
    fake, result = run_workflow(
        [httpx.ConnectError("model one is down"), lambda: iter([text_chunk("ok")])]
    )

    assert result["answer"] == "ok"
    assert result["model"] == "m2"
    assert fake.models.models_called == ["m1", "m2"]


def test_does_not_switch_models_after_partial_output(run_workflow):
    def partial_then_fail():
        yield text_chunk("Hel")
        raise httpx.ReadError("connection dropped")

    tokens = []

    with pytest.raises(httpx.ReadError):
        fake, _ = run_workflow(
            [partial_then_fail, lambda: iter([text_chunk("never used")])],
            on_token=tokens.append,
        )

    # the user already saw "Hel", so a second model must not start over
    assert tokens == ["Hel"]


def test_raises_when_every_model_fails(run_workflow):
    with pytest.raises(httpx.ConnectError):
        run_workflow(
            [httpx.ConnectError("one"), httpx.ConnectError("two")]
        )


def test_runs_a_tool_then_answers(run_workflow):
    calls = []

    def executor(tool_name, arguments):
        calls.append((tool_name, arguments))
        return {"meals": [{"food_name": "Oats"}]}

    fake, result = run_workflow(
        [
            lambda: iter([call_chunk("get_recent_meals", {"limit": 3})]),
            lambda: iter([text_chunk("You ate oats.")]),
        ],
        tool_executor=executor,
    )

    assert calls == [("get_recent_meals", {"limit": 3})]
    assert result["answer"] == "You ate oats."
    assert result["tool_rounds"] == 1


def test_a_failing_tool_does_not_crash_the_workflow(run_workflow):
    def broken(tool_name, arguments):
        raise RuntimeError("database is down")

    _, result = run_workflow(
        [
            lambda: iter([call_chunk("get_recent_meals", {})]),
            lambda: iter([text_chunk("Sorry, I could not read your meals.")]),
        ],
        tool_executor=broken,
    )

    assert result["answer"].startswith("Sorry")


def test_usage_metadata_is_converted_for_langsmith():
    usage = SimpleNamespace(
        prompt_token_count=10,
        candidates_token_count=5,
        thoughts_token_count=2,
        total_token_count=17,
    )

    assert chat_workflow._usage_dict(usage) == {
        "input_tokens": 10,
        "output_tokens": 7,
        "total_tokens": 17,
    }
    assert chat_workflow._usage_dict(None) is None


def test_llm_input_summary_hides_objects_and_keeps_the_useful_parts():
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text="hi there")])
    ]
    tools = [SimpleNamespace(function_declarations=[SimpleNamespace(name="x")])]

    summary = chat_workflow._summarize_llm_inputs(
        {
            "model_name": "m1",
            "contents": contents,
            "tools": tools,
            "genai_client": object(),
        }
    )

    assert summary == {
        "model": "m1",
        "message_count": 1,
        "last_message": "hi there",
        "tools": ["x"],
    }


def test_tool_output_summary_does_not_leak_the_data():
    summary = chat_workflow._summarize_tool_outputs(
        {"meals": [{"food_name": "secret dinner"}]}
    )

    assert "secret dinner" not in str(summary)
    assert summary["keys"] == ["meals"]
    assert summary["has_error"] is False
