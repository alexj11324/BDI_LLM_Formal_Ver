#!/usr/bin/env python3
"""
改进 Prompt 来修复并行任务场景
"""
import dspy
from schemas import BDIPlan
from verifier import PlanVerifier
import os

# 配置 API
os.environ["OPENAI_API_KEY"] = "sk-CAMQPAfhTgcWPrFfxm_1Zg"
os.environ["OPENAI_API_BASE"] = "https://ai-gateway.andrew.cmu.edu/v1"

lm = dspy.LM(model="openai/claude-opus-4-20250514-v1:0", max_tokens=4000,
             api_base="https://ai-gateway.andrew.cmu.edu/v1")
dspy.configure(lm=lm)

# 改进的 Signature
class ImprovedGeneratePlan(dspy.Signature):
    """
    You are a BDI (Belief-Desire-Intention) Planning Agent.
    Given a set of Beliefs (current context) and a Desire (goal),
    generate a formal Intention (Plan) as a directed graph of actions.

    CRITICAL GRAPH REQUIREMENTS:
    1. The plan MUST be a VALID Directed Acyclic Graph (DAG)
    2. The graph MUST be CONNECTED (weakly connected)
       - Every node must be reachable from at least one other node
       - There should be NO isolated subgraphs

    HANDLING PARALLEL TASKS:
    When the goal involves parallel/simultaneous tasks:
    - Create a virtual START node as the common ancestor
    - Fork: Connect START to both parallel tasks
    - Join: Create a synchronization node that both tasks lead to
    - Example structure:
         START
        /     \\
    Task_A  Task_B
        \\     /
         JOIN

    DEPENDENCIES:
    - Must be logical (e.g., 'UnlockDoor' before 'OpenDoor')
    - Use source->target format (source must happen before target)

    VERIFICATION:
    Your plan will be validated to ensure:
    - No cycles (no deadlocks)
    - Connected graph (no isolated components)
    - Valid topological ordering exists
    """
    beliefs: str = dspy.InputField(desc="Current state of the world and available tools")
    desire: str = dspy.InputField(desc="The high-level goal to achieve")
    plan: BDIPlan = dspy.OutputField(desc="Structured execution plan with nodes and edges")

class ImprovedBDIPlanner(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_plan = dspy.Predict(ImprovedGeneratePlan)

    def forward(self, beliefs: str, desire: str) -> dspy.Prediction:
        pred = self.generate_plan(beliefs=beliefs, desire=desire)
        try:
            plan_obj = pred.plan
            G = plan_obj.to_networkx()
            is_valid, errors = PlanVerifier.verify(G)

            if not is_valid:
                print(f"\n⚠️ Validation errors: {'; '.join(errors)}")
            else:
                print("\n✅ Plan is valid!")
        except Exception as e:
            print(f"\n⚠️ Parsing error: {e}")

        return pred

# 测试并行任务场景
def test_parallel_task():
    print("=" * 60)
    print("测试改进后的 Prompt - 并行任务场景")
    print("=" * 60)

    planner = ImprovedBDIPlanner()

    beliefs = """
    Location: Office.
    Equipment: Computer (off), Printer (on), Phone.
    Available Skills: [TurnOn, TurnOff, Send, Print, Call]
    """

    desire = "Print a document and send an email simultaneously, then turn off the printer."

    print(f"\n🎯 Goal: {desire}")
    print("\n🤖 Generating plan with improved prompt...")

    response = planner(beliefs=beliefs, desire=desire)
    plan = response.plan

    print(f"\n📋 Plan Description: {plan.goal_description}")
    print(f"\n📊 Nodes ({len(plan.nodes)}):")
    for node in plan.nodes:
        print(f"  - [{node.id}] {node.action_type}: {node.description}")

    print(f"\n🔗 Edges ({len(plan.edges)}):")
    for edge in plan.edges:
        print(f"  - {edge.source} → {edge.target}")

    # 验证
    G = plan.to_networkx()
    is_valid, errors = PlanVerifier.verify(G)

    print(f"\n{'='*60}")
    if is_valid:
        print("✅ 验证通过！")
        order = PlanVerifier.topological_sort(G)
        print(f"\n执行顺序: {' → '.join(order)}")

        # 检查连通性
        import networkx as nx
        num_components = nx.number_weakly_connected_components(G)
        print(f"\n弱连通分量数: {num_components}")
        if num_components == 1:
            print("✅ 图是连通的！")
        else:
            print(f"❌ 图有 {num_components} 个独立的子图")
    else:
        print("❌ 验证失败！")
        for error in errors:
            print(f"  - {error}")

    print("=" * 60)
    return is_valid

if __name__ == "__main__":
    success = test_parallel_task()
    print(f"\n{'🎉 成功！' if success else '😞 仍然失败'}")
