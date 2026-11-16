def route_after_supervisor(state: dict) -> str:

    selected_agents = state.get("selected_agents", [])

    if not selected_agents:
        return "unsupported"

    if len(selected_agents) == 1:
        return selected_agents[0]

    return "parallel_agents"