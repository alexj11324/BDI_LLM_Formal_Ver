"""DSPy Signatures for structured BDI reasoning.

This module defines the three core DSPy Signatures that force the Teacher LLM
to produce structured, domain-agnostic BDI reasoning output.  Each Signature
specifies typed input/output fields so that DSPy can automatically compose
the prompt template and parse the LLM response.

Signatures
----------
BDIReasoningSignature
    Primary generation: belief state + desire → reasoning + intention DAG JSON.
ErrorCorrectionSignature
    Retry path: failed DAG + error context → corrected DAG JSON.
RecoveryPlanSignature
    Deadlock recovery: suspended intentions + epistemic flags → recovery plan.

Design notes
------------
* All field types are ``str`` (serialised JSON) because DSPy Signatures
  operate at the text level.  The BDI engine is responsible for
  serialising / deserialising Pydantic models before and after invocation.
* The docstrings on each Signature class serve as the *system instruction*
  for the underlying LLM call (DSPy convention).
* No domain-specific logic is present here – the Signatures are
  domain-agnostic by design.
"""

from __future__ import annotations

import dspy


# ---------------------------------------------------------------------------
# Signature 1: Primary BDI Reasoning
# ---------------------------------------------------------------------------

class BDIReasoningSignature(dspy.Signature):
    """Given the agent's current belief state, a desire (goal), and
    domain-specific context, produce a step-by-step reasoning chain and
    a valid IntentionDAG as a JSON object.

    The IntentionDAG JSON must contain:
    - "dag_id": a unique string identifier
    - "nodes": a list of action nodes, each with "node_id", "action_type",
      "parameters" (dict), and "dependencies" (list of node_id strings)
    - "metadata": an optional dict of additional information

    Reason carefully about preconditions and effects of each action before
    producing the DAG.  Ensure the topological ordering respects all
    dependencies."""

    # ── Inputs ──
    belief_state: str = dspy.InputField(
        desc=(
            "JSON-serialised BeliefState containing environment_context, "
            "epistemic_flags, and suspended_intentions."
        ),
    )
    desire: str = dspy.InputField(
        desc=(
            "JSON-serialised goal/desire that the agent must resolve.  "
            "This is a domain-agnostic dict describing the objective."
        ),
    )
    domain_context: str = dspy.InputField(
        desc=(
            "JSON-serialised domain-specific context extracted from the "
            "belief state's environment_context (e.g. PDDL state, repo "
            "snapshot).  Provided separately for convenience."
        ),
    )

    # ── Outputs ──
    reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step chain-of-thought explaining how the belief state "
            "and desire lead to the proposed IntentionDAG.  Include "
            "precondition checks and effect predictions for each action."
        ),
    )
    intention_dag_json: str = dspy.OutputField(
        desc=(
            "A strict JSON object representing the IntentionDAG.  Must "
            'contain keys "dag_id" (str), "nodes" (list of action node '
            'objects), and "metadata" (dict).  Do NOT wrap in markdown '
            "code fences."
        ),
    )


# ---------------------------------------------------------------------------
# Signature 2: Error Correction (Retry Path)
# ---------------------------------------------------------------------------

class ErrorCorrectionSignature(dspy.Signature):
    """Given a failed IntentionDAG, the original belief state, a formal error
    trace from the domain verifier, and a correction hint, produce a corrected
    IntentionDAG as a JSON object.

    Analyse the error trace carefully.  Identify which specific action node(s)
    violated preconditions or produced invalid effects, then fix only the
    problematic parts of the DAG while preserving valid portions.

    The corrected DAG JSON must follow the same schema as the original:
    - "dag_id": a new unique string identifier
    - "nodes": corrected list of action nodes
    - "metadata": dict (include a reference to the original failed dag_id)"""

    # ── Inputs ──
    belief_state: str = dspy.InputField(
        desc=(
            "JSON-serialised BeliefState at the time of the failed attempt."
        ),
    )
    failed_dag: str = dspy.InputField(
        desc=(
            "JSON-serialised IntentionDAG that failed verification.  "
            "Inspect node ordering, action types, and parameters."
        ),
    )
    error_trace: str = dspy.InputField(
        desc=(
            "Formal error trace from the domain verifier (e.g. "
            '"PreconditionViolation: clear(A) is False at node_2").  '
            "Use this to pinpoint the exact failure."
        ),
    )
    correction_hint: str = dspy.InputField(
        desc=(
            "Human-readable correction hint from the verifier suggesting "
            "what went wrong and how to fix it."
        ),
    )

    # ── Outputs ──
    reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step analysis of what went wrong in the failed DAG "
            "and how the correction addresses the error.  Reference "
            "specific node IDs and precondition violations."
        ),
    )
    corrected_dag_json: str = dspy.OutputField(
        desc=(
            "A strict JSON object representing the corrected IntentionDAG.  "
            'Must contain keys "dag_id" (str), "nodes" (list), and '
            '"metadata" (dict).  Do NOT wrap in markdown code fences.'
        ),
    )


# ---------------------------------------------------------------------------
# Signature 3: Recovery Plan (Epistemic Deadlock)
# ---------------------------------------------------------------------------

class RecoveryPlanSignature(dspy.Signature):
    """Given a list of suspended (deadlocked) intentions and the agent's
    epistemic flags (including compressed failure traces), generate a
    recovery plan that unblocks the agent.

    The recovery plan should:
    1. Analyse why previous attempts failed (from epistemic_flags).
    2. Propose an alternative strategy or decompose the original goal into
       simpler sub-goals.
    3. Produce a new IntentionDAG (or sequence of DAGs) that avoids the
       previously identified failure modes.

    The recovery plan JSON must include:
    - "recovery_strategy": a string describing the high-level recovery approach
    - "sub_goals": a list of simpler goal dicts (if decomposing)
    - "recovery_dag": an IntentionDAG JSON object for immediate execution
      (optional, may be null if only sub-goals are proposed)"""

    # ── Inputs ──
    suspended_intentions: str = dspy.InputField(
        desc=(
            "JSON-serialised list of IntentionDAG dicts that have been "
            "suspended due to epistemic deadlock.  Each contains the "
            "failed plan structure."
        ),
    )
    epistemic_flags: str = dspy.InputField(
        desc=(
            "JSON-serialised dict of epistemic flags from BeliefState, "
            "including compressed failure traces, retry counts, and "
            "deadlock markers for each suspended intention."
        ),
    )

    # ── Outputs ──
    reasoning: str = dspy.OutputField(
        desc=(
            "Detailed analysis of why the suspended intentions failed "
            "and what alternative strategy the agent should pursue.  "
            "Reference specific failure traces from epistemic_flags."
        ),
    )
    recovery_plan_json: str = dspy.OutputField(
        desc=(
            "A strict JSON object containing the recovery plan.  Must "
            'include "recovery_strategy" (str), "sub_goals" (list of '
            'goal dicts), and optionally "recovery_dag" (IntentionDAG '
            "JSON or null).  Do NOT wrap in markdown code fences."
        ),
    )
