"""
Symbolic Fallback Planner

Implements 'Graceful Symbolic Degradation'. When the LLM repeatedly fails to 
repair a plan (due to spatial or topological complexity), this module generates
a temporary PDDL problem reflecting the exact N-1 state and invokes `pyperplan`
to deterministically solve the remaining path.
"""

import os
import re
import tempfile
import logging
from threading import Lock
from typing import Optional

from src.bdi_llm.schemas import BDIPlan, ActionNode, DependencyEdge

logger = logging.getLogger(__name__)

class SymbolicFallbackPlanner:
    """Thread-safe wrapper around pyperplan for deterministic fallback recovery."""

    _planner_lock = Lock()
    last_error: str | None = None

    @staticmethod
    def _sanitize_state_props(current_state_props: set[str]) -> set[str]:
        """Keep only ground propositions safe to inject into a PDDL :init block."""
        sanitized: set[str] = set()
        for prop in current_state_props:
            if not prop:
                continue
            normalized = " ".join(str(prop).split())
            if "?" in normalized:
                logger.warning("Skipping non-ground proposition in fallback state: %s", normalized)
                continue
            if not (normalized.startswith("(") and normalized.endswith(")")):
                logger.warning("Skipping malformed proposition in fallback state: %s", normalized)
                continue
            sanitized.add(normalized)
        return sanitized
    
    @staticmethod
    def _create_temp_problem(original_problem_path: str, current_state_props: set[str]) -> str:
        """
        Reads the original problem file and replaces the (:init ...) block
        with the current propositions.
        """
        with open(original_problem_path, 'r') as f:
            content = f.read()

        # Find the init block.
        # This regex looks for (:init and captures everything until (:goal
        init_pattern = re.compile(r'(\(:init\s+)(.*?)(\)\s*\(:goal)', re.DOTALL)
        
        sanitized_state = SymbolicFallbackPlanner._sanitize_state_props(current_state_props)
        if not sanitized_state:
            raise ValueError("Fallback state is empty or contains no valid ground propositions.")

        # Build new init content
        new_init_content = "\n".join(sorted(sanitized_state)) + "\n"
        
        # Replace the old init block with the new one
        new_content = init_pattern.sub(rf'\g<1>{new_init_content}\g<3>', content)
        if new_content == content:
            raise ValueError("Failed to rewrite problem :init block for symbolic fallback.")
        
        fd, temp_path = tempfile.mkstemp(suffix=".pddl", prefix="fallback_prob_")
        with os.fdopen(fd, 'w') as f:
            f.write(new_content)
            
        return temp_path

    @staticmethod
    def generate_fallback_plan(
        domain_file: str, 
        problem_file: str, 
        current_state_props: set[str],
        goal_description: str = "Symbolic Fallback Recovery"
    ) -> Optional[BDIPlan]:
        """
        Invokes pyperplan to solve the problem from the given state.
        Returns a BDIPlan if successful.
        """
        SymbolicFallbackPlanner.last_error = None
        try:
            temp_prob_file = SymbolicFallbackPlanner._create_temp_problem(
                problem_file,
                current_state_props,
            )
        except Exception as e:
            SymbolicFallbackPlanner.last_error = str(e)
            logger.error("Symbolic Fallback Problem Construction Exception: %r", e)
            return None
        
        try:
            from pyperplan import planner
            
            # Using A* or BFS. pyperplan search_plan signature:
            # search_plan(domain_file, problem_file, search_name, heuristic_name)
            # astar with hmax is a good default for classical planning.
            logger.info("Executing Pyperplan Symbolic Fallback...")

            search_fn = planner.SEARCHES["astar"]
            heuristic_cls = planner.HEURISTICS["hmax"]
            
            # pyperplan parsing/grounding is not thread-safe in practice, so serialize it.
            with SymbolicFallbackPlanner._planner_lock:
                plan_actions = planner.search_plan(
                    domain_file,
                    temp_prob_file,
                    search_fn,
                    heuristic_cls,
                )
            
            if plan_actions is None:
                SymbolicFallbackPlanner.last_error = (
                    "Symbolic fallback could not find a valid route from the current state."
                )
                logger.warning(SymbolicFallbackPlanner.last_error)
                return None
                
            nodes = []
            edges = []
            
            prev_id = None
            for i, action_node in enumerate(plan_actions):
                # pyperplan action names already include parentheses on some builds.
                raw_action_name = str(getattr(action_node, "name", action_node)).strip()
                action_str = raw_action_name if raw_action_name.startswith("(") else f"({raw_action_name})"
                
                node_id = f"fallback_{i}"
                nodes.append(ActionNode(
                    id=node_id,
                    action_type=action_str,
                    params={},
                    description=f"Fallback Action: {action_str}"
                ))
                
                if prev_id:
                    edges.append(DependencyEdge(
                        source=prev_id,
                        target=node_id,
                        relationship="depends_on"
                    ))
                prev_id = node_id
                
            logger.info(f"Symbolic Fallback generated {len(nodes)} actions successfully.")
            return BDIPlan(
                goal_description=goal_description,
                nodes=nodes,
                edges=edges
            )
            
        except Exception as e:
            SymbolicFallbackPlanner.last_error = str(e)
            logger.error(f"Symbolic Fallback Exception: {e!r}")
            return None
        finally:
            if os.path.exists(temp_prob_file):
                os.unlink(temp_prob_file)
