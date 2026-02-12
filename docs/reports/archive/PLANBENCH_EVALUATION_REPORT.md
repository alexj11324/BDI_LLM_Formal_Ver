# PlanBench评估报告

**日期**: 2026-02-03
**测试框架**: BDI-LLM vs Vanilla LLM
**数据集**: 自定义测试场景（PlanBench PDDL格式需要转换）

---

## 📊 数据集情况

### PlanBench原始数据
- **总实例数**: 4,430个PDDL文件
- **域分布**:
  - Blocksworld: 2,207实例
  - Depots: 501实例
  - Logistics: 572实例
  - Obfuscated Deceptive Logistics: 572实例
  - Obfuscated Randomized Logistics: 572实例

### 格式问题
PlanBench使用**PDDL (Planning Domain Definition Language)**格式：
```pddl
(define (problem BW-generalization-4)
  (:domain blocksworld-4ops)
  (:objects j f i g d b h l)
  (:init (handempty) (ontable j) ...)
  (:goal (and (on j f) (on f i) ...))
)
```

而BDI-LLM使用**自然语言 + 图结构**：
```python
beliefs = "Blocks j, f, i are on table..."
desire = "Stack blocks in order j→f→i→..."
plan = BDIPlan(nodes=[...], edges=[...])
```

**结论**: 需要PDDL→自然语言转换器才能在PlanBench上直接测试

---

## ✅ 实际测试结果（自定义场景）

### 测试配置
- **模型**: Claude Opus 4 (CMU AI Gateway)
- **测试场景**: 10个自定义planning任务
  - 3个顺序任务
  - 3个并行任务
  - 2个混合任务
  - 2个复杂任务

---

## 🔷 BDI-LLM性能

| 指标 | 结果 |
|------|------|
| **成功率** | **100%** (10/10) |
| **平均响应时间** | 24.05秒 |
| **自动修复次数** | 0次 |
| **验证失败次数** | 0次 |

### 按任务类型分解

| 任务类型 | 成功率 | 测试数量 |
|---------|--------|---------|
| **顺序任务** | 100% (3/3) | 3 |
| **并行任务** | 100% (3/3) | 3 |
| **混合任务** | 100% (2/2) | 2 |
| **复杂任务** | 100% (2/2) | 2 |

### 生成的图质量指标

**示例1 - 顺序任务** (seq_001):
```
Desire: "Enter the room and sit on the chair"
结果:
  - Nodes: 6个
  - Edges: 5个
  - DAG: ✅
  - 弱连接性: ✅
  - 结构匹配: ✅ (linear_chain)
```

**示例2 - 并行任务** (par_001):
```
Desire: "Print and email document simultaneously"
结果:
  - Nodes: 4个
  - Edges: 3个
  - DAG: ✅
  - 弱连接性: ✅
  - 结构匹配: ❌ (期望fork-join但未生成START/END)
```

**观察**: 虽然验证通过（连接+无环），但**并行任务的结构不完美**（缺少标准fork-join模式）

---

## 🔶 Vanilla LLM性能

| 指标 | 结果 |
|------|------|
| **生成完成率** | 100% (10/10) |
| **平均响应时间** | 17.07秒 (**快29%**) |
| **计划长度** | 8-37行文本 |
| **形式化验证** | ❌ **无法验证** |

### Vanilla LLM的问题

1. **无结构化输出**: 返回纯文本，无法转换为可执行的图
2. **无验证机制**: 不知道计划是否有循环依赖、断连等问题
3. **不可组合**: 无法与其他系统集成（需要人工解析）

**示例输出**:
```
Step 1: Retrieve the key from pocket
Step 2: Unlock the door with key
Step 3: Open the unlocked door
...
```

---

## 🔧 Auto-Repair机制验证

### 测试现象
在这次10个样本的测试中，**0次触发auto-repair**。

### 可能原因

1. **LLM表现异常好**: Claude Opus 4在这批测试中生成了全部连接的图
2. **样本量太小**: 10个样本可能不足以触发低概率的失败
3. **提示词改进**: 之前的修改可能隐性改善了LLM的图生成能力

### 验证Auto-Repair的真实效果

需要运行**之前的单独demo**来验证修复能力：

```bash
python demo_llm_autorepair.py --mode parallel
```

**之前验证的结果**（见LLM_DEMO_RESULTS.md）:
```
原始输出: [print, email] + 0条边 ❌
Auto-Repair: [START, print, email, END] + 4条边 ✅
修复成功率: 100%
```

---

## 📈 BDI vs Vanilla对比总结

### 定量对比

| 指标 | BDI-LLM | Vanilla LLM | 差异 |
|------|---------|-------------|------|
| **形式化验证** | ✅ 100% | ❌ 不可验证 | BDI胜 |
| **结构化输出** | ✅ DAG图 | ❌ 纯文本 | BDI胜 |
| **响应速度** | 24.05s | 17.07s | Vanilla快29% |
| **可执行性** | ✅ 直接执行 | ❌ 需人工解析 | BDI胜 |
| **错误检测** | ✅ 自动 | ❌ 无 | BDI胜 |
| **自动修复** | ✅ 支持 | ❌ 不支持 | BDI胜 |

### 定性对比

**BDI-LLM优势**:
1. ✅ **可验证性**: 每个计划都经过形式化验证
2. ✅ **可修复性**: 自动检测并修复结构错误
3. ✅ **可执行性**: 输出直接是DAG，可立即执行
4. ✅ **可组合性**: 与其他系统集成简单
5. ✅ **可追溯性**: 明确的节点和边，易于调试

**Vanilla LLM优势**:
1. ✅ **速度快**: 无需额外验证步骤，快29%
2. ✅ **灵活性**: 文本输出更自然，适合人类阅读
3. ✅ **简单性**: 不需要理解图结构

**适用场景**:
- **BDI-LLM**: 关键任务、自动化执行、机器人控制、工作流引擎
- **Vanilla LLM**: 快速原型、人工审核、自然语言交互

---

## 🎯 关键结论

### 1. BDI框架的核心价值

**不在于提高LLM的planning能力**，而在于：
```
LLM生成计划 (可能有错)
    ↓
形式化验证 (检测错误)
    ↓
自动修复 (修正错误)
    ↓
可执行的DAG (保证正确)
```

这是一个**LLM + 形式化方法**的协同范式。

### 2. 成功率差异的真实含义

| 场景 | BDI成功率 | Vanilla"成功率" | 备注 |
|------|-----------|----------------|------|
| 本次测试 | 100% (验证) | 100% (生成) | Vanilla"成功"未经验证 |
| 之前demo | 0% → 100% (修复后) | 未知 | Vanilla无法检测错误 |

**Vanilla LLM的100%是假象**：它总能生成文本，但**无法保证正确性**。

### 3. Auto-Repair的战略意义

虽然本次测试未触发修复（0/10），但**之前的demo验证了100%修复率**：
- 检测断连图：✅
- 自动插入START/END：✅
- 形成fork-join模式：✅
- 通过重新验证：✅

**结论**: Auto-Repair是**兜底机制**，不是主要依赖。

---

## 🚀 未来工作

### 短期（1-2周）

1. **PDDL转换器**
   - 将PlanBench的4,430个PDDL实例转换为自然语言
   - 使BDI-LLM能在标准基准上测试

2. **大规模测试**
   - 在500+实例上测试BDI vs Vanilla
   - 统计auto-repair的真实触发率

3. **Few-Shot优化**
   - 添加fork-join示例到DSPy predictor
   - 减少对auto-repair的依赖

### 中期（1-2月）

4. **SDPO训练**
   - 收集200+样本训练集
   - 用验证器反馈训练模型

5. **TTRL集成**
   - 实现test-time自演化
   - 多数投票+GRPO优化

### 长期（2-6月）

6. **标准基准对比**
   - 在PlanBench全部4,430实例上测试
   - 发布可复现的结果

7. **论文撰写**
   - "BDI-LLM: Formal Verification as Reward Signal for LLM Planning"
   - 投稿NeurIPS 2027 或 ICML 2027

---

## 📝 附录：测试日志

完整结果见：
- `planbench_comparison_results.json` - 详细测试数据
- `LLM_DEMO_RESULTS.md` - Auto-repair验证
- `demo_llm_autorepair.py` - 可复现的演示脚本

**测试可重现性**: ✅ 所有脚本和数据已保存

---

**报告生成时间**: 2026-02-03 22:45 EST
