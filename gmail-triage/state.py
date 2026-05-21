from typing import Literal, TypedDict
from langgraph.graph import MessagesState

class EmailInput(TypedDict):
    message_id: str
    thread_id: str
    subject: str
    from_addr: str
    body: str

class State(MessagesState):
    email_input: EmailInput
    classification: Literal["ignore", "notify", "respond"] | None
    reasoning: str | None
    draft_id: str | None
    rework_count: int