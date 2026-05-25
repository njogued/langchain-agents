"""
Node that drafts email replies using MCP tools.                                            
This node receives emails classified as "respond" and uses an LLM                          
with MCP-provided Gmail tools to draft a reply.
"""

from langchain.chat_models import init_chat_model
from prompts import RESPONSE_SYSTEM
from state import State

# set up an LLM instance for the response agent that handles tool calling by deciding when and how to call MCP tools
response_llm = init_chat_model("gpt-5-mini", model_provider="openai", temperature=0)


def make_response_agent(tools):
    """                                                                                  
    Factory that creates the response_agent node with MCP tools bound.
                                                                                            
    Why a factory? Because the MCP tools are loaded asynchronously at                      
    startup (from the MCP server). We can't bind them at import time.                      
    So graph.py will call this function after loading tools, and pass                      
    the returned node function to StateGraph.add_node().                                   
    """
    # bind_tools() tells LLM about available tools
    # when invoked, the LLM can choose to emit a tool_call in its response
    llm_with_tools = response_llm.bind_tools(tools)

    def response_agent(state: State):
        """Build a prompt from the email and let the LLM decide to draft a reply"""
        email = state["email_input"]
        print(f"  [respond] Drafting reply to: {email['from_addr']}")
        # Check if we already have messages (i.e., we've been here before                      
        # and the tool already ran). If so, pass the full history so the
        # LLM can see the tool result and decide to stop.                                      
        if state["messages"]:                                                                  
            # Messages already contain: our prior LLM response + ToolMessage
            # with the result. Just pass them through so the LLM sees                          
            # "I already drafted the reply, tool returned draft ID X" and                      
            # responds with text (no tool call) → tools_condition routes to END.               
            response = llm_with_tools.invoke(                                                  
                [{"role": "system", "content": RESPONSE_SYSTEM}]                               
                + state["messages"]                                                            
            )                                                                                
        else:
            # First time here — seed with the email content.
            user_prompt = (
                f"Reply to this email.\n\n"
                f"From: {email['from_addr']}\n"
                f"Subject: {email['subject']}\n"
                f"Thread ID: {email['thread_id']}\n"
                f"RFC Message-ID: {email.get('rfc_message_id', '')}\n"
                f"References: {email.get('references', '')}\n\n"
                f"{email['body']}"
            )
            response = llm_with_tools.invoke(
                [
                    {"role": "system", "content": RESPONSE_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ]
            )
            print(f"  [respond] tool_calls: {bool(response.tool_calls)}")
            return {"messages": [
                {"role": "user", "content": user_prompt},
                response,
            ]}
        print(f"  [respond] tool_calls: {bool(response.tool_calls)}")
        return {"messages": [response]}
    return response_agent