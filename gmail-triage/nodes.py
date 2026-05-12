from typing import Literal

from langchain.chat_models import init_chat_model
from langgraph.types import Command
from pydantic import BaseModel, Field

from prompts import TRIAGE_SYSTEM
from state import State

class ClassificationOutput(BaseModel):
    """Structured output schema for the triage router"""
    reasoning: str = Field(
        description="Step-by-step reasoning behind the classification"
    )
    classification: Literal["ignore", "notify", "respond"] = Field(
        description="Triage decision for this email"
    )

llm = init_chat_model("gpt-5-mini", model_provider="openai", temperature=0)
router_llm = llm.with_structured_output(ClassificationOutput)

def triage_router(state: State) -> Command:
    """Classify the email and route accordingly"""
    email = state["email_input"]
    user_prompt = f"""From: {email['from_addr']}
        Subject: {email['subject']}
        Body: {email['body']}"""
    result = router_llm.invoke(
        [
            {"role": "system", "content": TRIAGE_SYSTEM},
            {"role": "user", "content": user_prompt}
        ]
    )
    return Command(
        goto="__end__",
        update={
            "classification": result.classification,
            "reasoning": result.reasoning,
        },
    )