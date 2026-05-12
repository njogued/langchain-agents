from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START

from nodes import triage_router
from state import State

def build_graph():
    workflow = StateGraph(State)
    workflow.add_node("triage_router", triage_router)
    workflow.add_edge(START, "triage_router")

    return workflow.compile(checkpointer=InMemorySaver())

graph = build_graph()