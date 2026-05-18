from fastmcp import FastMCP
import gmail_client

# create a server instance and give it a display name
mcp = FastMCP("gmail-tools")

# create an mcp tool - list_messages
@mcp.tool()
def list_messages(label_name: str, max_results: int = 5) -> list[dict]:
    """List email message stubs for a given Gmail label.

    Returns a list of dicts with 'id' and 'threadId' keys.
    Use these IDs with get_message to fetch full email content.
    """
    # Delegates directly to your existing function.
    return gmail_client.list_messages_by_label(label_name, max_results)

@mcp.tool()
def get_message(message_id: str) -> dict:
    """Fetch a full email by message ID.
    Returns a dict with: message_id, thread_id, from_addr, subject, body.
    """
    return gmail_client.get_message(message_id)


@mcp.tool()
def create_draft(to: str, subject: str, content: str, thread_id: str) -> str:
    """Create a Gmail draft reply in an existing thread.
    Args:
        to: Recipient email address.
        subject: Email subject line.
        content: Plain text body of the draft.
        thread_id: Gmail thread ID to attach this draft to.
    Returns the draft ID.
    """
    return gmail_client.create_email_draft(to, subject, content, thread_id)

# This is the entry point. When run as `python gmail_mcp_server.py`,
# FastMCP starts a stdio transport loop — it reads JSON-RPC requests
# from stdin, dispatches to the matching @mcp.tool(), and writes
# the response to stdout.
if __name__ == "__main__":
    mcp.run()