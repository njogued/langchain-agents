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
    print(f"  [triage] Processing: {email['subject'][:50]}...") 
    user_prompt = f"""From: {email['from_addr']}
        Subject: {email['subject']}
        Body: {email['body']}"""
    result = router_llm.invoke(
        [
            {"role": "system", "content": TRIAGE_SYSTEM},
            {"role": "user", "content": user_prompt}
        ]
    )
    print(f"  [triage] Result: {result.classification}") 
    goto = "response_agent" if result.classification == "respond" else "__end__"

    return Command(
        goto=goto,
        update={
            "classification": result.classification,
            "reasoning": result.reasoning,
        },
    )