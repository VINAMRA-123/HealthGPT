
from operator import add
from typing import Annotated, Any, Callable, TypedDict


def merge_agent_results(
    current: dict[str, Any] | None,
    update: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge specialist agent outputs into the shared state."""
    return {
        **(current or {}),
        **(update or {}),
    }


class HealthGPTState(TypedDict, total=False):

    # -------------------------
    # User input and context
    # -------------------------
    user_id: str
    db: Any

    user_message: str
    conversation_history: list[dict]

    health_context: dict
    meals: list[dict]
    meals_considered: int

    # -------------------------
    # Supervisor / routing
    # -------------------------
    intent: str
    selected_agents: list[str]

    # -------------------------
    # Specialist agent outputs
    # -------------------------
    agent_results: Annotated[
        dict[str, Any],
        merge_agent_results,
    ]

    completed_agents: Annotated[list[str], add]
    errors: Annotated[list[dict], add]

    # -------------------------
    # Final synthesis
    # -------------------------
    final_answer: str
    answer: str
    model: str

    needs_clarification: bool
    clarification_question: str

    # -------------------------
    # Existing Gemini workflow
    # -------------------------
    contents: list[Any]
    system_instruction: str
    tools: list[Any]
    on_token: Callable[[str], None]

    tool_executor: Callable[..., dict]
    model_names: list[str]

    pending_calls: list[Any]
    tool_rounds: int
    max_tool_rounds: int
