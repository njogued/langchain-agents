import base64
from email.mime.text import MIMEText
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDS_FILE = Path("credentials.json")
TOKEN_FILE = Path("token.json")

def _get_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def _resolve_label_id(service, label_name: str) -> str:
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for lbl in labels:
        if lbl["name"].lower() == label_name.lower():
            return lbl["id"]
    raise ValueError(f"Label not found: {label_name}")

def list_messages_by_label(label_name: str, max_results: int = 5) -> list[dict]:
    """Return up to max_results message stubs ({id, threadId}) tagged with label_name."""
    service = _get_service()
    label_id = _resolve_label_id(service, label_name)
    resp = (
        service.users()
        .messages()
        .list(userId="me", labelIds=[label_id], maxResults=max_results)
        .execute()
    )
    return resp.get("messages", [])

def get_message(message_id: str) -> dict:
    """Return a normalized email dict: {message_id, thread_id, from, subject, body}."""
    service = _get_service()
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    body = _extract_body(msg["payload"])
    return {
        "message_id": msg["id"],
        "thread_id": msg["threadId"],
        "from_addr": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "body": body,
        "rfc_message_id": headers.get("message-id", ""),
        "references": headers.get("references", ""),
    }

def _extract_body(payload: dict) -> str:
    """Walk MIME parts, prefer text/plain."""
    if payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    parts = payload.get("parts", [])
    for part in parts:
        if part["mimeType"] == "text/plain" and part.get("body", {}).get("data"):
            return _decode(part["body"]["data"])
    for part in parts:
        if part["mimeType"].startswith("multipart"):
            nested = _extract_body(part)
            if nested:
                return nested
    return ""

def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")

def create_email_draft(
    to: str,
    subject: str,
    content: str,
    thread_id: str,
    rfc_message_id: str = "",
    references: str = "",
) -> str:
    """Create a Gmail draft as a reply to thread_id. Returns draft id."""
    service = _get_service()
    msg = MIMEText(content)
    msg["to"] = to
    msg["subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if rfc_message_id:
        msg["In-Reply-To"] = rfc_message_id
        msg["References"] = f"{references} {rfc_message_id}".strip()
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw, "threadId": thread_id}})
        .execute()
    )
    return draft["id"]
