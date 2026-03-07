import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

class ActionNode(BaseModel):
    """
    Represents an atomic action (Intention) in the BDI plan.
    Corresponds to a node in the Plan Graph.
    """
    id: str = Field(..., description="Unique identifier for this action (e.g., 'nav_to_door')")
    action_type: str = Field(
        ...,
        description="The type of action/skill to invoke (e.g., 'Navigate', 'PickUp')",
    )
    params: dict[str, Any] = Field(default_factory=dict, description="Parameters for the action")
    description: str = Field(..., description="Human-readable description of what this action does")
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        """Accept common alias variants from raw LLM output."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "action_type" not in normalized:
            normalized["action_type"] = normalized.pop(
                "action",
                normalized.pop("type", "unknown"),
            )
        if "params" not in normalized or normalized["params"] is None:
            normalized["params"] = {}
        if "description" not in normalized or not normalized["description"]:
            normalized["description"] = (
                f"{normalized.get('action_type', '')} {normalized.get('params', {})}"
            ).strip()
        return normalized

class DependencyEdge(BaseModel):
    """
    Represents a dependency between two actions.
    Corresponds to a directed edge in the Plan Graph (source -> target).
    Implies: 'source' must act before 'target'.
    """
    source: str = Field(..., description="ID of the prerequisite action")
    target: str = Field(..., description="ID of the dependent action")
    relationship: str = Field("depends_on", description="Type of dependency")
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        """Accept common edge alias variants from raw LLM output."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "source" not in normalized:
            normalized["source"] = normalized.pop(
                "from_id",
                normalized.pop("from", ""),
            )
        if "target" not in normalized:
            normalized["target"] = normalized.pop(
                "to_id",
                normalized.pop("to", ""),
            )
        return normalized

class BDIPlan(BaseModel):
    """
    The complete BDI Plan structure.
    Outputted by the LLM as a structured object.
    """
    goal_description: str = Field(..., description="Restatement of the user's goal")
    nodes: list[ActionNode] = Field(..., description="List of all actions to be performed")
    edges: list[DependencyEdge] = Field(
        default_factory=list,
        description="List of execution dependencies",
    )
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _normalize_plan(cls, data: Any) -> Any:
        """Make direct Pydantic validation tolerant to minor LLM schema drift.

        This path is used by Instructor/response-model parsing, so it must be
        at least as forgiving as ``from_llm_text``.
        """
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        raw_nodes = normalized.get("nodes", []) or []
        normalized_nodes: list[dict[str, Any]] = []

        for idx, raw_node in enumerate(raw_nodes, start=1):
            if hasattr(raw_node, "model_dump"):
                raw_node = raw_node.model_dump()
            if not isinstance(raw_node, dict):
                continue
            node = dict(raw_node)
            if "action_type" not in node:
                node["action_type"] = node.pop("action", node.pop("type", "unknown"))
            if "params" not in node or node["params"] is None:
                node["params"] = {}
            if "id" not in node or not node["id"]:
                node["id"] = f"step_{idx}"
            if "description" not in node or not node["description"]:
                node["description"] = (
                    f"{node.get('action_type', '')} {node.get('params', {})}"
                ).strip()
            normalized_nodes.append(node)

        normalized["goal_description"] = normalized.get(
            "goal_description",
            "Generated plan",
        )
        normalized["nodes"] = normalized_nodes

        node_ids = {node["id"] for node in normalized_nodes}
        raw_edges = normalized.get("edges")
        normalized_edges: list[dict[str, Any]] = []

        if isinstance(raw_edges, list):
            for raw_edge in raw_edges:
                if hasattr(raw_edge, "model_dump"):
                    raw_edge = raw_edge.model_dump()
                if not isinstance(raw_edge, dict):
                    continue
                edge = dict(raw_edge)
                if "source" not in edge:
                    edge["source"] = edge.pop("from_id", edge.pop("from", ""))
                if "target" not in edge:
                    edge["target"] = edge.pop("to_id", edge.pop("to", ""))
                source = edge.get("source", "")
                target = edge.get("target", "")
                if not source or not target or source == target:
                    continue
                if source not in node_ids or target not in node_ids:
                    continue
                normalized_edges.append(edge)

        # If the model omitted edges entirely, or produced only malformed ones,
        # salvage the plan by falling back to a linear chain in node order.
        should_linearize = raw_edges is None or (bool(raw_edges) and not normalized_edges)
        if should_linearize and len(normalized_nodes) > 1:
            normalized_edges = [
                {
                    "source": normalized_nodes[idx]["id"],
                    "target": normalized_nodes[idx + 1]["id"],
                }
                for idx in range(len(normalized_nodes) - 1)
            ]

        normalized["edges"] = normalized_edges
        return normalized

    def to_networkx(self):
        """Helper to convert Pydantic model to NetworkX DiGraph"""
        import networkx as nx
        G = nx.DiGraph()
        for node in self.nodes:
            G.add_node(node.id, **node.model_dump())
        for edge in self.edges:
            G.add_edge(edge.source, edge.target, relationship=edge.relationship)
        return G

    @classmethod
    def from_llm_text(cls, text: str) -> Optional["BDIPlan"]:
        """Parse raw LLM text output into a *BDIPlan*, with field normalisation.

        Handles:
        - Markdown code-fence stripping (```json ... ```)
        - Node field normalisation ('action'/'type' → 'action_type', auto-id)
        - Edge field normalisation ('from_id'/'from'/'to_id'/'to' → 'source'/'target')

        Returns *None* if the text cannot be parsed or validated.
        """
        content = text.strip()

        # Strip markdown fences
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            plan_dict = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from LLM output")
            return None
        if not isinstance(plan_dict, dict):
            logger.warning("LLM output did not decode to a JSON object")
            return None

        # Normalise nodes
        raw_nodes = plan_dict.get("nodes", [])
        normalised_nodes = []
        for n in raw_nodes:
            if not isinstance(n, dict):
                continue
            if "action_type" not in n:
                n["action_type"] = n.pop("action", n.pop("type", "unknown"))
            if "description" not in n:
                n["description"] = f"{n.get('action_type', '')} {n.get('params', '')}"
            if "id" not in n:
                n["id"] = f"s{len(normalised_nodes) + 1}"
            normalised_nodes.append(n)

        # Normalise edges
        raw_edges = plan_dict.get("edges", [])
        normalised_edges = []
        for e in raw_edges:
            if not isinstance(e, dict):
                continue
            if "source" not in e:
                e["source"] = e.pop("from_id", e.pop("from", ""))
            if "target" not in e:
                e["target"] = e.pop("to_id", e.pop("to", ""))
            normalised_edges.append(e)

        try:
            nodes = [ActionNode(**n) for n in normalised_nodes]
            edges = [DependencyEdge(**e) for e in normalised_edges]
            return cls(
                goal_description=plan_dict.get("goal_description", "Generated plan"),
                nodes=nodes,
                edges=edges,
            )
        except Exception as e:
            logger.warning(f"Pydantic validation failed: {e}")
            return None


# Backward-compatible module-level alias
def parse_plan_from_text(text: str) -> BDIPlan | None:
    """Thin wrapper kept for backward compatibility — delegates to *BDIPlan.from_llm_text*."""
    return BDIPlan.from_llm_text(text)
