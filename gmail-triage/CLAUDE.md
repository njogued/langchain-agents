# gmail-triage

LangGraph agent that pulls Gmail messages by label and classifies each one as `ignore`, `notify`, or `respond`. Draft-writing is scaffolded but not wired into the graph yet.

## Entry point

`main.py` — lists messages under the hard-coded `LABEL` (currently `0-Clients/client-cynthia`, capped at `MAX_EMAILS`), fetches each via `gmail_client.get_message`, then runs `graph.invoke({"email_input": email}, config)` per message. `thread_id` in the LangGraph config is the Gmail `message_id` so the in-memory checkpointer keys per email.

## Module map

- `graph.py` — builds a `StateGraph(State)` with a single `triage_router` node from `START`, compiled with `InMemorySaver`. The compiled graph is exported as `graph`.
- `nodes.py` — `triage_router` calls `gpt-5-mini` via `init_chat_model` (`openai`, `temperature=0`) with `with_structured_output(ClassificationOutput)`. Returns a `Command(goto="__end__", update=...)` populating `classification` and `reasoning`.
- `state.py` — `EmailInput` TypedDict (`message_id`, `thread_id`, `subject`, `from_addr`, `body`) and `State(MessagesState)` adding `email_input`, `classification`, `reasoning`.
- `prompts.py` — `TRIAGE_SYSTEM` (the classifier prompt, hard-codes Ed's three clients: Marc/Almedia, Michael/Storied, Cynthia Scott) and `RESPONSE_SYSTEM` (draft-writing prompt, currently unused).
- `gmail_client.py` — Google API wrapper. `list_messages_by_label`, `get_message` (normalizes payload + walks MIME parts for `text/plain`), `create_email_draft(to, subject, content, thread_id)`. OAuth flow uses `credentials.json` + `token.json` with scope `gmail.modify`.
- `tools.py` — LangChain `@tool`s `write_email_draft` (wraps `gmail_client.create_email_draft`, requires `thread_id`) and `Done`. Defined but not yet wired into the graph.
- `smoke_test.py` — minimal check that the Gmail client can list + fetch one message under the Cynthia label.

## Running

```
python main.py        # full triage loop
python smoke_test.py  # Gmail auth + fetch sanity check
```

First run triggers the OAuth browser flow and writes `token.json`.

## Secrets

`.env`, `credentials.json`, `token.json` are all local and gitignored-worthy — do not commit. `.env` holds the OpenAI key loaded by `load_dotenv()` in `main.py` before any other import.

## Classification contract

`ClassificationOutput` (Pydantic) requires `reasoning` first, then `classification` ∈ `{"ignore", "notify", "respond"}`. The prompt instructs reasoning-then-label; keep that order if you change the schema or the LLM may degrade.

## Known gaps

- `tools.py` is not imported anywhere — drafting is not yet a graph node.
- `LABEL` and `MAX_EMAILS` are hard-coded in `main.py`.
