from langchain.tools import tool
from gmail_client import create_gmail_draft

@tool
def write_email_draft(to: str, subject: str, body: str) -> str:
    """Writes an email draft in Gmail.
    Args:
        to: Recipient email address.
        subject: Subject line for the email.
        body: Body content of the email.
    Returns:
        A string indicating the draft ID of the created email.
    """
    draft_id = create_gmail_draft(to, subject, body)
    return f"Draft created with ID: {draft_id}"

@tool
def Done(summary: str) -> str:
    """Signal that the response is complete.

    Args:
        summary: One-line summary of what was done.
    """
    return summary