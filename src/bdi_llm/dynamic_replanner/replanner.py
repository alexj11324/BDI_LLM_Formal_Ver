import logging

import instructor
from openai import OpenAI

from src.bdi_llm.config import Config
from src.bdi_llm.dynamic_replanner.executor import ExecutionResult
from src.bdi_llm.schemas import BDIPlan

logger = logging.getLogger(__name__)


class DynamicReplanner:
    """
    Handles dynamic replanning (repair) by sending execution feedback
    to an LLM to generate a recovery plan. Utilizes explicit Context Cache
    where supported (e.g. qwen3.5-plus).
    """

    def __init__(self, model_name: str = None, max_retries: int = 3):
        # We explicitly want to use a model that supports caching.
        if model_name is None:
            model_name = Config.MODEL_NAME
            
        # Strip provider prefixes (like 'openai/') when using direct OpenAI client 
        # against a compatible endpoint
        if "/" in model_name:
            model_name = model_name.split("/", 1)[1]
            
        self.model_name = model_name
        self.max_retries = max_retries
        self.last_error: str | None = None

        # Use Config for API key and base URL so it works with both
        # DashScope and standard OpenAI environments
        api_key = Config.DASHSCOPE_API_KEY or Config.OPENAI_API_KEY
        base_url = Config.OPENAI_API_BASE or 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        
        raw_client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={"User-Agent": "curl/7.68.0"},
            timeout=Config.TIMEOUT,
        )
        
        # Syntax Pivot: Wrap client with Instructor for guaranteed structured JSON output
        # Use Mode.JSON to avoid 'tool_choice' errors when using thinking models
        self.client = instructor.from_openai(raw_client, mode=instructor.Mode.JSON)

    def generate_recovery_plan(
        self,
        beliefs: str,
        desire: str,
        execution_result: ExecutionResult
    ) -> BDIPlan | None:
        """
        Constructs a cached prompt containing the original context + the new failure
        feedback, and requests a recovery plan.
        """

        # 1. System Prompt (Cacheable)
        system_prompt = """You are a highly capable BDI (Belief-Desire-Intention) agent.
Your task is to REPLAN an operation from a newly updated belief state. 
You previously executed a plan, but it was interrupted. We have extracted the EXACT GROUND TRUTH
state from the environment at the moment of interruption.

You must treat this as a COMPLETELY NEW zero-shot planning task starting from this new state.
DO NOT attempt to "patch" or "fix" the old plan. Just look at the CURRENT WORLD STATE,
look at the GOAL, and generate a continuous JSON DAG plan of the REMAINING actions needed.

CRITICAL INSTRUCTION ON ACTION PARAMETERS:
You must strictly follow the required parameters for each action. Do not omit parameters.
For example, if an action requires (truck loc-from loc-to city), you must provide all four.

CRITICAL INSTRUCTION ON OUTPUT SIZE:
Prefer a simple linear recovery plan unless parallel branches are absolutely necessary.
Use concise sequential node IDs such as step_1, step_2, ... and keep dependency edges minimal.
"""

        # 2. Environment Context (Beliefs & Desire) - Cacheable
        environment_context = f"=== ORIGINAL GOAL ===\n{desire}"
        
        if hasattr(execution_result, '_actions_schema') and execution_result._actions_schema:
            environment_context += "\n\n=== ALLOWED ACTIONS & PARAMETERS ===\n"
            for act_name, act_def in execution_result._actions_schema.items():
                params = " ".join(act_def['params'])
                environment_context += f"- ({act_name} {params})\n"

        # 3. Execution Feedback (Dynamic part, not cached)
        executed_str = "None"
        if execution_result.executed_actions:
            executed_str = "\n".join(
                f"{i + 1}. {a}" for i, a in enumerate(execution_result.executed_actions)
            )

        failure_reasons_str = "None provided"
        if execution_result.failure_reason:
            failure_reasons_str = "\n".join(f"- {r}" for r in execution_result.failure_reason)

        current_state_str = execution_result.current_state or "State not available"

        # Feedback Pivot: Differential Belief Injection
        unsatisfied_core = ""
        if execution_result.failure_reason:
            for reason in execution_result.failure_reason:
                if "Unsatisfied precondition" in reason or "goal is not satisfied" in reason.lower() or "Advice:" in reason:
                    unsatisfied_core += f"\n🚨 CRITICAL DIFFERENCE 🚨: {reason}\nYou MUST bridge this specific gap starting from the NEW BELIEF STATE!\n"

        feedback_prompt = f"""
=== PLAN INTERRUPTION INFO ===
Successfully executed actions so far:
{executed_str}

The plan was interrupted because the next action ({execution_result.failed_action}) was invalid:
{failure_reasons_str}
{unsatisfied_core}

=== NEW BELIEF STATE (GROUND TRUTH) ===
This is the absolute true state of the world right now, after the successful actions.
{current_state_str}

=== YOUR TASK ===
1. Analyze your NEW BELIEF STATE.
2. Note the CRITICAL DIFFERENCE between the failed action's expectation and the current reality.
3. Generate a BDI JSON DAG plan for the actions required to reach the GOAL from this exact NEW BELIEF STATE.
4. Prefer a linear chain of actions over a wide graph, to minimize JSON size and avoid truncation.
5. DO NOT include the already successful actions in your new plan. Focus only on what must be done next.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": environment_context,
            },
            {"role": "user", "content": feedback_prompt}
        ]

        self.last_error = None
        for attempt in range(self.max_retries):
            try:
                extra_body = {}
                if "thinking" in self.model_name or "plus" in self.model_name or "5.4" in self.model_name:
                    extra_body["enable_thinking"] = True
                    
                if Config.REASONING_EFFORT:
                    extra_body["reasoning_effort"] = Config.REASONING_EFFORT

                extra_headers = {"x-dashscope-session-cache": "enable"}

                # Syntax Pivot: Use Instructor to force Pydantic schema validation directly
                plan: BDIPlan = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    response_model=BDIPlan, # Force structured output
                    temperature=0.3,
                    max_tokens=8192,
                    extra_body=extra_body,
                    extra_headers=extra_headers,
                    max_retries=2 # Instructor will automatically retry on Pydantic validation errors!
                )
                
                return plan

            except Exception as e:
                self.last_error = str(e)
                logger.warning(f"Replanning attempt {attempt+1} failed: {e}")

        return None
