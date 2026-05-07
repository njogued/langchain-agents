from langchain.tools import tool
from gmail_client import create_gmail_draft

@tool
def write_email_draft(to: str, subject: str, body: str) -> str:
    """Writes an email draft in Gmail."""
    draft_id = create_gmail_draft(to, subject, body)
    return f"Draft created with ID: {draft_id}"

@tool
def Done(summary: str) -> str:
    """Indicates that the agent has completed its task."""
    return summary