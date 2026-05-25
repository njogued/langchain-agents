# gmail-triage

LangGraph agent that pulls Gmail messages by label, classifies each one as `ignore`, `notify`, or `respond`, and drafts replies for `respond` emails via MCP tools.

## Entry point

`main.py` — async entry point. Connects to the Gmail MCP server (stdio transport), loads MCP tools as LangChain tools, builds the graph, then loops over emails under the hard-coded `LABEL` (currently `0-Clients/client-cynthia`, capped at `MAX_EMAILS`). Uses `graph.ainvoke()` per email. The MCP session stays alive for the entire run.

## Graph flow

```
START → triage_router → (respond?) → response_agent → human_review → tools → END
                       → (ignore/notify?) → END                  ↘ (rework) → response_agent
                                                                 ↘ (max reworks) → END
```

- `triage_router` classifies and routes via `Command(goto=...)`
- `response_agent` drafts replies using an LLM with MCP tools bound
- `human_review` interrupts the graph and waits for user approval/feedback before tools run
- `tools` (`ToolNode`) executes MCP tool calls (only reached after human approval)

The ReAct loop is gated on a human-in-the-loop checkpoint: after the LLM emits a `create_draft` tool call, `human_review` pauses execution via `interrupt()`, surfacing the proposed draft to the caller. The caller resumes with either empty input (approve → tools execute) or revision instructions (back to `response_agent` with feedback, up to `MAX_REWORKS = 2`).

## Module map

- `main.py` — async entry point. Owns the MCP client lifecycle: spawns `gmail_mcp_server.py` via `stdio_client`, creates a `ClientSession`, loads tools with `load_mcp_tools(session)`, passes them to `build_graph(tools)`. Per-email loop drives HITL: after each `graph.ainvoke`, while the result contains `__interrupt__`, prints the proposed draft and reads `input()` for approve/revise, then resumes with `Command(resume=fb)`.
- `graph.py` — `build_graph(tools)` builds a `StateGraph(State)` with four nodes (`triage_router`, `response_agent`, `human_review`, `tools`). Compiled with `InMemorySaver`. Takes MCP tools as a parameter. `route_after_draft` sends the flow to `human_review` if the LLM emitted tool calls, otherwise to END.
- `nodes.py` — `triage_router` calls `gpt-5-mini` via `init_chat_model` with `with_structured_output(ClassificationOutput)`. Returns `Command(goto="response_agent"|"__end__")` based on classification.
- `response_node.py` — `make_response_agent(tools)` factory returns the `response_agent` node. Uses `bind_tools(tools)` for tool-calling. **First call** seeds `state["messages"]` with both the email-context user prompt and the AI response, so the original email context persists across rework rounds. **Subsequent calls** (after tool execution or human feedback) pass the full message history through.
- `human_review_node.py` — `human_review` reads the last message's tool call args, calls `interrupt()` with the proposed draft fields (`to`, `subject`, `content`, `rework_count`, `max_reworks`). On resume: empty feedback → `goto="tools"` (approve); non-empty feedback → `goto="response_agent"` with `RemoveMessage` clearing the prior draft + a new user message containing the feedback; `rework_count` past `MAX_REWORKS` (= 2) → `goto="__end__"`.
- `state.py` — `EmailInput` TypedDict (`message_id`, `thread_id`, `subject`, `from_addr`, `body`, `rfc_message_id`, `references`) and `State(MessagesState)` adding `email_input`, `classification`, `reasoning`, `draft_id`, `rework_count`.
- `prompts.py` — `TRIAGE_SYSTEM` (classifier prompt, hard-codes Ed's three clients) and `RESPONSE_SYSTEM` (draft-writing prompt; instructs the LLM to forward `thread_id`, `rfc_message_id`, and `references` unchanged so the draft threads on send).
- `gmail_mcp_server.py` — FastMCP server wrapping `gmail_client.py`. Exposes three MCP tools: `list_messages`, `get_message`, `create_draft`. Runs on stdio transport.
- `gmail_client.py` — Google API wrapper. `list_messages_by_label`, `get_message`, `create_email_draft`. `get_message` extracts the RFC `Message-ID` and `References` headers in addition to from/subject/body. `create_email_draft` sets `In-Reply-To` + `References` MIME headers on the draft (so it threads on send, not just in the Gmail UI) and forces a `Re:` subject prefix. OAuth flow uses `credentials.json` + `token.json` with scope `gmail.modify`.
- `tools.py` — RETIRED. Old LangChain `@tool`s replaced by MCP tools. Still in directory but not imported.
- `smoke_test.py` — minimal check that the Gmail client can list + fetch one message.
- `MCP_INTEGRATION_NOTES.md` — full build log documenting the MCP integration, all challenges, and lessons learned.
- `devnotes.md` — running log of challenges hit and how they were resolved (state-loss on rework, draft threading on send, etc.).
- `wishlist.md` — nice-to-haves not committed to: quoted message body, signature injection, configurable LABEL/MAX_EMAILS.

## MCP architecture

The agent consumes Gmail tools over MCP rather than calling `gmail_client.py` directly:

1. `gmail_mcp_server.py` (FastMCP) wraps `gmail_client.py` functions as MCP tools
2. `main.py` spawns it as a subprocess via the raw `mcp` SDK (`stdio_client` + `ClientSession`)
3. `load_mcp_tools(session)` converts MCP tools to LangChain `BaseTool` objects
4. Tools are passed to `build_graph()` which binds them to the LLM and `ToolNode`

**Important:** Use the raw `mcp` SDK for stdio transport, not `MultiServerMCPClient`. The latter creates ephemeral per-call sessions (new subprocess per tool call), which is unreliable for stdio. The raw SDK maintains a persistent session.

## Dependencies

```
langchain, langgraph, pydantic          # core agent framework
fastmcp                                  # MCP server
langchain-mcp-adapters, mcp             # MCP client + LangChain bridge
google-api-python-client, google-auth-oauthlib  # Gmail API
python-dotenv                            # env vars
```

## Running

```
python main.py        # full triage + draft pipeline
python smoke_test.py  # Gmail auth + fetch sanity check
```

First run triggers the OAuth browser flow and writes `token.json`.

## Secrets

`.env`, `credentials.json`, `token.json` are all local and gitignored-worthy — do not commit. `.env` holds the OpenAI key loaded by `load_dotenv()` in `main.py` before any other import.

## Classification contract

`ClassificationOutput` (Pydantic) requires `reasoning` first, then `classification` in `{"ignore", "notify", "respond"}`. The prompt instructs reasoning-then-label; keep that order if you change the schema or the LLM may degrade.

## Known gaps

- `LABEL` and `MAX_EMAILS` are hard-coded in `main.py`.
- `tools.py` is retired but not deleted.
- No labeling action after triage (only drafting for `respond`).
- `notify` classification doesn't trigger any notification mechanism.
- Drafted replies don't include quoted original-message history or a signature (Gmail's compose UI normally adds these — see `wishlist.md`).

## Roadmap

### Phase 1: Gmail labeling via MCP

Add automatic Gmail labeling after triage. Every email gets a label (`triage/ignore`, `triage/notify`, `triage/respond`) regardless of classification.

- Add `label_message(message_id, label_name)` to `gmail_client.py`
- Expose it as a `label_message` tool in `gmail_mcp_server.py`
- Add a `label_node` to the graph that runs for all emails, before the respond/end routing

Target graph:
```
START → triage_router → label_node → (respond?) → response_agent → human_review → tools → END
                                    → (ignore/notify?) → END
```

### Phase 2: Human-in-the-loop (HITL) — DONE

Implemented in `human_review_node.py`. The graph pauses via `interrupt()` after the LLM proposes a draft and waits for the caller (currently `main.py` via terminal `input()`) to approve or send revision instructions. Up to `MAX_REWORKS = 2` revisions allowed before the loop terminates.

Key wrinkle solved: on rework, the email context must persist in `state["messages"]` or the LLM hallucinates / asks for the thread_id back. Fix in `response_node.py` is to write both the seed user prompt and the AI response into state on the first call. See `devnotes.md` #3.

### Phase 3: Memory (LangGraph Store)

Add cross-thread memory so the agent learns and improves over time.

- Use LangGraph's `Store` for persistent memory across different emails/runs
- Unlike the checkpointer (per-thread, per-email), the Store is shared and long-lived
- The response agent reads from the Store before drafting (for context) and writes after (to remember)
- Example memories: "Cynthia prefers short bullet-point replies", "Always mention project timeline with Michael", "Last email to Marc was about the API migration"

LangGraph concept: `Store` is a key-value store injected into nodes. Nodes read/write via `store.get()` / `store.put()`. Data persists across graph invocations.

### Phase 4: Dynamic tool registration

Make the agent's capabilities configurable per user. Different users get different tool sets without code changes.

**Config-driven MCP connections:** A config file declares which MCP servers to connect to:
```json
{
  "servers": {
    "gmail": {"command": "python3", "args": ["gmail_mcp_server.py"], "transport": "stdio"},
    "slack": {"command": "npx", "args": ["@slack/mcp-server"], "transport": "stdio"},
    "notion": {"command": "python3", "args": ["notion_mcp_server.py"], "transport": "stdio"}
  }
}
```

At startup, the agent reads the config, connects to all listed servers, loads all tools, and passes the combined list to the graph. User A gets Gmail + Slack, User B gets Gmail + Notion. Same agent code, different tool sets.

Implementation:
- `main.py` reads a `servers.json` config file
- Connects to each server via `stdio_client` + `ClientSession` (persistent sessions)
- Merges all tools into a single list passed to `build_graph(tools)`
- The LLM sees all available tools via `bind_tools()` and decides which to use

### Phase 5: Natural language orchestration (end goal)

Give users the power to define multi-tool workflows by prompting in natural language.

The user says: *"When I get a client email, draft a reply, create a Notion task for follow-up, and ping me on Slack."*

This works because:
1. **Phase 4** already loads all available MCP tools dynamically
2. **`bind_tools()`** gives the LLM visibility into every tool's name, description, and schema
3. The LLM chains tool calls based on the natural language instruction — no code changes needed
4. **Phase 3 memory** lets the agent remember user preferences across sessions
5. **Phase 2 HITL** lets the user approve/edit before actions fire

The system prompt becomes configurable per user — describing their preferences, clients, and desired workflows. The agent figures out the tool calls.

Architecture at this stage:
```
User prompt (natural language workflow definition)
    ↓
System prompt (user context + preferences from Store)
    ↓
LLM (sees all tools from all connected MCP servers)
    ↓
Tool calls (Gmail draft + Notion task + Slack message + ...)
    ↓
HITL approval → execute → update memory
```
