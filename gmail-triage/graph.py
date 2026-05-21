from langgraph.checkpoint.memory import InMemorySaver                                        
from langgraph.graph import StateGraph, START                                                  
from langgraph.prebuilt import ToolNode, tools_condition
                                                                                                
from nodes import triage_router                                                                
from response_node import make_response_agent
from state import State                                                                        
                                                                                            
                                                                                                
def build_graph(tools):                                                                        
    """
    Build the triage graph. Now synchronous — the async MCP setup                              
    moves to main.py which passes the loaded tools in.                                       
    """                                     
    workflow = StateGraph(State)        
                                                                                                
    workflow.add_node("triage_router", triage_router)                                          
                                                                                                
    response_agent = make_response_agent(tools)                                                
    workflow.add_node("response_agent", response_agent)                                        

    workflow.add_node("tools", ToolNode(tools))                                                
                                                                                            
    workflow.add_edge(START, "triage_router")
    workflow.add_conditional_edges("response_agent", tools_condition)                          
    workflow.add_edge("tools", "response_agent")
                                                                                                
    return workflow.compile(checkpointer=InMemorySaver())  