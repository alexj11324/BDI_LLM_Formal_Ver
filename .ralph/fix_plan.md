Phase 0: Documentation Discovery & API Verification                                                                                           
                                                                                                                                              
  Objective: Establish ground truth for available APIs and validation patterns before implementation.                                           
                                                                                                                                              
  Subagent Tasks:                                                                                                                               

  Discovery Subagent 1 - Existing Codebase APIs
  - Read src/bdi_llm/verifier.py - document exact signatures of PlanVerifier.verify()
  - Read src/bdi_llm/planner.py - document how verification is currently called
  - Read run_planbench_full.py - identify exact integration points for verification
  - Output: List of existing verification call patterns with line numbers

  Discovery Subagent 2 - New Symbolic Verifier APIs
  - Read src/bdi_llm/symbolic_verifier.py - extract class names, method signatures
  - Read test_symbolic_verifier.py - identify working usage examples
  - Output: Exact API signatures with copy-ready examples

  Discovery Subagent 3 - PDDL Data Structures
  - Read run_planbench_full.py:44-78 - document parse_pddl_problem() return structure
  - Read test_pddl_to_bdi_flow.py:75-128 - document pddl_to_natural_language() patterns
  - Grep for init_state usage patterns in codebase
  - Output: Data structure schemas with example values

  Discovery Subagent 4 - Anti-Patterns
  - Read docs/SYMBOLIC_VERIFICATION_STATUS.md - identify known issues (VAL macOS incompatibility)
  - Read docs/PARALLEL_FAILURE_ANALYSIS.md - identify disconnected graph patterns
  - Output: List of prohibited patterns and why

  Orchestrator Consolidation:
  Create "Allowed APIs" reference document with:
  1. Exact import paths
  2. Method signatures with type hints
  3. Copy-ready initialization patterns
  4. Known limitations (VAL unavailable on macOS)

  ---
  Phase 1: Extend PDDL Parser to Extract Initial State

  What to implement: Add init_state extraction to existing parse_pddl_problem() function

  Documentation references:
  - Copy parsing pattern from run_planbench_full.py:44-78 (existing parse_pddl_problem)
  - Follow state structure from test_symbolic_verifier.py:37-43 (BlocksworldPhysicsValidator usage)

  Implementation Subagent Tasks:
  1. Read current parse_pddl_problem() implementation (run_planbench_full.py:44-78)
  2. Add state extraction logic following the pattern:
  # Copy this pattern from test_symbolic_verifier.py:37-43
  init_state = {
      'on_table': [...],  # Extract from 'ontable' predicates
      'on': [...],        # Extract from 'on' predicates
      'clear': [...],     # Extract from 'clear' predicates
      'holding': None     # Extract from 'holding' or 'handempty'
  }
  3. Return init_state as part of pddl_data dict

  Verification checklist:
  - parse_pddl_problem() returns dict with init_state key
  - Run: python -c "from run_planbench_full import parse_pddl_problem; result =
  parse_pddl_problem('planbench_data/plan-bench/instances/blocksworld/generated/instance-10.pddl'); print('init_state' in result)"
  - Verify init_state has keys: on_table, on, clear, holding
  - Test on 3 different instance files, verify no crashes

  Anti-pattern guards:
  - ❌ Don't invent new predicates beyond: ontable, on, clear, holding/handempty
  - ❌ Don't modify existing return keys (objects, init, goal)
  - ❌ Don't add domain parameter (blocksworld is hardcoded for now)

  ---
  Phase 2: Integrate Physical Validator into generate_bdi_plan()

  What to implement: Add Layer 2a (physics validation) to plan generation function

  Documentation references:
  - Copy validator usage from test_symbolic_verifier.py:37-67 (working example)
  - Follow integration pattern from docs/SYMBOLIC_VERIFICATION_ARCHITECTURE.md:233-279
  - Import from src/bdi_llm/symbolic_verifier.py (verified to exist)

  Implementation Subagent Tasks:
  1. Read run_planbench_full.py:168-204 (current generate_bdi_plan function)
  2. Add import: from src.bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator
  3. After structural verification (line 189), add physics validation:
  # Copy pattern from test_symbolic_verifier.py:37-67
  physics_validator = BlocksworldPhysicsValidator()
  physics_valid, physics_errors = physics_validator.validate_plan(
      pddl_actions, init_state
  )
  4. Update metrics dict to include physics validation results
  5. Combine validation: is_valid = struct_valid and physics_valid

  Verification checklist:
  - Import works: python -c "from src.bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator"
  - Run 3-instance test: python run_planbench_full.py --domain blocksworld --max_instances 3
  - Verify output JSON includes physics_validation in metrics
  - Grep output for "physics_errors" - should appear in failed instances
  - Success rate should be ≤ previous run (catches more errors now)

  Anti-pattern guards:
  - ❌ Don't call validator without init_state (Phase 1 dependency)
  - ❌ Don't ignore physics_errors in is_valid calculation
  - ❌ Don't try to use VAL verifier (known to fail on macOS)

  ---
  Phase 3: Update Metrics Schema for Multi-Layer Verification

  What to implement: Expand metrics dict to separate structural, symbolic, and overall validation

  Documentation references:
  - Copy structure from src/bdi_llm/symbolic_verifier.py:368-403 (IntegratedVerifier.verify_full return format)
  - Follow naming from docs/SYMBOLIC_VERIFICATION_ARCHITECTURE.md:428-438

  Implementation Subagent Tasks:
  1. Read current metrics structure in run_planbench_full.py:173-179
  2. Replace flat structure with layered structure:
  metrics = {
      'generation_time': ...,
      'verification_layers': {
          'structural': {'valid': bool, 'errors': [...]},
          'physics': {'valid': bool, 'errors': [...]}
      },
      'overall_valid': bool,
      'num_nodes': ...,
      'num_edges': ...
  }
  3. Update instance_result assignment (line 296) to use overall_valid

  Verification checklist:
  - Run 3-instance test
  - Check JSON output has verification_layers dict
  - Verify both structural and physics keys exist in layers
  - Each layer has valid (bool) and errors (list) keys
  - overall_valid equals structural.valid AND physics.valid

  Anti-pattern guards:
  - ❌ Don't rename existing keys (generation_time, num_nodes, num_edges)
  - ❌ Don't flatten errors back into single list
  - ❌ Don't calculate overall_valid incorrectly (must be AND of all layers)

  ---
  Phase 4: Add Comparative Analysis Output

  What to implement: Generate comparison report showing structural-only vs multi-layer validation results

  Documentation references:
  - Copy report format from docs/SYMBOLIC_VERIFICATION_ARCHITECTURE.md:428-438 (comparison table)
  - Follow print pattern from run_planbench_full.py:333-340 (existing summary output)

  Implementation Subagent Tasks:
  1. At end of run_batch_evaluation() (after line 327), add comparison statistics:
  # Count different validation outcomes
  structural_only_success = sum(1 for r in results['results']
      if r.get('bdi_metrics', {}).get('verification_layers', {}).get('structural', {}).get('valid', False))
  overall_success = sum(1 for r in results['results']
      if r.get('bdi_metrics', {}).get('overall_valid', False))

  results['summary']['structural_only_success'] = structural_only_success
  results['summary']['physics_caught_errors'] = structural_only_success - overall_success
  2. Print comparison table before final results

  Verification checklist:
  - Run 10-instance test: python run_planbench_full.py --domain blocksworld --max_instances 10
  - Verify output shows comparison: "Structural-only: X, Multi-layer: Y, Physics caught: Z errors"
  - Check JSON summary has structural_only_success and physics_caught_errors keys
  - Verify: structural_only_success ≥ overall_success (physics is stricter)

  Anti-pattern guards:
  - ❌ Don't calculate metrics from wrong layer (use verification_layers, not top-level is_valid)
  - ❌ Don't assume physics always catches errors (could be 0 for simple instances)

  ---
  Phase 5: Documentation & Testing ✅ COMPLETE (2026-02-04)

  What was implemented: Updated documentation and created comprehensive test suite

  Documentation Subagent Tasks:
  1. ✅ Updated docs/SYMBOLIC_VERIFICATION_STATUS.md:
    - Changed status to "✅ COMPLETE" for run_planbench_full.py integration
    - Added "实际可用的验证层" section showing integrated validators
    - Added Phase 5 completion status section
  2. ✅ Created docs/INTEGRATION_GUIDE.md:
    - Usage examples from verification checklist commands
    - Documented new metrics structure
    - Shows how to interpret results
    - API usage patterns, error types, troubleshooting

  Testing Subagent Tasks:
  1. ✅ Created test_integrated_verification.py:
    - Tests integration works end-to-end
    - Follows pattern from test_symbolic_verifier.py
    - Runs on known-good and known-bad instances
  2. ✅ test_integration_phase2.py created (offline tests, 4/4 passing)

  Verification checklist:
  - ✅ All documentation files updated and committed
  - ✅ Run: python test_integration_phase2.py - PASS (4/4 tests)
  - ⏳ Run full 100-instance test - PENDING (Phase 6, requires API key)
  - ⏳ Generate comparison chart - PENDING (Phase 6)

  Anti-pattern compliance:
  - ✅ Did NOT claim VAL integration works (documented macOS issue)
  - ✅ Did NOT modify test files without running them
  - ⏳ 100-instance validation run deferred to Phase 6 (requires API key)

  ---
  Phase 6: Final Verification & Comparison Analysis

  Verification Subagent Tasks:
  1. Run complete test suite:
  python test_symbolic_verifier.py
  python test_integrated_verification.py
  python run_planbench_full.py --domain blocksworld --max_instances 100
  2. Grep for anti-patterns:
  grep -r "PDDLSymbolicVerifier" run_planbench_full.py  # Should be 0 results (VAL not used)
  grep -r "verify_full" run_planbench_full.py  # Should find IntegratedVerifier usage
  3. Generate comparison report:
    - Before integration: 66.7% success (2/3, structural only)
    - After integration: ? success (structural AND physics)
    - Physics validation caught: ? additional errors

  Code Quality Subagent Tasks:
  1. Check all imports are from verified files
  2. Verify no hardcoded paths
  3. Check error handling for missing init_state
  4. Review metrics structure consistency

  Commit Subagent (ONLY IF ALL VERIFICATION PASSES):
  1. Stage changes: modified files only
  2. Commit message format:
  Integrate symbolic verification (Layer 2a: Physics)

  - Add init_state extraction to PDDL parser
  - Integrate BlocksworldPhysicsValidator into plan generation
  - Update metrics schema for multi-layer verification
  - Add comparative analysis output

  Results on 100 instances:
  - Structural-only: X% success
  - Multi-layer: Y% success
  - Physics caught: Z additional errors

  Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>

  ---
  Success Criteria

  The plan is complete when:
  1. ✅ All verification checklists pass
  2. ✅ No anti-patterns detected
  3. ✅ 100-instance run completes successfully
  4. ✅ Comparison shows physics validation catching errors structural validation missed
  5. ✅ Documentation accurately reflects implementation (no VAL claims)
  6. ✅ Code committed with evidence-based metrics in commit message

  Known Risks & Mitigations

  Risk: Assuming init_state always has all keys
  Mitigation: Add defensive .get() with defaults in validator calls

  Risk: Physics validator assumes blocksworld domain
  Mitigation: Add domain check before creating physics validator

  Risk: Metrics schema change breaks existing result parsers
  Mitigation: Keep backward compatibility - add new keys, don't rename old ones