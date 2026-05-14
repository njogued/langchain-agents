from langchain.tools import tool
from gmail_client import create_email_draft

@tool
def write_email_draft(to: str, subject: str, body: str, thread_id: str) -> str:
    """Writes an email draft in Gmail as a reply on an existing thread.
    Args:
        to: Recipient email address.
        subject: Subject line for the email.
        body: Body content of the email.
        thread_id: Gmail thread ID to attach the draft to so it becomes a reply.
    Returns:
        A string indicating the draft ID of the created email.
    """
    draft_id = create_email_draft(to, subject, body, thread_id)
    return f"Draft created with ID: {draft_id}"

@tool
def Done(summary: str) -> str:
    """Signal that the response is complete.

    Args:
        summary: One-line summary of what was done.
    """
    return summary