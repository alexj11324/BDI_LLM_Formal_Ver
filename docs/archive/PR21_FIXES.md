# PR #21 Review Issues and Fixes

This document outlines the security and bug risk issues identified in PR #21 and the fixes that need to be applied.

## Status

### ✅ Completed Fixes

1. **DSPy Configuration Idempotency** (src/bdi_llm/planner.py)
   - **Issue**: `configure_dspy()` was called on every BDIPlanner instantiation, causing unnecessary overhead
   - **Fix Applied**: Added module-level `_dspy_configured` flag to make configuration idempotent
   - **Impact**: Performance improvement, prevents repeated global reconfiguration

### 🔴 Remaining Fixes for PR #21 Branch

The following fixes apply to files in the `mcp-server-refactor-11310542235390350219` branch that are not present in the current branch:

#### 2. Hard-coded Domain in IntegratedVerifier (src/interfaces/mcp_server.py:33)
   - **Issue**: `IntegratedVerifier(domain="blocksworld")` is hard-coded, limiting correctness for other domains
   - **Fix Required**:
     ```python
     # Option 1: Add domain parameter
     def _verify_plan_logic(domain_pddl, problem_pddl, plan_actions, domain="blocksworld"):
         verifier = IntegratedVerifier(domain=domain)

     # Option 2: Parse domain from PDDL
     def parse_domain_name(domain_pddl: str) -> str:
         # Extract domain name from (define (domain <name>) ...)
         match = re.search(r'\(domain\s+(\w+)\)', domain_pddl)
         return match.group(1) if match else "blocksworld"
     ```

#### 3. PDDL Action Construction Type-Safety (src/interfaces/mcp_server.py:76)
   - **Issue**: Building PDDL from `node.params.values()` is non-deterministic and type-fragile
   - **Fix Required**:
     ```python
     # Ensure string conversion and deterministic ordering
     params_str = " ".join(str(v) for v in node.params.values()) if node.params else ""
     # Or use a defined parameter order:
     if hasattr(node, 'param_order'):
         params_str = " ".join(str(node.params[k]) for k in node.param_order)
     ```

#### 4. Verification Result Structure (src/interfaces/mcp_server.py:129)
   - **Issue**: Using substring check `"Plan is VALID" in verification_result` is brittle
   - **Fix Required**:
     ```python
     # Make _verify_plan_logic return structured result
     def _verify_plan_logic(...) -> tuple[bool, str]:
         # ... verification logic ...
         return (is_valid, message)

     # In execute_verified_plan:
     is_valid, verification_message = _verify_plan_logic(...)
     if is_valid:
         # Execute command
     else:
         return f"Verification FAILED. {verification_message}"
     ```

#### 5. 🚨 Shell Command Injection (src/interfaces/mcp_server.py:123-129)
   - **Issue**: Using `subprocess.run(..., shell=True)` with user input is a critical security vulnerability
   - **Fix Required**:
     ```python
     import shlex

     # Option 1: Use shlex.split with shell=False (RECOMMENDED)
     def _execute_command(command: str) -> tuple[bool, str]:
         try:
             # Split command into argument list safely
             args = shlex.split(command)
             result = subprocess.run(
                 args,
                 shell=False,  # Safe execution
                 check=True,
                 capture_output=True,
                 text=True,
                 timeout=30  # Add timeout
             )
             return True, result.stdout
         except subprocess.CalledProcessError as e:
             return False, f"Command failed: {e.stderr}"
         except Exception as e:
             return False, f"Execution error: {str(e)}"

     # In execute_verified_plan:
     if is_valid:
         success, output = _execute_command(command_to_execute)
         if success:
             return f"Verification PASSED. Command Executed Successfully.\nOutput:\n{output}"
         else:
             return f"Verification PASSED but execution failed: {output}"
     ```

#### 6. 🚨 Dockerfile Security Hardening (Dockerfile)
   - **Issue**: Container runs as root, providing full privileges
   - **Fix Required**:
     ```dockerfile
     FROM python:3.11-slim

     # Install system dependencies
     RUN apt-get update && apt-get install -y \
         build-essential flex bison make git \
         && rm -rf /var/lib/apt/lists/*

     # Create non-root user BEFORE copying files
     RUN groupadd -r app && useradd -r -g app app

     # Set up application directory
     WORKDIR /app

     # Copy and install Python dependencies
     COPY requirements.txt .
     RUN pip install --no-cache-dir -r requirements.txt

     # Copy application code
     COPY --chown=app:app . .

     # Compile VAL validator
     RUN cd planbench_data/planner_tools/VAL && \
         make clean && make && \
         chmod +x validate && \
         chown app:app validate

     # Set environment
     ENV PYTHONPATH=/app
     ENV VAL_VALIDATOR_PATH=/app/planbench_data/planner_tools/VAL/validate

     # Switch to non-root user
     USER app

     # Run MCP server
     CMD ["python", "src/interfaces/mcp_server.py"]
     ```

## Testing Recommendations

After applying fixes:

1. **Test DSPy Configuration**:
   ```python
   from src.bdi_llm.planner import BDIPlanner
   # Multiple instantiations should not reconfigure DSPy
   p1 = BDIPlanner(domain="blocksworld")
   p2 = BDIPlanner(domain="logistics")
   p3 = BDIPlanner(domain="depots")
   ```

2. **Test Multi-Domain Verification**:
   ```python
   # Test with different domains
   for domain in ["blocksworld", "logistics", "depots"]:
       result = verify_plan(domain_pddl, problem_pddl, actions, domain=domain)
   ```

3. **Test Command Execution Security**:
   ```python
   # These should be safely handled or rejected:
   dangerous_commands = [
       "echo hello; rm -rf /",
       "ls `whoami`",
       "cat /etc/passwd",
   ]
   ```

4. **Test Docker as Non-Root**:
   ```bash
   docker build -t bdi-mcp .
   docker run bdi-mcp whoami  # Should output 'app', not 'root'
   ```

## Priority

1. 🔴 **CRITICAL**: Fix shell=True security issue (#5)
2. 🔴 **CRITICAL**: Add non-root user to Dockerfile (#6)
3. 🟡 **HIGH**: Make verification result structured (#4)
4. 🟡 **HIGH**: Fix hard-coded domain (#2)
5. 🟢 **MEDIUM**: Improve PDDL construction type-safety (#3)

## References

- PR #21: https://github.com/alexj11324/BDI_LLM_Formal_Ver/pull/21
- Sourcery AI Review: PR #21 comments
- Branch: `mcp-server-refactor-11310542235390350219`
