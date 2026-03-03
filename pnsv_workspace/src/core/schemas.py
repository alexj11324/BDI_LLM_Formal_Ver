"""Core Pydantic V2 schemas for the BDI reasoning engine.

This module defines the foundational data models used throughout the PNSV
framework.  All models use strict Pydantic V2 BaseModel with full type
annotations.  They are intentionally domain-agnostic: no PDDL, SWE, or any
other domain-specific concepts leak into these definitions.

Models
------
IntentionNode
    A single action within an intention DAG.
IntentionDAG
    A directed acyclic graph of intention nodes produced by the Teacher LLM.
BeliefState
    The agent's current epistemic snapshot, including environment context,
    epistemic flags, and any suspended intentions.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class IntentionNode(BaseModel):
    """A single node (action) inside an IntentionDAG.

    Attributes
    ----------
    node_id : str
        Unique identifier for this node within its parent DAG.
    action_type : str
        The type of action this node represents (e.g. "unstack", "apply_edit").
    parameters : Dict[str, Any]
        Arbitrary key-value parameters consumed by the domain verifier /
        executor.
    dependencies : List[str]
        List of ``node_id`` values that must complete before this node can
        execute, establishing the topological ordering of the DAG.
    """

    node_id: str = Field(
        ...,
        description="Unique identifier for this node within the DAG.",
    )
    action_type: str = Field(
        ...,
        description="The type of action this node represents.",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value parameters for the action.",
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Node IDs that must complete before this node executes.",
    )


class IntentionDAG(BaseModel):
    """A directed acyclic graph of IntentionNode instances.

    Produced by the Teacher LLM and validated by a domain-specific verifier
    before execution.

    Attributes
    ----------
    dag_id : str
        Unique identifier for this intention DAG.
    nodes : List[IntentionNode]
        Ordered list of action nodes comprising the plan.
    metadata : Dict[str, Any]
        Optional metadata attached to this DAG (e.g. generation timestamp,
        model used, domain hints).
    """

    dag_id: str = Field(
        ...,
        description="Unique identifier for this intention DAG.",
    )
    nodes: List[IntentionNode] = Field(
        default_factory=list,
        description="Ordered list of action nodes comprising the plan.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata attached to this DAG.",
    )


class BeliefState(BaseModel):
    """The agent's current epistemic state.

    BeliefState captures everything the BDI engine knows about the world at a
    given point in time.  Domain verifiers receive a deep copy of this state so
    that the original remains immutable until a successful verification.

    Attributes
    ----------
    environment_context : Dict[str, Any]
        Domain-specific environmental state (e.g. PDDL predicates, file system
        snapshots).  The BDI engine treats this as an opaque dict.
    epistemic_flags : Dict[str, Any]
        Meta-cognitive flags set during reasoning (e.g. compressed failure
        traces, confidence scores, deadlock markers).
    suspended_intentions : List[IntentionDAG]
        Intention DAGs that triggered an EpistemicDeadlockError and have been
        suspended for later recovery.
    """

    environment_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Domain-specific environmental state (opaque to the engine).",
    )
    epistemic_flags: Dict[str, Any] = Field(
        default_factory=dict,
        description="Meta-cognitive flags set during reasoning.",
    )
    suspended_intentions: List[IntentionDAG] = Field(
        default_factory=list,
        description="Intention DAGs suspended due to epistemic deadlock.",
    )
