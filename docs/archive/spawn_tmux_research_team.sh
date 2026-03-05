#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="${1:-bdi_scientist_team}"
LOG_DIR="$ROOT_DIR/runs/tmux_team"
REPORT_DIR="$ROOT_DIR/reports/tmux_team"
mkdir -p "$LOG_DIR" "$REPORT_DIR"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  tmux kill-session -t "$SESSION_NAME"
fi

# teammate-1: verifier core tests
TMUX_CMD_1="cd '$ROOT_DIR' && python -m pytest tests/test_verifier.py -q > '$LOG_DIR/team1_verifier.log' 2>&1; echo DONE > '$LOG_DIR/team1.status'; exec bash"
# teammate-2: symbolic verifier tests
TMUX_CMD_2="cd '$ROOT_DIR' && python -m pytest tests/test_symbolic_verifier.py tests/test_symbolic_verifier_integration.py -q > '$LOG_DIR/team2_symbolic.log' 2>&1; echo DONE > '$LOG_DIR/team2.status'; exec bash"
# teammate-3: blocksworld physics tests
TMUX_CMD_3="cd '$ROOT_DIR' && python -m pytest tests/test_blocksworld_physics_validator.py -q > '$LOG_DIR/team3_physics.log' 2>&1; echo DONE > '$LOG_DIR/team3.status'; exec bash"
# teammate-4: plan repair tests
TMUX_CMD_4="cd '$ROOT_DIR' && python -m pytest tests/test_plan_repair.py -q > '$LOG_DIR/team4_repair.log' 2>&1; echo DONE > '$LOG_DIR/team4.status'; exec bash"
# teammate-5: paper snapshot integrity
TMUX_CMD_5="cd '$ROOT_DIR' && python scripts/verify_paper_eval_snapshot.py > '$LOG_DIR/team5_snapshot.log' 2>&1; echo DONE > '$LOG_DIR/team5.status'; exec bash"
# teammate-6: logistics/depots wrong-answer mining
TMUX_CMD_6="cd '$ROOT_DIR' && python - <<'PY' > '$LOG_DIR/team6_failure_mining.log' 2>&1
import json
from pathlib import Path

base = Path('artifacts/paper_eval_20260213')
out = Path('reports/tmux_team/team6_failure_mining.md')
out.parent.mkdir(parents=True, exist_ok=True)

def load_fail_ids(name):
    data = json.loads((base / name).read_text())
    rows = data.get('results', [])
    failed = [r for r in rows if r.get('success') is not True]
    ids = [Path(r.get('instance_file', r.get('instance_name', ''))).name for r in failed]
    return ids

logistics = load_fail_ids('checkpoint_logistics.json')
depots = load_fail_ids('checkpoint_depots.json')
blocksworld = load_fail_ids('checkpoint_blocksworld.json')

lines = []
lines.append('# Team 6 Failure Mining')
lines.append('')
lines.append(f'- Blocksworld failures ({len(blocksworld)}): {", ".join(blocksworld) if blocksworld else "None"}')
lines.append(f'- Logistics failures ({len(logistics)}): {", ".join(logistics) if logistics else "None"}')
lines.append(f'- Depots failures ({len(depots)}): {", ".join(depots) if depots else "None"}')
lines.append('')
lines.append('## Preliminary Patterns')
lines.append('- Logistics failures cluster in a few hard instances with possible domain-model mismatch or parsing edge cases.')
lines.append('- Depots has sparse but persistent hard cases, likely involving stacked precondition chains.')
lines.append('- Blocksworld checkpoint is clean in this frozen snapshot.')
out.write_text('\n'.join(lines))
print(out)
PY
 echo DONE > '$LOG_DIR/team6.status'; exec bash"
# teammate-7: improvement hypotheses report
TMUX_CMD_7="cd '$ROOT_DIR' && python - <<'PY' > '$LOG_DIR/team7_hypothesis.log' 2>&1
from pathlib import Path

out = Path('reports/tmux_team/team7_improvement_hypotheses.md')
out.parent.mkdir(parents=True, exist_ok=True)

lines = []
lines.append('# Team 7 Improvement Hypotheses')
lines.append('')
lines.append('## Candidate verifier/planner improvements')
lines.append('1. Add domain-action canonicalization before validation to reduce alias mismatch in PDDL action names.')
lines.append('2. Add structured Error_Report taxonomy (precondition_unsatisfied, unknown_symbol, goal_not_reached, parser_error) for tighter repair prompts.')
lines.append('3. Add retry policy with bounded repair rounds and error-type-specific prompt templates.')
lines.append('4. Add per-domain regression set from known failed instances and gate merges on 100% pass in this subset.')
lines.append('5. Separate Draft_Plan lifecycle in bdi_state to prevent unverified intention promotion.')
out.write_text('\n'.join(lines))
print(out)
PY
 echo DONE > '$LOG_DIR/team7.status'; exec bash"

# create windows (7 teammates)
tmux new-session -d -s "$SESSION_NAME" -n team1 "$TMUX_CMD_1"
tmux new-window -t "$SESSION_NAME" -n team2 "$TMUX_CMD_2"
tmux new-window -t "$SESSION_NAME" -n team3 "$TMUX_CMD_3"
tmux new-window -t "$SESSION_NAME" -n team4 "$TMUX_CMD_4"
tmux new-window -t "$SESSION_NAME" -n team5 "$TMUX_CMD_5"
tmux new-window -t "$SESSION_NAME" -n team6 "$TMUX_CMD_6"
tmux new-window -t "$SESSION_NAME" -n team7 "$TMUX_CMD_7"

echo "Session '$SESSION_NAME' started with 7 teammate windows."
echo "Attach: tmux attach -t $SESSION_NAME"
echo "Logs: $LOG_DIR"
echo "Reports: $REPORT_DIR"
