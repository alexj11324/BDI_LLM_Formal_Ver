"""
BDI Plan Visualizer - Using NetworkX skill from AI Research Skills

Creates publication-quality visualizations of BDI plan graphs.
Helps visually verify plan structure and execution flow.
"""
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from typing import Dict, Optional, Tuple
import os

from .schemas import BDIPlan
from .verifier import PlanVerifier


class PlanVisualizer:
    """
    Visualizes BDI Plan Graphs using NetworkX.
    Based on AI Research Skills: NetworkX visualization reference.
    """

    # Color scheme for action types
    ACTION_COLORS = {
        'Navigate': '#4CAF50',     # Green
        'PickUp': '#2196F3',       # Blue
        'PutDown': '#9C27B0',      # Purple
        'OpenDoor': '#FF9800',     # Orange
        'UnlockDoor': '#F44336',   # Red
        'TurnOn': '#FFEB3B',       # Yellow
        'TurnOff': '#795548',      # Brown
        'default': '#9E9E9E',      # Gray
    }

    @classmethod
    def visualize_plan(
        cls,
        plan: BDIPlan,
        output_path: Optional[str] = None,
        figsize: Tuple[int, int] = (12, 8),
        show_execution_order: bool = True,
        title: Optional[str] = None,
        seed: int = 42
    ) -> plt.Figure:
        """
        Create a visualization of the BDI plan graph.

        Args:
            plan: The BDI plan to visualize
            output_path: Path to save the figure (optional)
            figsize: Figure dimensions
            show_execution_order: Whether to annotate nodes with execution order
            title: Custom title for the plot
            seed: Random seed for reproducible layout

        Returns:
            matplotlib Figure object
        """
        G = plan.to_networkx()

        # Verify and get execution order
        is_valid, errors = PlanVerifier.verify(G)
        execution_order = PlanVerifier.topological_sort(G) if is_valid else []

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Use Kamada-Kawai layout for better visualization of DAGs
        # (As recommended by NetworkX skill for DAG structures)
        pos = nx.kamada_kawai_layout(G)

        # Prepare node colors based on action type
        node_colors = [
            cls.ACTION_COLORS.get(
                G.nodes[n].get('action_type', 'default'),
                cls.ACTION_COLORS['default']
            )
            for n in G.nodes()
        ]

        # Prepare node sizes based on connectivity (degree)
        degrees = dict(G.degree())
        max_degree = max(degrees.values()) if degrees else 1
        node_sizes = [300 + 500 * (degrees[n] / max_degree) for n in G.nodes()]

        # Draw edges first (so they appear behind nodes)
        nx.draw_networkx_edges(
            G, pos,
            ax=ax,
            edge_color='#BDBDBD',
            width=2,
            arrows=True,
            arrowsize=20,
            arrowstyle='->',
            connectionstyle='arc3,rad=0.1',
            alpha=0.8
        )

        # Draw nodes
        nx.draw_networkx_nodes(
            G, pos,
            ax=ax,
            node_color=node_colors,
            node_size=node_sizes,
            edgecolors='black',
            linewidths=2
        )

        # Draw labels (action descriptions)
        labels = {n: G.nodes[n].get('id', n) for n in G.nodes()}
        nx.draw_networkx_labels(
            G, pos,
            labels=labels,
            ax=ax,
            font_size=10,
            font_weight='bold'
        )

        # Add execution order annotations if valid
        if show_execution_order and execution_order:
            order_labels = {n: f"#{i+1}" for i, n in enumerate(execution_order)}
            # Offset position for order labels
            pos_order = {n: (p[0], p[1] + 0.08) for n, p in pos.items()}
            nx.draw_networkx_labels(
                G, pos_order,
                labels=order_labels,
                ax=ax,
                font_size=8,
                font_color='red',
                font_weight='bold'
            )

        # Create legend for action types
        used_types = set(G.nodes[n].get('action_type', 'default') for n in G.nodes())
        legend_elements = [
            Patch(facecolor=cls.ACTION_COLORS.get(t, cls.ACTION_COLORS['default']),
                  edgecolor='black', label=t)
            for t in used_types
        ]
        ax.legend(handles=legend_elements, loc='upper left', title='Action Types')

        # Set title
        if title:
            ax.set_title(title, fontsize=16, fontweight='bold')
        else:
            status = "✓ Valid DAG" if is_valid else "✗ Invalid"
            ax.set_title(f"BDI Plan: {plan.goal_description}\n[{status}]",
                        fontsize=14, fontweight='bold')

        # Add error annotations if invalid
        if not is_valid:
            error_text = "\n".join(f"• {e}" for e in errors)
            ax.annotate(
                f"Errors:\n{error_text}",
                xy=(0.02, 0.02),
                xycoords='axes fraction',
                fontsize=9,
                color='red',
                bbox=dict(boxstyle='round', facecolor='#FFCDD2', alpha=0.8)
            )

        ax.axis('off')
        plt.tight_layout()

        # Save if path provided
        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"Saved visualization to: {output_path}")

        return fig

    @classmethod
    def compare_plans(
        cls,
        plans: Dict[str, BDIPlan],
        output_path: Optional[str] = None,
        seed: int = 42
    ) -> plt.Figure:
        """
        Compare multiple plans side by side.

        Args:
            plans: Dictionary of {label: plan} pairs
            output_path: Path to save the figure
            seed: Random seed for layout

        Returns:
            matplotlib Figure object
        """
        n_plans = len(plans)
        fig, axes = plt.subplots(1, n_plans, figsize=(6 * n_plans, 6))

        if n_plans == 1:
            axes = [axes]

        for ax, (label, plan) in zip(axes, plans.items()):
            G = plan.to_networkx()
            is_valid, _ = PlanVerifier.verify(G)

            pos = nx.kamada_kawai_layout(G)

            node_colors = [
                cls.ACTION_COLORS.get(
                    G.nodes[n].get('action_type', 'default'),
                    cls.ACTION_COLORS['default']
                )
                for n in G.nodes()
            ]

            nx.draw(
                G, pos,
                ax=ax,
                node_color=node_colors,
                with_labels=True,
                arrows=True,
                node_size=500,
                font_size=8,
                edgecolors='black',
                linewidths=1
            )

            status = "✓" if is_valid else "✗"
            ax.set_title(f"{label} [{status}]", fontsize=12)
            ax.axis('off')

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')

        return fig


def demo_visualization():
    """Demonstrate visualization capabilities."""
    from .schemas import ActionNode, DependencyEdge

    # Create a sample plan
    plan = BDIPlan(
        goal_description="Navigate to Kitchen",
        nodes=[
            ActionNode(id="pickup_keys", action_type="PickUp",
                      params={"object": "keys"}, description="Pick up keys"),
            ActionNode(id="walk_to_door", action_type="Navigate",
                      params={"target": "door"}, description="Go to door"),
            ActionNode(id="unlock_door", action_type="UnlockDoor",
                      description="Unlock the door"),
            ActionNode(id="open_door", action_type="OpenDoor",
                      description="Open the door"),
            ActionNode(id="enter_kitchen", action_type="Navigate",
                      params={"target": "kitchen"}, description="Enter kitchen"),
        ],
        edges=[
            DependencyEdge(source="pickup_keys", target="walk_to_door"),
            DependencyEdge(source="pickup_keys", target="unlock_door"),
            DependencyEdge(source="walk_to_door", target="unlock_door"),
            DependencyEdge(source="unlock_door", target="open_door"),
            DependencyEdge(source="open_door", target="enter_kitchen"),
        ]
    )

    # Visualize
    PlanVisualizer.visualize_plan(
        plan,
        output_path="plan_visualization.png",
        title="BDI Plan: Kitchen Navigation"
    )
    plt.show()


if __name__ == "__main__":
    demo_visualization()
