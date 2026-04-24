import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

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


class DependencyEdge(BaseModel):
    """
    Represents a dependency between two actions.
    Corresponds to a directed edge in the Plan Graph (source -> target).
    Implies: 'source' must act before 'target'.
    """

    source: str = Field(..., description="ID of the prerequisite action")
    target: str = Field(..., description="ID of the dependent action")
    relationship: str = Field("depends_on", description="Type of dependency")


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

        # Normalise nodes
        raw_nodes = plan_dict.get("nodes", [])
        normalised_nodes = []
        for n in raw_nodes:
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
