from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ActionNode(BaseModel):
    """
    Represents an atomic action (Intention) in the BDI plan.
    Corresponds to a node in the Plan Graph.
    """
    id: str = Field(..., description="Unique identifier for this action (e.g., 'nav_to_door')")
    action_type: str = Field(..., description="The type of action/skill to invoke (e.g., 'Navigate', 'PickUp')")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the action")
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
    nodes: List[ActionNode] = Field(..., description="List of all actions to be performed")
    edges: List[DependencyEdge] = Field(default_factory=list, description="List of execution dependencies")

    def to_networkx(self):
        """Helper to convert Pydantic model to NetworkX DiGraph"""
        import networkx as nx
        G = nx.DiGraph()
        for node in self.nodes:
            G.add_node(node.id, **node.model_dump())
        for edge in self.edges:
            G.add_edge(edge.source, edge.target, relationship=edge.relationship)
        return G
