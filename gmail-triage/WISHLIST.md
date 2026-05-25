# Wishlist

Nice-to-haves. Not committed to building any of these — capture only.

## Match Gmail's compose UX when drafting replies

Gmail's "Reply" button does two things automatically that the API does not. Both happen in `gmail_client.create_email_draft`, not in the LLM prompt — they're mechanical concerns.

### 1. Quoted original message

Gmail prepends the original thread as quoted text. Replicating it would mean formatting something like:

```
{reply body}

On {date}, {from_addr} wrote:
> {original body, each line prefixed with "> "}
```

Requires:
- Adding `date` extraction to `gmail_client.get_message` (it's in headers already, just not pulled).
- A small formatter that prefixes lines with `> ` for plain text, or wraps in `<blockquote>` if we switch to `text/html`.

### 2. Signature

Gmail's compose UI appends whatever signature is set in Settings. The API doesn't inject it. Two options:

- **Hardcode** the signature in `create_email_draft` — simplest.
- **Fetch from Gmail** via `users.settings.sendAs.list` — stays in sync with whatever's configured for the account.

## Configurable LABEL / MAX_EMAILS

Currently hardcoded in `main.py`. Move to CLI args or env vars.

## Delete retired `tools.py`

Replaced by MCP tools but still on disk.
