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
    # StdioServerParameters tells the MCP SDK how to launch the server.                        
    # Same info as before, just in a different container.                                    
    server_params = StdioServerParameters(                                                     
        command="python3",
        args=["gmail_mcp_server.py"],                                                          
    )                                                                                        

    # stdio_client() launches the subprocess and gives us read/write streams.                  
    # ClientSession wraps those streams into the MCP protocol (JSON-RPC).
    # Both are async context managers — the server stays alive for the                         
    # entire duration of the nested `async with` blocks.                                       
    async with stdio_client(server_params) as (read, write):                                   
        async with ClientSession(read, write) as session:                                      
            # Initialize the MCP handshake (capabilities exchange).                            
            # This is where client and server agree on protocol version                        
            # and what features each side supports.                                            
            await session.initialize()                                                         
                                                                                            
            # load_mcp_tools binds each tool to THIS session.                                  
            # When a tool is called later, it uses this live connection                      
            # instead of spawning a new process. One server, one connection.                   
            tools = await load_mcp_tools(session)                                              
                                                                                                
            # build_graph is unchanged — it just receives tools.                               
            graph = build_graph(tools)                                                       
                                                                                                
            stubs = list_messages_by_label(LABEL, max_results=MAX_EMAILS)                    
            print(f"Found {len(stubs)} emails labeled '{LABEL}'\n")
                                                                                                
            for stub in stubs:
                email = get_message(stub["id"])                                                
                                                                                            
                config = {"configurable": {"thread_id": email["message_id"]}}
                result = await graph.ainvoke({"email_input": email}, config)
                                                                                                
                print(f"From:           {email['from_addr']}")
                print(f"Subject:        {email['subject']}")                                   
                print(f"Classification: {result['classification']}")                         
                print(f"Reasoning:      {result['reasoning']}")
                if result.get("draft_id"):
                    print(f"Draft ID:       {result['draft_id']}")                             
                print("-" * 70)
                                                                                                
                                                                                            
if __name__ == "__main__":
    asyncio.run(main())