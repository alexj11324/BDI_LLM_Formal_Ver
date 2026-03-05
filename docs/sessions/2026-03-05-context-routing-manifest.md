# Context Routing Manifest — BDI Dynamic Replanning
> Generated: 2026-03-05 | Layer: context-window-management (执行层)
> Purpose: 指导下一次会话的上下文窗口装载策略

## 🔴 P0 — 必须注入（Critical Path，首尾位置）

这些信息直接决定下次会话能否继续推进，必须出现在 Prompt 的**开头或末尾**（Serial Position Effect 最佳位置）。

| 信息类型 | 内容 | 来源 |
|----------|------|------|
| **阻塞项** | `DASHSCOPE_API_KEY` 仍未注入，E2E 测试无法通过 | Session state |
| **运行命令** | `export DASHSCOPE_API_KEY=<key> && python scripts/run_dynamic_replanning.py --domain blocksworld --instances 1` | Next step |
| **超时配置** | `Config.TIMEOUT = 600s`，所有 LLM 调用已统一 | Decision record |
| **`.env` 陷阱** | `python-dotenv` 不支持 `${VAR}` 展开，API key 必须硬编码字面值 | Persistent fact |

## 🟡 P1 — 按需召回（Retrieve from Entity Memory）

这些信息在具体操作时需要，但不必占用宝贵的首尾窗口位置。当 Agent 需要修改某文件或调试某模块时，从实体记忆库中召回即可。

| 触发场景 | 应召回的实体 | 记忆库位置 |
|----------|------------|-----------|
| 修改 replanning 逻辑 | `BeliefBase`, `PlanExecutor`, `DynamicReplanner` 的接口与职责 | entity-memory-store.md |
| 调试 API 调用 | `litellm` → `DashScope` 路由关系、`qwen3.5-plus` 模型名 | entity-memory-store.md |
| 扩展到新域 | Logistics / Depots 的 PDDL 域文件路径与注册方式 | entity-memory-store.md |
| 查看评测脚本 | `run_dynamic_replanning.py` 的 `--resume` / checkpoint 机制 | entity-memory-store.md |

## 🟢 P2 — 可安全裁剪（Trim / Omit）

这些信息已完成其使命或与下阶段无关，下次会话可安全丢弃，不会造成"上下文腐化"或重复探索。

| 信息 | 裁剪理由 |
|------|---------|
| Skills MCP Server 调试全过程 | 已完成，`skills-mcp-server.py` 功能正常 |
| `npx skills find/add/remove` 的 CLI 用法探索 | 已封装进 MCP，不需要再手动操作 |
| Session Summary Skill 搜索与安装过程 | 两个 Skill 已装好，不影响 BDI 项目 |
| `sickn33/antigravity-awesome-skills` 全量安装过程 | 已完成，900+ skills 注册完毕 |
| `BeliefBase` 单元测试的详细输出 | 测试通过，结论已记录，无需保留原始输出 |
| `pkill` MCP 进程的操作细节 | 一次性操作，已解决 |

## 📐 窗口预算分配建议

假设下次会话的有效窗口为 ~200K tokens：

```
┌──────────────────────────────────────────────┐
│  [HEAD — 5%]  P0 阻塞项 + 运行命令            │  ← Serial Position: 最强记忆区
│  [BODY — 15%] P1 按需实体（仅在触发时注入）      │
│  [BODY — 70%] 新会话的实际工作内容               │
│  [TAIL — 10%] P0 Next Steps 重申              │  ← Serial Position: 次强记忆区
│  [TRIM]       P2 内容全部丢弃                   │
└──────────────────────────────────────────────┘
```

## 上下文健康度评估

| 维度 | 评分 (1-5) | 备注 |
|------|-----------|------|
| Accuracy (技术细节) | 4.5 | 文件路径、配置值、错误信息均已精确记录 |
| Artifact Trail (文件追踪) | 4.0 | 6 个修改文件已完整列出 |
| Continuity (可续性) | 2.0 | ⚠️ 被 API Key 阻塞，无法验证最终结果 |
| Decision Integrity (决策完整性) | 5.0 | 4 项决策均有明确理由 |
