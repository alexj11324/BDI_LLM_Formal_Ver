# Ralph Setup and Usage Guide

## Quick Start

### 1. Load Environment Variables

Before running Ralph, source the environment file:

```bash
source .ralph_env.sh
```

This will expose the API key to Ralph and all child processes.

### 2. Start Ralph Monitor

```bash
ralph --monitor
```

Or reset and start fresh:

```bash
ralph --reset-session
ralph --monitor
```

## Configuration Summary

### API Access
- **API Key**: `sk-CAMQPAfhTgcWPrFfxm_1Zg` (CMU AI Gateway)
- **Base URL**: `https://ai-gateway.andrew.cmu.edu/v1`
- **Model**: `claude-opus-4-20250514-v1:0`

### Allowed Tools (Updated)
Ralph can now execute:
- All Bash commands: `Bash(*)`
- File operations: `Write`, `Read`, `Edit`
- Search: `Glob`, `Grep`

### Files Created
1. `.env` - Environment variables (gitignored)
2. `.ralph_env.sh` - Shell script to export env vars for Ralph
3. `.ralphrc` - Ralph configuration (updated ALLOWED_TOOLS)

## Alternative: Direct Export

If you prefer not to use the script:

```bash
export OPENAI_API_KEY=sk-CAMQPAfhTgcWPrFfxm_1Zg
export OPENAI_API_BASE=https://ai-gateway.andrew.cmu.edu/v1
ralph --monitor
```

## Verification

Test that the environment is configured correctly:

```bash
# Should show the API key
echo $OPENAI_API_KEY

# Run a simple test
python -c "import os; print(os.environ.get('OPENAI_API_KEY', 'NOT SET'))"
```

## Troubleshooting

**"OPENAI_API_KEY environment variable is not set"**
- Run `source .ralph_env.sh` first
- Or manually export the variables

**"Claude Code was denied permission to execute commands"**
- Fixed: `.ralphrc` now includes `ALLOWED_TOOLS="Bash(*)"`
- Run `ralph --reset-session` to clear stale session state

**Ralph not seeing API key**
- Environment variables must be set in the same shell session
- Use `source .ralph_env.sh` (NOT `bash .ralph_env.sh`)
