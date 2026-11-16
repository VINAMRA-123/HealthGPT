
import logging
import os
from typing import Any, Callable, TypedDict

import httpx
from google import genai
from google.genai import types
from google.genai.errors import ServerError
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)


class ChatState(TypedDict, total=False):
    contents: list[Any]
    system_instruction: str
    tools: list[Any]
    on_token: Callable[[str], None]

    tool_executor: Callable[..., dict]
    model_names: list[str]

    pending_calls: list[Any]
    tool_rounds: int
    max_tool_rounds: int

    answer: str
    model: str


def build_chat_workflow():
    """Gemini agent -> backend tools -> Gemini final answer."""

    def agent_node(state: ChatState) -> dict:
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        model_names = state.get("model_names", [])

        if not model_names:
            raise RuntimeError("No Gemini models configured.")

        client = genai.Client(api_key=api_key)

        tool_rounds = state.get("tool_rounds", 0)
        max_tool_rounds = state.get("max_tool_rounds", 5)

        available_tools = (
            state.get("tools", [])
            if tool_rounds < max_tool_rounds
            else []
        )

        on_token = state.get("on_token")
        last_error = None

        for model_name in model_names:
            emitted_any = False

            try:
                logger.info("Trying Gemini model: %s", model_name)

                stream = client.models.generate_content_stream(
                    model=model_name,
                    contents=state["contents"],
                    config=types.GenerateContentConfig(
                        system_instruction=state["system_instruction"],
                        tools=available_tools,
                        temperature=0.3,
                        max_output_tokens=1600,
                    ),
                )

                text_chunks = []
                response_parts = []

                for chunk in stream:
                    if chunk.text:
                        text_chunks.append(chunk.text)

                        # Track partial output even without a callback.
                        emitted_any = True

                        if on_token:
                            on_token(chunk.text)

                    if chunk.candidates:
                        content = chunk.candidates[0].content

                        if content and content.parts:
                            response_parts.extend(content.parts)

                if not response_parts and text_chunks:
                    response_parts = [
                        types.Part.from_text(
                            text="".join(text_chunks)
                        )
                    ]

                if not response_parts:
                    logger.warning(
                        "Gemini returned an empty response: %s",
                        model_name,
                    )
                    continue

                content = types.Content(
                    role="model",
                    parts=response_parts,
                )

                function_calls = [
                    part.function_call
                    for part in response_parts
                    if part.function_call is not None
                ]

                updated_contents = [
                    *state["contents"],
                    content,
                ]

                if function_calls:
                    if tool_rounds >= max_tool_rounds:
                        return {
                            "contents": updated_contents,
                            "pending_calls": [],
                            "answer": (
                                "I couldn't complete that request within "
                                "the allowed tool execution limit. "
                                "Please try a more specific question."
                            ),
                            "model": model_name,
                        }

                    return {
                        "contents": updated_contents,
                        "pending_calls": function_calls,
                        "model": model_name,
                    }

                answer = "".join(text_chunks).strip()

                if answer:
                    return {
                        "contents": updated_contents,
                        "pending_calls": [],
                        "answer": answer,
                        "model": model_name,
                    }

            except ServerError as exc:
                status_code = (
                    getattr(exc, "code", None)
                    or getattr(exc, "status_code", None)
                )

                logger.warning(
                    "Gemini model %s failed with HTTP %s",
                    model_name,
                    status_code,
                    exc_info=True,
                )

                if status_code in (429, 500, 502, 503, 504):
                    last_error = exc

                    # Do not switch models after partial output.
                    if emitted_any:
                        raise

                    continue

                raise

            except httpx.TransportError as exc:
                logger.warning(
                    "Gemini transport error with model %s: %s",
                    model_name,
                    str(exc),
                    exc_info=True,
                )

                # Do not switch models after partial output.
                if emitted_any:
                    raise

                last_error = exc

                # Try the next configured model.
                continue

        if last_error:
            raise last_error

        raise RuntimeError(
            "Gemini could not generate a complete response."
        )

    def tools_node(state: ChatState) -> dict:
        tool_messages = []

        for function_call in state.get("pending_calls", []):
            tool_name = function_call.name
            arguments = dict(function_call.args or {})

            try:
                result = state["tool_executor"](
                    tool_name=tool_name,
                    arguments=arguments,
                )

                if not isinstance(result, dict):
                    result = {"result": result}

            except Exception:
                logger.exception(
                    "HealthGPT tool execution failed: %s",
                    tool_name,
                )

                result = {
                    "error": (
                        "The requested operation could not be completed. "
                        "Please try again or rephrase your request."
                    )
                }

            tool_messages.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result},
                )
            )

        return {
            "contents": [
                *state["contents"],
                types.Content(
                    role="user",
                    parts=tool_messages,
                ),
            ],
            "pending_calls": [],
            "tool_rounds": state.get("tool_rounds", 0) + 1,
        }

    def choose_next_step(state: ChatState) -> str:
        if state.get("answer"):
            return "finish"

        if state.get("pending_calls"):
            if state.get("tool_rounds", 0) >= state.get(
                "max_tool_rounds", 5
            ):
                return "finish"

            return "execute_tools"

        return "finish"

    graph = StateGraph(ChatState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)

    graph.add_edge(START, "agent")

    graph.add_conditional_edges(
        "agent",
        choose_next_step,
        {
            "execute_tools": "tools",
            "finish": END,
        },
    )

    graph.add_edge("tools", "agent")

    return graph.compile()
