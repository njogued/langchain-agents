# Dev notes

Challenges hit during the build, what caused them, how they were fixed. Written for future-me. See also `MCP_INTEGRATION_NOTES.md` for the original MCP integration log.

## 1. MCP stdio transport: use the raw SDK, not `MultiServerMCPClient`

**Symptom:** Tools loaded fine but tool calls were flaky — every call seemed to spawn a fresh subprocess and connection.

**Cause:** `MultiServerMCPClient` (from `langchain-mcp-adapters`) creates an ephemeral session per call for stdio transport. New subprocess on every tool call, no shared state, slow.

**Fix:** Drop down to the raw `mcp` SDK (`stdio_client` + `ClientSession`) in `main.py`. Open the session once, wrap the whole agent run in nested `async with` blocks. One subprocess, one persistent connection. See `main.py:30-44`.

## 2. stdio MCP + `input()` for HITL don't conflict

**Worry:** "Don't use stdio when you also need stdin" advice — would the MCP subprocess's stdin/stdout collide with `input()` reading from the terminal?

**Answer:** No. The stdio MCP uses the *subprocess's* stdin/stdout (piped to the parent's MCP client code). `input()` reads from the *parent process's* stdin (the user's terminal). Different file descriptors entirely.

The one real constraint: the MCP server itself must never `print()` to stdout — that would corrupt the JSON-RPC stream. FastMCP routes logs to stderr by default, so it's safe.

## 3. Email context lost on rework rounds

**Symptom:** After the user gave revision feedback in `human_review`, the re-drafted reply hallucinated (`Hi [Name]`), asked for the thread_id back, or didn't emit a tool call at all and the loop just ended.

**Cause:** `response_node.response_agent` invoked the LLM with the email content as a user prompt but only returned the AI response to state. The user prompt was never persisted. When `human_review` then removed the AI message and added a feedback message, `state["messages"]` contained *only* the feedback. The next LLM call had no idea what email it was replying to.

**Fix:** In the `else` branch (first call), return both messages — the seed user prompt and the AI response. Now `state["messages"]` retains the email context across all rework rounds. See `response_node.py:53-65`.

**Tell:** In LangSmith, if the AI starts asking for fields it should already know (`send me the thread_id`), the state is missing context.

## 4. Gmail draft threading on send

**Symptom:** Draft showed up correctly attached to the thread in the Gmail UI, but when sent it became a standalone email with `Re: ORIGINAL SUBJECT` as the subject.

**Cause:** Setting `threadId` on the API body only handles thread display on your own Gmail side. The sent MIME message also needs RFC 2822 headers for the recipient's mail client (and Gmail itself on send) to thread properly:
- `In-Reply-To` — the RFC `Message-ID` of the email being replied to.
- `References` — the chain of prior `Message-ID`s in the thread.

These are different from Gmail's internal `msg["id"]`. The RFC `Message-ID` is in the email headers (`<...@mail.gmail.com>`); the Gmail internal ID is opaque (`1a2b3c`).

**Fix:**
- `gmail_client.get_message` now extracts `message-id` and `references` headers.
- `EmailInput` carries `rfc_message_id` and `references`.
- `gmail_client.create_email_draft` sets `In-Reply-To` and `References`, and forces a `Re:` subject prefix as a guardrail against LLM-invented subjects.
- The MCP tool, prompt, and response node pass the new fields through.

## 5. ReAct loop ending early when LLM gave up

**Observation:** Sometimes the response_agent emitted a plain text reply instead of a `create_draft` tool call. `tools_condition` returned non-`"tools"`, `route_after_draft` routed to `__end__`, and the loop terminated with no draft.

**Cause:** Same root cause as #3 — missing context. When the LLM didn't have enough to act on, it wrote prose instead of calling the tool.

**Fix:** Same fix as #3. Worth noting because the symptom (silent termination) is different from the hallucination symptom, but the underlying problem is the same.

## 6. LangSmith "TURN" count ≠ rework count

**Confusion:** `MAX_REWORKS = 2` (i.e. 3 drafts allowed) but LangSmith showed 6 turns.

**Reason:** LangSmith counts **graph supersteps** (node executions between checkpoints). Each draft cycle costs 2 nodes (`response_agent` + `human_review`). 3 drafts × 2 nodes = 6 turns. Not a bug.
