#!/usr/bin/env python3
"""
分析并行任务场景失败的原因
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import networkx as nx

# 创建图形
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

# ========== 左图: LLM 生成的错误结果 ==========
ax1.set_title("❌ LLM 生成的计划（断开的图）", fontsize=14, fontweight='bold', color='red')
ax1.set_xlim(0, 10)
ax1.set_ylim(0, 10)
ax1.axis('off')

# 绘制两个独立的子图
# 子图 1: 打印任务
ax1.add_patch(FancyBboxPatch((0.5, 6), 3, 1.5, boxstyle="round,pad=0.1",
                              edgecolor='blue', facecolor='lightblue', linewidth=2))
ax1.text(2, 6.75, 'Print Document', ha='center', va='center', fontsize=11, fontweight='bold')

ax1.add_patch(FancyBboxPatch((0.5, 3.5), 3, 1.5, boxstyle="round,pad=0.1",
                              edgecolor='blue', facecolor='lightblue', linewidth=2))
ax1.text(2, 4.25, 'Turn Off Printer', ha='center', va='center', fontsize=11, fontweight='bold')

# 箭头
arrow1 = FancyArrowPatch((2, 6), (2, 5), arrowstyle='->', lw=2, color='blue',
                         mutation_scale=20)
ax1.add_patch(arrow1)

# 子图 2: 邮件任务（独立的！）
ax1.add_patch(FancyBboxPatch((6.5, 6), 3, 1.5, boxstyle="round,pad=0.1",
                              edgecolor='green', facecolor='lightgreen', linewidth=2))
ax1.text(8, 6.75, 'Send Email', ha='center', va='center', fontsize=11, fontweight='bold')

ax1.add_patch(FancyBboxPatch((6.5, 3.5), 3, 1.5, boxstyle="round,pad=0.1",
                              edgecolor='green', facecolor='lightgreen', linewidth=2))
ax1.text(8, 4.25, 'Turn On Computer', ha='center', va='center', fontsize=11, fontweight='bold')

# 箭头
arrow2 = FancyArrowPatch((8, 6), (8, 5), arrowstyle='->', lw=2, color='green',
                         mutation_scale=20)
ax1.add_patch(arrow2)

# 添加警告标记
ax1.text(5, 2, '⚠️ 两个独立的子图！\n无法找到统一的执行顺序',
         ha='center', fontsize=12, color='red', fontweight='bold',
         bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))

# 添加断开标记
ax1.plot([4, 6], [5, 5], 'r--', linewidth=3, alpha=0.5)
ax1.text(5, 5.5, '❌ 断开', ha='center', fontsize=10, color='red', fontweight='bold')

# ========== 右图: 正确的结构 ==========
ax2.set_title("✅ 正确的计划（连通的 DAG）", fontsize=14, fontweight='bold', color='green')
ax2.set_xlim(0, 10)
ax2.set_ylim(0, 10)
ax2.axis('off')

# 起始节点
ax2.add_patch(FancyBboxPatch((3.5, 8.5), 3, 1, boxstyle="round,pad=0.1",
                              edgecolor='purple', facecolor='plum', linewidth=2))
ax2.text(5, 9, 'START (Virtual)', ha='center', va='center', fontsize=11, fontweight='bold')

# 并行任务
ax2.add_patch(FancyBboxPatch((0.5, 6), 3, 1.5, boxstyle="round,pad=0.1",
                              edgecolor='blue', facecolor='lightblue', linewidth=2))
ax2.text(2, 6.75, 'Print Document', ha='center', va='center', fontsize=11, fontweight='bold')

ax2.add_patch(FancyBboxPatch((6.5, 6), 3, 1.5, boxstyle="round,pad=0.1",
                              edgecolor='green', facecolor='lightgreen', linewidth=2))
ax2.text(8, 6.75, 'Send Email', ha='center', va='center', fontsize=11, fontweight='bold')

# 同步节点
ax2.add_patch(FancyBboxPatch((3.5, 3.5), 3, 1.5, boxstyle="round,pad=0.1",
                              edgecolor='orange', facecolor='lightyellow', linewidth=2))
ax2.text(5, 4.25, 'Turn Off Printer\n(After both done)', ha='center', va='center',
         fontsize=10, fontweight='bold')

# 箭头：START -> 并行任务
arrow3 = FancyArrowPatch((4, 8.5), (2, 7.5), arrowstyle='->', lw=2, color='purple',
                         mutation_scale=20, connectionstyle="arc3,rad=0.3")
ax2.add_patch(arrow3)

arrow4 = FancyArrowPatch((6, 8.5), (8, 7.5), arrowstyle='->', lw=2, color='purple',
                         mutation_scale=20, connectionstyle="arc3,rad=-0.3")
ax2.add_patch(arrow4)

# 箭头：并行任务 -> 同步节点
arrow5 = FancyArrowPatch((2, 6), (4, 5), arrowstyle='->', lw=2, color='blue',
                         mutation_scale=20, connectionstyle="arc3,rad=0.3")
ax2.add_patch(arrow5)

arrow6 = FancyArrowPatch((8, 6), (6, 5), arrowstyle='->', lw=2, color='green',
                         mutation_scale=20, connectionstyle="arc3,rad=-0.3")
ax2.add_patch(arrow6)

# 添加说明
ax2.text(5, 1.5, '✅ 所有节点连通！\n有明确的同步点（Join Point）',
         ha='center', fontsize=12, color='green', fontweight='bold',
         bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))

plt.suptitle('并行任务场景失败原因分析', fontsize=16, fontweight='bold', y=0.98)
plt.tight_layout()
plt.savefig('parallel_task_failure_analysis.png', dpi=300, bbox_inches='tight')
print("✅ 可视化已保存到: parallel_task_failure_analysis.png")

# 创建第二张图：NetworkX 示意图
fig2, (ax3, ax4) = plt.subplots(1, 2, figsize=(14, 6))

# 错误的图
G_wrong = nx.DiGraph()
G_wrong.add_edges_from([
    ('Print', 'TurnOffPrinter'),
    ('TurnOnComputer', 'SendEmail')
])

pos_wrong = {
    'Print': (0, 1),
    'TurnOffPrinter': (0, 0),
    'TurnOnComputer': (2, 1),
    'SendEmail': (2, 0)
}

nx.draw(G_wrong, pos_wrong, ax=ax3, with_labels=True, node_color='lightcoral',
        node_size=3000, font_size=9, font_weight='bold', arrows=True,
        arrowsize=20, edge_color='red', width=2)
ax3.set_title('❌ 错误: 2 个独立子图\n(Disconnected)', fontsize=12, fontweight='bold', color='red')

# 检测连通性
num_components = nx.number_weakly_connected_components(G_wrong)
ax3.text(1, -0.8, f'弱连通分量数: {num_components}\n拓扑排序: 不可能❌',
         ha='center', fontsize=10,
         bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))

# 正确的图
G_correct = nx.DiGraph()
G_correct.add_edges_from([
    ('START', 'Print'),
    ('START', 'SendEmail'),
    ('Print', 'TurnOffPrinter'),
    ('SendEmail', 'TurnOffPrinter')
])

pos_correct = {
    'START': (1, 2),
    'Print': (0, 1),
    'SendEmail': (2, 1),
    'TurnOffPrinter': (1, 0)
}

nx.draw(G_correct, pos_correct, ax=ax4, with_labels=True, node_color='lightgreen',
        node_size=3000, font_size=9, font_weight='bold', arrows=True,
        arrowsize=20, edge_color='green', width=2)
ax4.set_title('✅ 正确: 1 个连通 DAG\n(Connected)', fontsize=12, fontweight='bold', color='green')

# 拓扑排序
topo_order = list(nx.topological_sort(G_correct))
ax4.text(1, -0.8, f'弱连通分量数: 1\n拓扑排序: {" → ".join(topo_order)}',
         ha='center', fontsize=9,
         bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))

plt.suptitle('图论视角：连通性检查', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('graph_connectivity_analysis.png', dpi=300, bbox_inches='tight')
print("✅ 图论分析已保存到: graph_connectivity_analysis.png")
