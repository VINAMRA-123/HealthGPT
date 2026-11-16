
import logging
from typing import Any, Callable

from langgraph.graph import START, END, StateGraph

from app.ai.graph.state import HealthGPTState
from app.ai.agents.data_agent import build_data_agent
from app.ai.agents.nutrition_agent import build_nutrition_agent


logger = logging.getLogger(__name__)


INTENT_AGENT_MAP = {
    "recent_meals": ["data_agent"],
    "weekly_budget": ["data_agent"],
    "daily_nutrition": ["nutrition_agent"],
    "weekly_protein": ["nutrition_agent"],
    "llm": ["gemini_agent"],
    "period_nutrition": ["nutrition_agent"],
}


def build_health_graph(
    classify_intent_fn: Callable,
    get_direct_answer_fn: Callable,
    gemini_workflow: Any,
    gemini_tools: list,
    get_gemini_models_fn: Callable,
    execute_health_tool_fn: Callable,
):

    # ========================================================
    # 1. SUPERVISOR
    # ========================================================

    def supervisor_node(state: HealthGPTState) -> dict:

        message = state.get("user_message", "").strip()

        if not message:
            return {
                "intent": "invalid",
                "selected_agents": [],
            }

        try:
            intent = classify_intent_fn(message)

            selected_agents = INTENT_AGENT_MAP.get(intent, [])

            return {
                "intent": intent,
                "selected_agents": selected_agents,
            }

        except Exception as exc:
            logger.exception("Intent classification failed")

            return {
                "intent": "classification_error",
                "selected_agents": [],
                "errors": [{
                    "agent": "supervisor",
                    "error": type(exc).__name__,
                }],
            }
    # ========================================================
    # 2. SPECIALIST AGENTS
    # ========================================================

    data_agent = build_data_agent(get_direct_answer_fn)

    nutrition_agent = build_nutrition_agent(get_direct_answer_fn)

    def safe_agent_node(
        agent_name: str,
        agent_fn: Callable,
    ):

        def node(state: HealthGPTState) -> dict:

            try:
                # Specialist agents already return graph state updates.
                # Return those updates directly; don't wrap them again.
                result = agent_fn(state)

                if not isinstance(result, dict):
                    raise TypeError(
                        f"{agent_name} returned an invalid result."
                    )

                return result

            except Exception as exc:

                logger.exception(
                    "%s execution failed",
                    agent_name,
                )

                return {
                    "errors": [
                        {
                            "agent": agent_name,
                            "error": type(exc).__name__,
                        }
                    ],
                    "completed_agents": [agent_name],
                }

        return node

    data_agent_node = safe_agent_node(
        "data_agent",
        data_agent,
    )

    nutrition_agent_node = safe_agent_node(
        "nutrition_agent",
        nutrition_agent,
    )

    # ========================================================
    # 3. GEMINI AGENT
    # ========================================================


    def gemini_agent_node(state: HealthGPTState) -> dict:

        try:
            workflow_result = gemini_workflow.invoke(
                {
                    "contents": state.get("contents", []),

                    "system_instruction": state.get(
                        "system_instruction",
                        "",
                    ),

                    "tools": gemini_tools,

                    "tool_executor": (
                        lambda tool_name, arguments: (
                            execute_health_tool_fn(
                                tool_name=tool_name,
                                arguments=arguments,
                                db=state["db"],
                                user_id=state["user_id"],
                            )
                        )
                    ),

                    "model_names": get_gemini_models_fn(),

                    "tool_rounds": 0,
                    "max_tool_rounds": 5,

                    "on_token": state.get("on_token"),
                }
            )

            if not isinstance(workflow_result, dict):
                raise TypeError(
                    "Gemini workflow returned an invalid result."
                )

            workflow_result = workflow_result.copy()

            answer = workflow_result.get("answer")

            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError(
                    "Gemini completed without generating an answer."
                )

            # Preserve meal-count metadata.
            # Do not overwrite a count explicitly returned by Gemini workflow.
            if "meals_considered" not in workflow_result:
                workflow_result["meals_considered"] = len(
                    state.get("meals", [])
                )

            return {
                "agent_results": {
                    "gemini_agent": workflow_result,
                },
                "completed_agents": ["gemini_agent"],
            }

        except Exception as exc:

            logger.exception("Gemini agent execution failed")

            return {
                "errors": [
                    {
                        "agent": "gemini_agent",
                        "error": type(exc).__name__,
                    }
                ],
                "completed_agents": ["gemini_agent"],
            }

        # ========================================================
        # 4. FINAL SYNTHESIS
        # ========================================================

    def synthesis_node(state: HealthGPTState) -> dict:

        results = state.get("agent_results", {}) or {}

        errors = state.get("errors", []) or []

        intent = state.get("intent")

        # ----------------------------------------------------
        # No agent returned a usable result.
        # ----------------------------------------------------

        if not results:

            if intent == "invalid":

                answer = "Please enter a question."
                model = "none"

            elif errors:

                answer = (
                    "I couldn't retrieve the information needed "
                    "to answer your question. Please try again."
                )
                model = "error"

            else:

                answer = (
                    "I can't answer this question using the "
                    "currently supported workflows."
                )
                model = "none"

            return {
                "final_answer": answer,
                "answer": answer,
                "model": model,
                "meals_considered": 0,
                "needs_clarification": False,
                "clarification_question": "",
            }

        # ----------------------------------------------------
        # Current architecture selects one agent per request.
        # ----------------------------------------------------

        selected_agents = state.get("selected_agents", [])

        if not selected_agents:
            result = None
        else:
            agent_name = selected_agents[0]
            result = results.get(agent_name)

        if not isinstance(result, dict):
            answer = (
                "I couldn't generate a reliable answer. "
                "Please try again."
            )

            return {
                "final_answer": answer,
                "answer": answer,
                "model": "error",
                "meals_considered": 0,
                "needs_clarification": False,
                "clarification_question": "",
            }

        answer = result.get("answer")

        if not isinstance(answer, str) or not answer.strip():

            answer = (
                "I couldn't generate a reliable answer. "
                "Please try again."
            )

            model = "error"

        else:

            model = result.get("model", "unknown")

        meals_considered = result.get(
            "meals_considered",
            0,
        )

        needs_clarification = result.get(
            "needs_clarification",
            False,
        )

        clarification_question = result.get(
            "clarification_question",
            "",
        )

        return {
            "final_answer": answer,
            "answer": answer,
            "model": model,
            "meals_considered": meals_considered,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
        }

    # ========================================================
    # 5. CONDITIONAL ROUTING
    # ========================================================

    def route_after_supervisor(state: HealthGPTState) -> str:

        selected_agents = state.get(
            "selected_agents",
            [],
        )

        if len(selected_agents) != 1:
            return "synthesis"

        return selected_agents[0]

    # ========================================================
    # 6. BUILD GRAPH
    # ========================================================

    graph = StateGraph(HealthGPTState)

    graph.add_node(
        "supervisor",
        supervisor_node,
    )

    graph.add_node(
        "data_agent",
        data_agent_node,
    )

    graph.add_node(
        "nutrition_agent",
        nutrition_agent_node,
    )

    graph.add_node(
        "gemini_agent",
        gemini_agent_node,
    )

    graph.add_node(
        "synthesis",
        synthesis_node,
    )

    graph.add_edge(
        START,
        "supervisor",
    )

    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "data_agent": "data_agent",
            "nutrition_agent": "nutrition_agent",
            "gemini_agent": "gemini_agent",
            "synthesis": "synthesis",
        },
    )

    graph.add_edge(
        "data_agent",
        "synthesis",
    )

    graph.add_edge(
        "nutrition_agent",
        "synthesis",
    )

    graph.add_edge(
        "gemini_agent",
        "synthesis",
    )

    graph.add_edge(
        "synthesis",
        END,
    )

    return graph.compile()
