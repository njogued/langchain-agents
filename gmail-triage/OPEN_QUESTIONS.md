# Open questions / loops

Captured from session on 2026-05-18. Pick up next session.

---

## 1. Visualizing the graph

Running `main.py` doesn't render anything. Options discussed:

- **Quickest:** add `print(graph.get_graph().draw_mermaid())` after `build_graph(tools)` in `main.py`, paste into mermaid.live.
- **PNG:** `graph.get_graph().draw_mermaid_png(output_file_path="graph.png")`.
- **LangSmith trace view:** inside an individual trace there should be a "Graph" tab showing the executed path. Couldn't confirm whether it's appearing for these runs — worth checking.
- **LangGraph Studio** (best UX): needs a `langgraph.json` config and `langgraph dev`. Blocker: `build_graph` takes `tools` as an arg, so Studio can't invoke it directly. Would need a zero-arg wrapper that sets up the MCP session.

**Next step:** decide between the mermaid print (5 min) and Studio setup (real investment). Studio is the right long-term call.

---

## 2. thread_id should not live in the prompt

Currently the `RESPONSE_SYSTEM` prompt and the user message both ask the LLM to pass `thread_id` into `create_draft`. But `thread_id` is already in `state["email_input"]["thread_id"]` — making the LLM responsible for plumbing it is non-deterministic for a field with exactly one correct value.

**Options:**
- **A (recommended):** wrap `create_draft` so `thread_id` is pre-filled from state and hidden from the LLM's tool schema entirely. Drop the "always pass thread_id" line from the prompt.
- **B:** keep tool as-is, intercept tool calls in a custom ToolNode to overwrite `args["thread_id"]` with the state value.

**Next step:** implement Option A. See response_node.py:50 and prompts.py for the touch points.

---

## 3. Double `response_agent` call per run

LangSmith trace shows the pattern:
```
response_agent #1  → emits create_draft tool_call    (6.74s, 2K tokens)
tools              → executes                        (0.72s)
response_agent #2  → observes result, emits text     (1.62s, 555 tokens)
```

This is standard ReAct ("act then observe"). The second call is the LLM acknowledging the tool result and deciding nothing more to do. For *this* graph it's wasteful — after `create_draft` there's nothing else to decide.

**Side note worth checking:** the trace showed `tools_condition` lighting up again under `response_agent #2`. If the second call is re-emitting a tool call (i.e. trying to re-draft), that's likely the same prompt-clarity / thread_id issue from #2 — the LLM doesn't realize it already drafted. Confirm by reading the actual message content from `response_agent #2`.

**Resolution depends on #4.** Don't optimize this until the architecture decision is made.

---

## 4. Architecture for multi-tool workflows (the big one)

Question: when adding more tools (label, Slack, Notion, Monday), should the agent still be one ReAct loop, or should there be a planner?

Three shapes discussed:

- **Shape A — Current ReAct expanded:** bind all tools to `response_agent`, let it pick one at a time. Same structure as today, just more tools.
- **Shape B — Triage as planner:** `triage_router` outputs `{classification, actions: [...]}`, an executor runs them deterministically.
- **Shape C — Separate planner node:** triage answers "does this matter?", a new planner node owns "what should we do?" Structurally identical to A, cleaner separation of concerns.

**Recommendation:** A or C. They're the same pattern under different names. Shape B works against Phase 5 (natural-language workflow definitions) because it removes the LLM from the action-by-action loop.

**Don't decide yet.** Drop in *one* more tool first (Phase 1's `label_message` is the obvious next move) inside the existing ReAct loop. Observe behavior. Then decide if a planner is warranted.

---

## 5. Resolved this session (for reference, no action)

- **OpenAI Responses API vs Chat Completions:** stick with Chat Completions. The Responses API's value (server-side state, hosted tools, reasoning persistence) duplicates or conflicts with LangGraph's role as orchestrator. Revisit only if switching to a reasoning model (`gpt-5` proper) for the response agent.
