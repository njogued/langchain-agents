# MCP + LangChain Integration: Full Build Log

## Overview

This document covers the process of integrating MCP (Model Context Protocol) tools into an existing LangGraph email triage agent. The goal was to replace hand-written LangChain `@tool` functions with tools served over MCP, learning both the server and client sides of the protocol.

**Date:** 2026-05-18
**Starting point:** A working triage-only agent that classified emails but took no action.
**End result:** A full pipeline that classifies emails and drafts replies via MCP tools.

---

## What is MCP?

MCP (Model Context Protocol) is a standard protocol for exposing tools, resources, and prompts to AI models. Think of it like a REST API, but instead of HTTP endpoints you declare **tools** with typed inputs and descriptions. Any MCP client — Claude Desktop, Claude Code, or a LangGraph agent — can connect and use those tools.

Key concepts:
- **MCP Server** — a process that exposes tools. Can be written in Python (FastMCP), TypeScript, etc.
- **MCP Client** — connects to a server, discovers tools, and calls them.
- **Transport** — how client and server communicate: `stdio` (subprocess pipes), `SSE` (HTTP streaming), or `Streamable HTTP`.

## How MCP connects to LangChain

The bridge is `langchain-mcp-adapters`. It converts MCP tools into standard LangChain `BaseTool` objects. Once converted, they're indistinguishable from regular `@tool`-decorated functions — they work with `model.bind_tools()`, `ToolNode`, `tools_condition`, and everything else in the LangChain/LangGraph ecosystem.

```
MCP Server (FastMCP)
    ↕ stdio (JSON-RPC over stdin/stdout)
MCP Client (mcp SDK)
    ↕ load_mcp_tools(session)
LangChain Tools (BaseTool)
    ↕ bind_tools() / ToolNode
LangGraph Agent
```

---

## Architecture Before & After

### Before (triage only)
```
START → triage_router → END
```
- Single node classified emails as ignore/notify/respond
- No action taken on any classification
- `tools.py` had `@tool` functions defined but not wired in

### After (triage + MCP-powered response)
```
START → triage_router → (respond?) → response_agent ⇄ tool_node → END
                       → (ignore/notify?) → END
```
- `triage_router` classifies and conditionally routes
- `response_agent` uses an LLM with MCP tools bound to draft replies
- `tool_node` (LangGraph's `ToolNode`) executes MCP tool calls
- ReAct loop: response_agent → tool_node → response_agent → END

---

## New & Modified Files

### New: `gmail_mcp_server.py` — The MCP Server

Built with [FastMCP](https://gofastmcp.com), this wraps existing `gmail_client.py` functions as MCP tools.

```python
from fastmcp import FastMCP
import gmail_client

mcp = FastMCP("gmail-tools")

@mcp.tool()
def list_messages(label_name: str, max_results: int = 5) -> list[dict]:
    """List email message stubs for a given Gmail label."""
    return gmail_client.list_messages_by_label(label_name, max_results)

@mcp.tool()
def get_message(message_id: str) -> dict:
    """Fetch a full email by message ID."""
    return gmail_client.get_message(message_id)

@mcp.tool()
def create_draft(to: str, subject: str, content: str, thread_id: str) -> str:
    """Create a Gmail draft reply in an existing thread."""
    return gmail_client.create_email_draft(to, subject, content, thread_id)

if __name__ == "__main__":
    mcp.run()
```

**Key points:**
- `@mcp.tool()` registers a function as an MCP tool. FastMCP auto-generates JSON Schema from type hints and uses the docstring as the tool description.
- The functions are thin wrappers — no new logic, just protocol adaptation.
- `mcp.run()` starts a stdio transport loop (read JSON-RPC from stdin, dispatch, write to stdout).
- **Install:** `pip install fastmcp`

### New: `response_node.py` — The Response Agent Node

```python
from langchain.chat_models import init_chat_model
from prompts import RESPONSE_SYSTEM
from state import State

response_llm = init_chat_model("gpt-5-mini", model_provider="openai", temperature=0)

def make_response_agent(tools):
    llm_with_tools = response_llm.bind_tools(tools)

    def response_agent(state: State):
        email = state["email_input"]
        if state["messages"]:
            # Subsequent calls: pass full history so LLM sees tool results
            response = llm_with_tools.invoke(
                [{"role": "system", "content": RESPONSE_SYSTEM}]
                + state["messages"]
            )
        else:
            # First call: seed with email content
            user_prompt = (
                f"Reply to this email.\n\n"
                f"From: {email['from_addr']}\n"
                f"Subject: {email['subject']}\n"
                f"Thread ID: {email['thread_id']}\n\n"
                f"{email['body']}"
            )
            response = llm_with_tools.invoke([
                {"role": "system", "content": RESPONSE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ])
        return {"messages": [response]}

    return response_agent
```

**Key points:**
- **Factory pattern** — `make_response_agent(tools)` returns the node function. Needed because MCP tools are loaded asynchronously at startup; we can't bind them at import time.
- **`bind_tools(tools)`** — tells the LLM what tools exist. The LLM receives tool schemas and can emit `tool_call` in its response. The tools came from MCP but look identical to any LangChain tool.
- **Message history is critical** — without passing `state["messages"]` on subsequent calls, the LLM never sees tool results and loops forever (see Challenges section).

### Modified: `graph.py` — Accepts Tools as Parameter

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

from nodes import triage_router
from response_node import make_response_agent
from state import State

def build_graph(tools):
    workflow = StateGraph(State)
    workflow.add_node("triage_router", triage_router)
    workflow.add_node("response_agent", make_response_agent(tools))
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "triage_router")
    workflow.add_conditional_edges("response_agent", tools_condition)
    workflow.add_edge("tools", "response_agent")

    return workflow.compile(checkpointer=InMemorySaver())
```

**Key points:**
- `build_graph` is now a regular sync function that takes `tools` as a parameter. MCP lifecycle management moved to `main.py`.
- `ToolNode(tools)` — LangGraph built-in that executes tool calls from LLM responses. Works with any LangChain tools, MCP or otherwise.
- `tools_condition` — built-in conditional edge. Routes to `"tools"` if the LLM response has tool calls, `END` if not. Creates the ReAct loop.
- `triage_router` routes via `Command(goto=...)` — returns `"response_agent"` for respond, `"__end__"` for ignore/notify.

### Modified: `main.py` — Owns MCP Client Lifecycle

```python
import asyncio
from dotenv import load_dotenv
load_dotenv()

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

from gmail_client import get_message, list_messages_by_label
from graph import build_graph

LABEL = "0-Clients/client-cynthia"
MAX_EMAILS = 5

async def main():
    server_params = StdioServerParameters(
        command="python3",
        args=["gmail_mcp_server.py"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            graph = build_graph(tools)

            stubs = list_messages_by_label(LABEL, max_results=MAX_EMAILS)
            for stub in stubs:
                email = get_message(stub["id"])
                config = {"configurable": {"thread_id": email["message_id"]}}
                result = await graph.ainvoke({"email_input": email}, config)
                # ... print results ...

if __name__ == "__main__":
    asyncio.run(main())
```

**Key points:**
- Uses the **raw `mcp` SDK** (not `MultiServerMCPClient`) for a persistent session. See Challenges section for why.
- `stdio_client(server_params)` spawns the MCP server as a subprocess **once**.
- `ClientSession` wraps the streams into JSON-RPC.
- `session.initialize()` performs the MCP handshake.
- `load_mcp_tools(session)` converts MCP tools to LangChain tools **bound to this session**. All tool calls reuse the same connection.
- Everything is `async` because MCP communication is async. `graph.ainvoke()` instead of `graph.invoke()`.

### Modified: `nodes.py` — Conditional Routing

Only change: `goto` is now conditional.

```python
goto = "response_agent" if result.classification == "respond" else "__end__"
```

### Modified: `prompts.py` — Updated Tool Names

```python
RESPONSE_SYSTEM = """You draft email replies in Ed's voice: brief, warm, direct. No corporate filler. No em dashes.

Use create_draft to draft your reply. Always pass the original thread_id so the draft becomes a real reply, not a new thread. When the draft is created, confirm with a one-line summary."""
```

Changed `write_email_draft` → `create_draft` (the MCP tool name) and removed reference to `Done` tool (doesn't exist in MCP).

### Modified: `state.py` — Added draft_id field

```python
class State(MessagesState):
    email_input: EmailInput
    classification: Literal["ignore", "notify", "respond"] | None
    reasoning: str | None
    draft_id: str | None          # NEW
```

### Retired: `tools.py`

Still in the directory but no longer imported. The `@tool`-decorated `write_email_draft` and `Done` functions are replaced by MCP tools from `gmail_mcp_server.py`.

---

## Dependencies Added

```bash
pip install fastmcp               # MCP server framework
pip install langchain-mcp-adapters  # MCP-to-LangChain tool converter
```

The `mcp` Python SDK is installed automatically as a dependency of both packages.

---

## Challenges & Lessons Learned

### 1. Async everywhere — `ainvoke` not `invoke`

**Problem:** `StructuredTool does not support sync invocation`

MCP tools communicate over async pipes. `graph.invoke()` runs nodes synchronously, so `ToolNode` tried to call MCP tools synchronously and crashed.

**Fix:** Use `graph.ainvoke()` which runs everything in async mode. The entire call chain must be async: `asyncio.run(main())` → `await graph.ainvoke()` → `ToolNode` calls tools asynchronously.

### 2. Unawaited coroutine at module level

**Problem:** `RuntimeWarning: coroutine 'build_graph' was never awaited`

The old `graph.py` had `graph = build_graph()` at module level. When `build_graph` became `async`, this line created a coroutine object instead of calling the function — and it ran at import time.

**Fix:** Remove the module-level call. Call `await build_graph()` explicitly in `main()`.

### 3. MultiServerMCPClient spawns a new server per tool call

**Problem:** FastMCP banner appeared 3+ times. Each tool call spawned a fresh subprocess, connected, called the tool, then tore down. This caused `BrokenResourceError` when the subprocess exited before the client finished reading.

**What we tried:**
- `async with MultiServerMCPClient(...) as client:` — not supported in `langchain-mcp-adapters >= 0.1.0`. Raises `NotImplementedError`.
- `MultiServerMCPClient(...)` without context manager — tools use ephemeral per-call sessions. Works for HTTP/SSE but unreliable for stdio (process spawn overhead + cleanup race conditions).

**Fix:** Bypass `MultiServerMCPClient` entirely. Use the raw `mcp` SDK:

```python
async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await load_mcp_tools(session)
        # ... use tools within this block ...
```

This keeps **one server process alive** for the entire program. `load_mcp_tools(session)` binds tools to the live session — no respawning.

**Lesson:** `MultiServerMCPClient` is a convenience wrapper best suited for HTTP/SSE transports. For stdio, use the raw SDK to control the subprocess lifecycle explicitly.

### 4. Infinite ReAct loop — LLM never sees tool results

**Problem:** After the `response_agent` called `create_draft` via MCP, the tool executed successfully, but the LLM called it again. And again. Infinite loop.

**Root cause:** The `response_agent` function rebuilt the prompt from scratch every time (system + user message about the email). It never read `state["messages"]`, which contained the prior LLM response and the `ToolMessage` with the tool result. So on each iteration, the LLM saw the email for the "first time" and decided to draft again.

**Fix:** Check `if state["messages"]` — if there's history, pass the full message list so the LLM can see what already happened:

```python
if state["messages"]:
    response = llm_with_tools.invoke(
        [{"role": "system", "content": RESPONSE_SYSTEM}]
        + state["messages"]
    )
else:
    # First time: seed with email content
    response = llm_with_tools.invoke([system_msg, user_msg])
```

**Lesson:** In a ReAct loop, the agent node must include conversation history. The `ToolNode` adds `ToolMessage` results to `state["messages"]`, but the agent node must actually *read* them on the next iteration.

### 5. Missing return statement

**Problem:** `ValueError: No messages found in input state to tool_edge`

**Root cause:** The `return {"messages": [response]}` line in `response_agent` was accidentally commented out. The function returned `None`, so no messages were added to state. `tools_condition` then found an empty messages list and crashed.

**Lesson:** When a LangGraph node needs to update state, it must explicitly return the update dict. A missing return means the state doesn't change.

### 6. Tool name mismatch in prompts

**Problem:** The `RESPONSE_SYSTEM` prompt referenced `write_email_draft` and `Done` — tools that existed in the old `tools.py` but not in the MCP server. The MCP tool is called `create_draft`.

**Fix:** Update the prompt to use the actual MCP tool names. The LLM can only call tools it knows about; if the prompt names don't match the bound tool names, the LLM either hallucinates a tool call (which ToolNode can't execute) or gets confused.

---

## Key Takeaways

1. **MCP is a protocol layer, not a replacement for LangChain.** MCP serves tools; LangChain/LangGraph orchestrates how an agent uses them. They complement each other.

2. **`langchain-mcp-adapters` is the glue.** `load_mcp_tools(session)` converts MCP tools into LangChain `BaseTool` objects. After conversion, they work everywhere LangChain tools work.

3. **For stdio transport, use the raw `mcp` SDK.** `MultiServerMCPClient` creates ephemeral connections per operation, which means a new subprocess per tool call. For stdio, you want a persistent session via `stdio_client()` + `ClientSession()`.

4. **The ReAct pattern requires message history.** If an agent node in a tool-calling loop doesn't include prior messages, the LLM has no memory of what it already did and will repeat actions indefinitely.

5. **Building both sides (server + client) is valuable.** Writing the FastMCP server teaches how tools are declared and exposed. Wiring the client teaches how tools are discovered and consumed. Together, they demystify the full MCP lifecycle.

---

## Running

```bash
# Install dependencies
pip install fastmcp langchain-mcp-adapters

# Run the full pipeline
python main.py

# Test MCP server standalone (optional)
fastmcp dev inspector gmail_mcp_server.py
```
