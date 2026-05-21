# gmail-triage

LangGraph agent that pulls Gmail messages by label, classifies each one as `ignore`, `notify`, or `respond`, and drafts replies for `respond` emails via MCP tools.

## Entry point

`main.py` — async entry point. Connects to the Gmail MCP server (stdio transport), loads MCP tools as LangChain tools, builds the graph, then loops over emails under the hard-coded `LABEL` (currently `0-Clients/client-cynthia`, capped at `MAX_EMAILS`). Uses `graph.ainvoke()` per email. The MCP session stays alive for the entire run.

## Graph flow

```
START → triage_router → (respond?) → response_agent ⇄ tool_node → END
                       → (ignore/notify?) → END
```

- `triage_router` classifies and routes via `Command(goto=...)`
- `response_agent` drafts replies using an LLM with MCP tools bound
- `tool_node` (`ToolNode`) executes MCP tool calls (ReAct loop with `tools_condition`)

## Module map

- `main.py` — async entry point. Owns the MCP client lifecycle: spawns `gmail_mcp_server.py` via `stdio_client`, creates a `ClientSession`, loads tools with `load_mcp_tools(session)`, passes them to `build_graph(tools)`.
- `graph.py` — `build_graph(tools)` builds a `StateGraph(State)` with three nodes (`triage_router`, `response_agent`, `tools`). Compiled with `InMemorySaver`. Takes MCP tools as a parameter.
- `nodes.py` — `triage_router` calls `gpt-5-mini` via `init_chat_model` with `with_structured_output(ClassificationOutput)`. Returns `Command(goto="response_agent"|"__end__")` based on classification.
- `response_node.py` — `make_response_agent(tools)` factory returns the `response_agent` node. Uses `bind_tools(tools)` for tool-calling. Passes message history on subsequent calls so the LLM sees tool results and stops the ReAct loop.
- `state.py` — `EmailInput` TypedDict (`message_id`, `thread_id`, `subject`, `from_addr`, `body`) and `State(MessagesState)` adding `email_input`, `classification`, `reasoning`, `draft_id`.
- `prompts.py` — `TRIAGE_SYSTEM` (classifier prompt, hard-codes Ed's three clients) and `RESPONSE_SYSTEM` (draft-writing prompt, references `create_draft` MCP tool).
- `gmail_mcp_server.py` — FastMCP server wrapping `gmail_client.py`. Exposes three MCP tools: `list_messages`, `get_message`, `create_draft`. Runs on stdio transport.
- `gmail_client.py` — Google API wrapper. `list_messages_by_label`, `get_message`, `create_email_draft`. OAuth flow uses `credentials.json` + `token.json` with scope `gmail.modify`.
- `tools.py` — RETIRED. Old LangChain `@tool`s replaced by MCP tools. Still in directory but not imported.
- `smoke_test.py` — minimal check that the Gmail client can list + fetch one message.
- `MCP_INTEGRATION_NOTES.md` — full build log documenting the MCP integration, all challenges, and lessons learned.

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

## Roadmap

### Phase 1: Gmail labeling via MCP

Add automatic Gmail labeling after triage. Every email gets a label (`triage/ignore`, `triage/notify`, `triage/respond`) regardless of classification.

- Add `label_message(message_id, label_name)` to `gmail_client.py`
- Expose it as a `label_message` tool in `gmail_mcp_server.py`
- Add a `label_node` to the graph that runs for all emails, before the respond/end routing

Target graph:
```
START → triage_router → label_node → (respond?) → response_agent ⇄ tool_node → END
                                    → (ignore/notify?) → END
```

### Phase 2: Human-in-the-loop (HITL)

Add human approval before the agent takes action (drafting replies, applying labels).

- Use LangGraph's `interrupt()` to pause the graph mid-execution
- The agent presents its plan ("I want to draft this reply to Cynthia about X") and waits
- The human approves, edits instructions, or skips
- The graph resumes (or doesn't) based on the human's response
- Placement: between `label_node` and `response_agent`

LangGraph concept: `interrupt()` suspends graph execution and returns a value to the caller. The caller resumes with `graph.ainvoke(Command(resume=...))` passing the human's decision. The checkpointer preserves state across the pause.

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
