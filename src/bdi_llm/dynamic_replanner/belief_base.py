"""
BeliefBase: Maintains the symbolic world state during plan execution.

Parses a PDDL problem's (:init ...) block into a set of ground propositions,
and provides `apply_action` to update state after each successful action
based on the domain definition.
This gives the DynamicReplanner a human-readable snapshot of the current
world state to include in the recovery prompt.
"""

import re
from dataclasses import dataclass, field


@dataclass
class BeliefBase:
    """
    Domain-agnostic ground-truth state tracker.
    State is a set of string propositions, e.g. {"(on a b)", "(clear a)", "(handempty)"}.
    """
    propositions: set[str] = field(default_factory=set)
    objects: list[str] = field(default_factory=list)
    domain_name: str = ""
    _actions: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    @classmethod
    def from_pddl(cls, domain_file: str, problem_file: str) -> "BeliefBase":
        """Parse PDDL problem and domain to create state tracker."""
        with open(problem_file) as f:
            prob_content = f.read()
            
        with open(domain_file) as f:
            dom_content = f.read()

        # Domain name
        dm = re.search(r"\(:domain\s+([^\)]+)\)", prob_content)
        domain_name = dm.group(1).strip() if dm else "unknown"

        # Objects
        objects_match = re.search(r":objects\s+(.*?)\)", prob_content, re.DOTALL)
        objects: list[str] = []
        if objects_match:
            text = objects_match.group(1)
            # Strip type annotations ("obj1 obj2 - Type")
            text = re.sub(r"\s*-\s*\w+", "", text)
            objects = [w.strip() for w in text.split() if w.strip()]

        # Init predicates
        init_match = re.search(r":init\s+(.*?)\(:goal", prob_content, re.DOTALL)
        propositions: set[str] = set()
        if init_match:
            init_text = init_match.group(1)
            for pred_body in re.findall(r"\(([^()]+)\)", init_text):
                # Normalise whitespace
                prop = "(" + " ".join(pred_body.split()) + ")"
                propositions.add(prop)

        # Parse Domain Actions for Effects
        actions = cls._parse_domain_actions(dom_content)

        return cls(propositions=propositions, objects=objects, domain_name=domain_name, _actions=actions)

    @classmethod
    def from_pddl_problem(cls, pddl_file: str) -> "BeliefBase":
        """Legacy support - without domain file."""
        return cls.from_pddl(pddl_file, pddl_file)  # Will fail on domain parse, just for backwards compat if used somewhere

    @staticmethod
    def _parse_domain_actions(content: str) -> dict:
        """Parse STRIPS actions from PDDL domain file using a balanced parenthesis parser."""
        actions = {}
        def get_balanced_block(s, start_idx):
            count = 0
            for i in range(start_idx, len(s)):
                if s[i] == '(':
                    count += 1
                elif s[i] == ')':
                    count -= 1
                if count == 0:
                    return s[start_idx:i+1]
            return None

        # Strip comments
        content = re.sub(r';.*$', '', content, flags=re.MULTILINE)

        for match in re.finditer(r':action\s+([A-Za-z0-9_-]+)', content, re.IGNORECASE):
            action_name = match.group(1).lower()
            idx = match.end()
            
            param_match = re.search(r':parameters\s*(\(.*?\))', content[idx:], re.IGNORECASE | re.DOTALL)
            if not param_match:
                continue
            params_str = param_match.group(1)
            params = []
            param_tokens = params_str.replace('(', ' ').replace(')', ' ').split()
            i = 0
            while i < len(param_tokens):
                token = param_tokens[i].strip()
                if token.startswith('?'):
                    params.append(token)
                    i += 1
                    if i < len(param_tokens) and param_tokens[i] == '-':
                        i += 2
                    continue
                i += 1
            
            effect_idx = content.find(':effect', idx)
            if effect_idx == -1: continue
            
            open_paren_idx = content.find('(', effect_idx)
            if open_paren_idx == -1: continue
            
            effect_block = get_balanced_block(content, open_paren_idx)
            if not effect_block: continue
            
            add_effs = []
            del_effs = []
            
            eff_content = effect_block.strip()
            if eff_content.startswith('(and'):
                # remove (and ...)
                eff_content = eff_content[4:-1].strip()
                
            i = 0
            while i < len(eff_content):
                if eff_content[i] == '(':
                    block = get_balanced_block(eff_content, i)
                    if block:
                        if block.startswith('(not'):
                            # get the inner predicate
                            inner = get_balanced_block(block, block.find('(', 4))
                            if inner:
                                del_effs.append(inner.strip())
                        else:
                            add_effs.append(block.strip())
                        i += len(block)
                    else:
                        i += 1
                else:
                    i += 1
                    
            actions[action_name] = {
                'params': params,
                'add': add_effs,
                'del': del_effs
            }
        return actions

    # ------------------------------------------------------------------ #
    # State queries
    # ------------------------------------------------------------------ #

    def holds(self, proposition: str) -> bool:
        """Check if a proposition currently holds."""
        return proposition in self.propositions

    def query(self, predicate_name: str) -> list[str]:
        """Return all propositions matching a predicate name."""
        return [
            p for p in self.propositions
            if p.startswith(f"({predicate_name} ") or p == f"({predicate_name})"
        ]

    # ------------------------------------------------------------------ #
    # State updates
    # ------------------------------------------------------------------ #

    def add(self, proposition: str):
        self.propositions.add(proposition)

    def remove(self, proposition: str):
        self.propositions.discard(proposition)

    def apply_action(self, action_str: str):
        """Apply a grounded action to the state based on domain definitions."""
        # Clean action: e.g. "(pick-up b1)" -> "pick-up b1"
        clean = action_str.strip().replace('(', ' ').replace(')', ' ').strip()
        parts = clean.split()
        if not parts: return
        
        act_name = parts[0].lower()
        args = parts[1:]
        
        if act_name not in self._actions:
            return # skip unknown actions
            
        action_def = self._actions[act_name]
        params = action_def['params']
        
        if len(args) != len(params):
            return
            
        # Map variables to arguments
        mapping = dict(zip(params, args))
        
        def substitute(prop: str) -> str:
            # prop is like "(clear ?x)"
            tokens = prop.replace('(', ' ( ').replace(')', ' ) ').split()
            res = []
            for t in tokens:
                if t in mapping:
                    res.append(mapping[t])
                else:
                    res.append(t)
            s = " ".join(res)
            # clean up spaces
            s = s.replace('( ', '(').replace(' )', ')')
            return s
            
        # apply deletes first
        for d in action_def['del']:
            ground_d = substitute(d)
            self.propositions.discard(ground_d)
            
        # apply adds
        for a in action_def['add']:
            ground_a = substitute(a)
            self.propositions.add(ground_a)

    def apply_effects(self, add_list: list[str], delete_list: list[str]):
        """Apply STRIPS-style add/delete effects manually."""
        for prop in delete_list:
            self.propositions.discard(prop)
        for prop in add_list:
            self.propositions.add(prop)

    # ------------------------------------------------------------------ #
    # Serialisation (for LLM prompts)
    # ------------------------------------------------------------------ #

    def to_natural_language(self) -> str:
        """Render current state as a readable string for LLM context."""
        sorted_props = sorted(self.propositions)
        lines = [f"=== CURRENT WORLD STATE ({len(sorted_props)} facts) ==="]
        for p in sorted_props:
            lines.append(f"  {p}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialise to JSON-safe dict."""
        return {
            "domain_name": self.domain_name,
            "objects": self.objects,
            "propositions": sorted(self.propositions),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BeliefBase":
        return cls(
            propositions=set(d.get("propositions", [])),
            objects=d.get("objects", []),
            domain_name=d.get("domain_name", ""),
        )
