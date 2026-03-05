---
description: 漏斗式计划工作流 — 从模糊想法到原子级开发清单，四步编排 brainstorming → architecture → writing-plans → concise-planning / planning-with-files
---

// turbo-all

# /plan — 漏斗式计划编排工作流

> **核心理念**: 宏观构思 → 架构评估 → 步骤拆解 → 文件落地
>
> 每一步的输出是下一步的输入，逐层收窄，最终交付可执行的原子级任务清单。

---

## Step 0: 前置准备 — 确认输入级别并决定入口

```
用户提供了什么级别的输入？
│
├── 🔮 模糊想法 → 从 Step 1 开始
├── 📋 已有 Spec/需求 → 跳到 Step 2 或 Step 3
├── 🏗️ 已有架构 + Spec → 直接 Step 3
└── 📝 已有任务拆解 → 直接 Step 4
    ├── 普通任务 (<15 文件) → 路径 A (@concise-planning)
    └── 复杂任务 (几十个文件) → 路径 B (@planning-with-files)
```

**准备动作**：
1. 读取 `README.md`、`GEMINI.md`、`docs/conductor/workflow.md` 等上下文文件
2. 检查 `.agent/workflows/` 中已有工作流
3. 查阅 Knowledge Items 中近期决策记录

---

## Step 1: 构思阶段 — 模糊想法 → 具体设计

**呼叫 Skill**: `@brainstorming`
**Skill 位置**: `~/.gemini/antigravity/skills/brainstorming/SKILL.md`

**触发条件**: 用户只有模糊想法（如 "我想做一个基于 RAG 的法律咨询 AI"）

**执行要点**:
1. 读取 `brainstorming` SKILL.md 的完整指令
2. 以**设计促进者**身份运作，**严禁写任何代码**
3. **一次只问一个问题**，优先用多选题
4. 锁定理解（Understanding Lock）—— 5-7 个要点摘要
5. 明确非功能需求（性能、安全、可靠性等）
6. 提出 2-3 种可行设计方案及取舍分析
7. 维护**决策日志**（Decision Log）

**退出门控**（Hard Gate，全部满足才可进入下一步）：
- [x] Understanding Lock 已由用户确认
- [x] 至少一种设计方案被接受
- [x] 主要假设已记录
- [x] 关键风险已承认
- [x] 决策日志完整

**交付物**: `design_spec.md` — 含理解摘要、假设、决策日志、最终设计

> [!IMPORTANT]
> 如果设计是高影响/高风险的，**必须**在进入下一步前将设计和决策日志交给 `@multi-agent-brainstorming` 进行多代理验证。

---

## Step 2: 架构决策 — 技术栈选型与权衡评估（可选，针对复杂系统）

**呼叫 Skill**: `@architecture`
**Skill 位置**: `~/.gemini/tmp/claude-code-templates-repo/cli-tool/components/skills/development/architecture/SKILL.md`

**触发条件**: 系统涉及多模块、多技术栈、需权衡取舍时

**执行要点**:
1. 读取 `architecture` SKILL.md 及相关子文件：
   - `context-discovery.md` — 起始架构设计时读
   - `trade-off-analysis.md` — 记录决策时读
   - `pattern-selection.md` — 选择模式时读
   - `examples.md` — 参考实现
   - `patterns-reference.md` — 模式速查
2. 遵循选择性阅读规则：只读与当前请求相关的文件
3. 核心原则："**简单就是极致的精巧**" — 只在必要时增加复杂性

**验证清单**（完成前必查）：
- [ ] 需求清晰理解
- [ ] 约束已识别
- [ ] 每个决策有取舍分析
- [ ] 已考虑更简单的替代方案
- [ ] ADR 已为重大决策编写
- [ ] 团队技术能力匹配所选模式

**交付物**: 架构决策记录（ADR）+ 系统组件图（Mermaid）

---

## Step 3: 需求转执行步骤 — Spec → 带依赖的 TDD 式任务拆解

**呼叫 Skill**: `@writing-plans`（完整版）或 `@plan-writing`（精简版）

### 路径选择

| 场景 | 推荐 Skill | 特点 |
|------|-----------|------|
| 需要完整 TDD 式拆解、含代码片段 | `@writing-plans` | 每步 2-5 分钟、含完整测试代码 |
| 需要快速结构化拆解、不含嵌入代码 | `@plan-writing` | 最多 10 个任务、1 页以内 |

### 路径 3A: @writing-plans（完整 TDD 式）

**Skill 位置**: `~/.gemini/tmp/claude-code-templates-repo/cli-tool/components/skills/development/writing-plans/SKILL.md`

**执行要点**:
1. 起始宣告："I'm using the writing-plans skill to create the implementation plan."
2. 每步是一个原子动作（2-5 分钟）：
   - 写失败测试 → 运行确认 fail → 写最小实现通过 → 运行确认 pass → 提交
3. 计划文件保存到 `docs/plans/YYYY-MM-DD-<feature-name>.md`
4. 包含：精确文件路径、完整代码、精确命令 + 预期输出
5. DRY / YAGNI / TDD / 频繁提交

**交付物**: `docs/plans/YYYY-MM-DD-<feature>.md`，完成后提供两种执行路线选择（子代理驱动 / 并行会话）

### 路径 3B: @plan-writing（精简结构化）

**Skill 位置**: `~/.gemini/tmp/claude-code-templates-repo/cli-tool/components/skills/productivity/plan-writing/SKILL.md`

**执行要点**:
1. 计划保存为 `{task-slug}.md` 在**项目根目录**
2. 最多 10 个任务，超过则拆成多个计划
3. 每个任务有明确的验证标准
4. 根据项目类型动态调整内容（新项目 / 功能新增 / Bug 修复）
5. **验证阶段永远是最后一个 Phase**

**交付物**: `<task-slug>.md` 在项目根目录

---

## Step 4: 原子级开发清单 / 文件级计划落地

### 路径 A: 普通任务 → `@concise-planning`

**Skill 位置**: `~/.gemini/antigravity/skills/concise-planning/SKILL.md`

**触发条件**: 任务相对直接（<15 个文件变更）

**执行要点**:
1. 快速扫描上下文（README、相关代码文件）
2. 最多问 1-2 个阻塞性问题
3. 生成精简计划：
   - **Approach**: 1-3 句说明做什么和为什么
   - **Scope**: In / Out 范围边界
   - **Action Items**: 6-10 个原子级有序任务（动词开头）
   - **Validation**: 至少一个测试/验证项
   - **Open Questions**: 最多 3 个待定问题

**交付物**: 单份 `plan.md`，直接可执行

---

### 路径 B: 极度复杂任务 → `@planning-with-files`

**Skill 位置**: `~/.gemini/antigravity/skills/planning-with-files/SKILL.md`（或 `~/.gemini/tmp/.../workflow-automation/planning-with-files/`）

**触发条件**: 涉及几十个文件变更、多阶段研究、跨模块重构

**执行要点**:
1. 在**项目根目录**创建三个持久化文件：
   - `task_plan.md` — 阶段跟踪、进度、决策
   - `findings.md` — 研究发现、API 学习
   - `progress.md` — 会话日志、测试结果
2. **2-Action Rule**: 每两次操作后保存关键发现
3. **Read Before Decide**: 每次重大决策前重新阅读计划文件
4. **3-Strike Error Protocol**: 三次同类失败后升级给用户
5. **5-Question Reboot Test**: 随时确认上下文完整性

**交付物**: 三个 Manus 风格的持久化文件，全程跟踪进展

---

## 注意事项

> [!IMPORTANT]
> - 每一步的输出必须经过用户确认才能进入下一步
> - brainstorming 阶段**严禁**编写任何代码
> - 所有假设必须显式记录，标注为 `[ASSUMPTION]`
> - YAGNI 原则贯穿始终 — 不添加"将来可能用到"的东西

> [!TIP]
> - Step 2 对简单功能可跳过
> - Step 3 中 `@writing-plans` 适合需要 TDD 保障的核心功能，`@plan-writing` 适合快速原型或小特性
> - 工作流可嵌套：大项目的 Step 3 中，可为每个子系统分别调用 Step 4
> - 如果已有 Knowledge Item 覆盖相关领域，优先查阅复用
