---
description: Start the BDI verification MCP server for agent integration
---

# Start MCP Server Workflow

// turbo-all

1. Activate the virtual environment:
```bash
source /Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/.venv/bin/activate
```

2. Start the MCP server in stdio mode:
```bash
cd /Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver && python -m src.mcp_server_bdi
```

3. The server is now running and ready to accept `generate_verified_plan` tool calls.
