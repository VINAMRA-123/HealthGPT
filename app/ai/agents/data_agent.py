
import logging
from typing import Any, Callable

from app.ai.agents.nutrition_validator import validate_meals

logger = logging.getLogger(__name__)

DATA_AGENT_INTENTS = {
    "recent_meals",
    "weekly_budget",
    "day_meals",
}


def build_data_agent(
    get_direct_answer_fn: Callable,
):
    def data_agent_node(state: dict[str, Any]) -> dict:
        intent = state.get("intent")

        if intent not in DATA_AGENT_INTENTS:
            return {
                "errors": [{
                    "agent": "data_agent",
                    "error": f"Unsupported intent: {intent}",
                }],
                "completed_agents": ["data_agent"],
            }

        try:
            result = get_direct_answer_fn(
                intent=intent,
                db=state["db"],
                user_id=state["user_id"],
                user_message=state.get("user_message", ""),
            )

            if not isinstance(result, dict) or not result:
                raise ValueError("No usable data returned.")

            # Avoid modifying the original result.
            result = result.copy()

            if intent == "recent_meals":
                meals = result.get("meals", [])

                if not isinstance(meals, list):
                    raise ValueError(
                        "Recent meals response must contain a list."
                    )

                result["meals"] = validate_meals(meals)

            if not result.get("answer"):
                raise ValueError(
                    "Data agent returned no answer."
                )

            return {
                "agent_results": {
                    "data_agent": result,
                },
                "completed_agents": ["data_agent"],
            }

        except Exception:
            logger.exception(
                "Data agent failed. Intent: %s",
                intent,
            )

            return {
                "errors": [{
                    "agent": "data_agent",
                    "error": (
                        "Data retrieval or validation failed."
                    ),
                }],
                "completed_agents": ["data_agent"],
            }

    return data_agent_node
