# langchain-agents

## Building ambient agents using langchain

### Agents v. Workflows
- Agents can make independent decisions on tools to call or actions to take, while workflows follow pre-defined patterns
- Agents take many more actions that workflows, can calls any tools it has access to, in any sequence
Agent - tool takes actions in a Loop, (Call a tool, get execution result, return output to the LLM for it to decide the next step)

### When to use Workflow v. Agent
- If action sequence is easy to enumerate (if you can easily chart out the control flow) -> use a workflow
- If latency and costs are critical consideration -> use a workflow
- If you need varied execution patterns, and need the agent to take independent decisions -> use a workflow
- Workflows and Agents require tradeoffs in linear control flow vs flexible decision making (agency vs. predictability)

## LangGraph Components
- Nodes (units of work)
- Edges (transition between nodes)

## Memory in LangGraph
- LangGraph has long-term state management - You can save a state and access it later
- Persistence layer that allows human-in-the-loop (allows checkpointing)

## LangGraph vs LangSmith vs LangChain
- LangSmith - Observability (Tracing and Evaluation)
- LangChain - Standard interface for chat models (import init_chat_model and invoke)
- LangGraph - Orchestration and application control flow


### Tool Calling
- Calls tools from Python functions using the tool decorator

```
from langchain.tools import tool

@tool
def write_email(to: str, subject: str, content: str) -> str: 
```

- You can connect tools to a chat model using the bind tools method, 
```model_with_tools = llm.bind_tools([write_email], tool_choice="any", parallel_tool_calls=False)```

- The foundational element of an agent is that LLMs can call tools


### FYIs
- **Tool Decorator:** @tool


State -> Workflow -> Node -> Edge -> Node -> END

LangChain Pre-built abstraction method
- Can be used to call the tool calling loop

Checkpoints
- Pass config into the invoke method, referencing the thread ID into the config

Interrupt
- Can be used to request feedback (human in the Loop)

LangSmith traceability
- Due to the LangSmith Env variable below, you can trace all the actions taken via agents and/or tools.
```LANGSMITH_TRACING=true```

Deployment
- Set up the app project with a structure including the src files, env files, pyproject.toml, and langgraph.json
- Ensure you have a langgraph.json file that is a config file for LangGraph
