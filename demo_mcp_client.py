import asyncio
import sys
import os

# usage: python demo_mcp_client.py

async def run_demo():
    print("🚀 Starting BDI Verification Demo...")
    
    # We will run the server as a subprocess
    server_script = os.path.join(os.getcwd(), "src", "mcp_server_bdi.py")
    
    print(f"🔌 Connecting to MCP Server at: {server_script}")
    
    # Use mcp.client (simplified usage for demo)
    # Since fastmcp simplifies server creation, we can use stdio client to talk to it.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=os.environ.copy()
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List tools
            tools = await session.list_tools()
            print(f"🛠️  Available Tools: {[t.name for t in tools.tools]}")
            
            # Call the tool
            print("\n📝 Requesting Verified Plan: 'Stack block A on block B'...")
            
            result = await session.call_tool(
                name="generate_verified_plan",
                arguments={
                    "goal": "stack a on b",
                    "domain": "blocksworld",
                    "context": "on(a, table), on(b, table), clear(a), clear(b), handempty",
                    "pddl_domain_file": "planbench_data/blocksworld/domain.pddl",
                    "pddl_problem_file": "planbench_data/blocksworld/problem.pddl"
                }
            )
            
            print("\n✅ Verification Result:")
            print("==================================================")
            # Result content is a list of TextContent or ImageContent
            for content in result.content:
                if content.type == 'text':
                    print(content.text)
            print("==================================================")

if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except ImportError:
        print("❌ Error: 'mcp' library not found. Please run: pip install mcp")
    except Exception as e:
        print(f"❌ Error: {e}")
