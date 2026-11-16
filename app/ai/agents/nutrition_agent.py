
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

NUTRITION_AGENT_INTENTS = {
    "daily_nutrition",
    "weekly_protein",
    "period_nutrition",
}


def build_nutrition_agent(
    get_direct_answer_fn: Callable,
):
    def nutrition_agent_node(state: dict[str, Any]) -> dict:
        intent = state.get("intent")

        if intent not in NUTRITION_AGENT_INTENTS:
            return {
                "errors": [{
                    "agent": "nutrition_agent",
                    "error": f"Unsupported intent: {intent}",
                }],
                "completed_agents": ["nutrition_agent"],
            }

        try:
            result = get_direct_answer_fn(
                intent=intent,
                db=state["db"],
                user_id=state["user_id"],
                user_message=state.get("user_message", ""),
            )

            if not isinstance(result, dict) or not result:
                raise ValueError(
                    "No usable nutrition data returned."
                )

            if not result.get("answer"):
                raise ValueError(
                    "Nutrition agent returned no answer."
                )

            return {
                "agent_results": {
                    "nutrition_agent": result,
                },
                "completed_agents": ["nutrition_agent"],
            }

        except Exception:
            logger.exception(
                "Nutrition agent failed. Intent: %s",
                intent,
            )

            return {
                "errors": [{
                    "agent": "nutrition_agent",
                    "error": "Nutrition data retrieval failed.",
                }],
                "completed_agents": ["nutrition_agent"],
            }

    return nutrition_agent_node
