---
description: Generate and formally verify a BDI plan using PDDL/VAL before execution
---

# Verify Plan Workflow

1. Identify the goal and current state (beliefs) from the user's request.
2. Determine the PDDL domain (blocksworld, logistics, depots, or coding).
3. Call the `generate_verified_plan` MCP tool with the goal, context, and domain.
4. If the plan is verified, present the action sequence to the user.
5. If verification fails, analyze the error and attempt plan repair (up to 3 retries).
6. Always show the verification result (valid/invalid) before proceeding with execution.
