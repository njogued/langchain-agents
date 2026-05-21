from langchain.types import interrupt, Command
from langchain.graph.message import RemoveMessage
from state import State

MAX_REWORKS = 2

def human_review_node(state: State) -> Command:
    last = state["messages"][-1]
    args = last.tool_calls[0]["args"]
    rework_count = state.get("rework_count", 0)
    feedback = interrupt({
        "to": args.get("to"),
        "subject": args.get("subject"),
        "content": args.get("content"),
        "rework_count": rework_count,
        "max_reworks": MAX_REWORKS
    })
    if not feedback or not feedback.strip():
        return Command(goto="tools")
    if rework_count >= MAX_REWORKS:
        print(f"[Max review attempts exceeded: {MAX_REWORKS}. Terminating...]")
        return Command(goto="__end__")
    return Command(
        goto="response_agent",
        update={
            "rework_count": rework_count + 1,
            "messages": [
                RemoveMessage(id=last.id),
                {
                    "role": "user",
                    "content": f"Generate the draft based on this feedback: {feedback}"
                }
            ]
        }
    )