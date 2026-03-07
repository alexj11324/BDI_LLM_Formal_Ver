## Generic PDDL Planner Refactor on Isolated Branch

### Summary
Work must happen on a new branch from `main` named `codex/generic-pddl-domain`.

Goal of this branch:
- make `BDIPlanner` truly support **generic PDDL domains**
- keep all existing `PlanBench` scripts and workflows intact
- add a **new, separate generic-domain runner**
- introduce a thin higher-level planning/task interface so future non-PDDL benchmarks like TravelPlanner can plug in later, but **do not implement TravelPlanner in this branch**

This is a decoupling branch, not a benchmark-integration branch.

### Implementation Changes
- Refactor `BDIPlanner` so it no longer hardcodes domain behavior inside the planner constructor.
  - Move domain-specific action schema, required params, prompt examples, and prompt selection into dedicated **domain spec / adapter** objects.
  - Keep current built-in adapters for `blocksworld`, `logistics`, and `depots`.
  - Add a **generic PDDL adapter** that accepts:
    - `domain_name`
    - raw `domain.pddl`
    - optional prompt-time action schema summary derived from the PDDL
- Add a new planner-facing abstraction layer for future reuse.
  - `PlanningTask`: normalized planning input object
    - `task_id`
    - `domain_name`
    - `beliefs`
    - `desire`
    - optional `domain_context`
    - optional metadata
  - `TaskAdapter`: transforms benchmark-native data into `PlanningTask`
  - `PlanSerializer` or equivalent output contract: converts planner output into benchmark-native output
- Keep `BDIPlan` as the planner’s internal output for now.
  - Do **not** redesign it for TravelPlanner yet.
  - Future non-PDDL support is only a reserved interface boundary in this branch, not a completed benchmark implementation.
- Add a new generic DSPy signature path.
  - Introduce `GeneratePlanGeneric` for arbitrary PDDL domains using `beliefs + desire + domain_context`
  - Existing fixed-domain signatures remain for current PlanBench domains
  - Generic signature must avoid hardcoded action names and instead rely on domain context derived from PDDL
- Add a new standalone runner, separate from all existing PlanBench entrypoints.
  - New script: `scripts/evaluation/run_generic_pddl_eval.py`
  - It should:
    - accept `--domain_pddl`
    - accept `--problem_pddl` or `--problem_dir`
    - convert PDDL problems into `PlanningTask`
    - invoke the generic planner path
    - run structural verification + VAL verification
    - write results under a dedicated run directory
  - It must not replace or rename `run_planbench_full.py`, `run_planbench_eval.py`, or related scripts
- Preserve PlanBench compatibility.
  - Existing `run_planbench_*` scripts stay in place
  - Existing CLI behavior stays unchanged
  - Existing PlanBench domains should route through the new adapter/spec layer internally only if that can be done without changing external behavior
- Add a minimal future-facing interface reservation for non-PDDL benchmarks.
  - Define the adapter boundary now so future benchmarks can map into `PlanningTask`
  - Do not add TravelPlanner logic, files, prompts, or scoring in this branch
  - The only goal is to avoid redoing the planner abstraction later

### Public Interfaces / Contracts
- New internal contracts:
  - `PlanningTask`
  - `TaskAdapter`
  - domain spec / domain adapter interface
- New CLI entrypoint:
  - `python scripts/evaluation/run_generic_pddl_eval.py --domain_pddl ... --problem_pddl ...`
- Existing PlanBench CLIs remain public and unchanged

### Test Plan
- Unit tests for generic planner routing:
  - built-in domains still select their existing domain-specific behavior
  - generic PDDL path is selected when given external domain context
- Unit tests for domain adapter/spec behavior:
  - action schema extraction from a new PDDL domain
  - required-parameter mapping generation
  - prompt context generation from domain file
- Integration tests for the new generic runner:
  - one toy custom PDDL domain + one toy problem
  - planner output parses into `BDIPlan`
  - structural verifier runs
  - VAL verifier runs
- Regression tests:
  - current PlanBench smoke cases still pass through their existing scripts
  - no CLI breakage in current `run_planbench_*` entrypoints
- Acceptance criteria:
  - a new custom PDDL domain can be evaluated without editing `BDIPlanner` source
  - `main`-style PlanBench workflows remain behaviorally unchanged
  - non-PDDL benchmark support is not implemented, but a clear adapter seam exists for it

### Assumptions
- Base branch is `main`
- Working branch is `codex/generic-pddl-domain`
- This branch does **not** include TravelPlanner execution or scoring
- This branch does **not** rename or remove existing PlanBench scripts
- “Generic domain” means arbitrary **PDDL** domain support first, with only interface preparation for later non-PDDL benchmarks
