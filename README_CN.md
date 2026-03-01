# BDI-LLM 形式化验证框架

[English](README.md) | 简体中文

一个神经符号规划框架，将 LLM 生成能力与形式化验证相结合，产出可证明正确的计划。

## 概述

BDI-LLM 通过将每个生成的计划送入 3 层验证流水线，解决 LLM 生成计划中的幻觉和逻辑不一致问题。验证失败的计划会自动修复并重新验证后再返回。

### 核心特性

- **混合 BDI + LLM 规划**：使用 DSPy ChainOfThought 从自然语言目标生成结构化 BDI 计划（信念、愿望、意图），以 DAG 形式表示。
- **3 层验证**：
  1. **结构验证** — 硬错误检查（空图、环）+ 软告警（断开子图）
  2. **符号验证** — 通过 VAL 检查 PDDL 前提条件/效果
  3. **物理验证** — 领域特定状态模拟（如 Blocksworld 的 clear/hand 约束）
- **自动修复**：无需重新查询 LLM 即可修复环路、连接断开的子图（即使其在结构层仅为告警）并规范化节点 ID。使用 VAL 错误信息引导 LLM 修复（最多 3 次尝试）。
- **MCP 服务器**：将 `generate_verified_plan` 作为 MCP 工具暴露，供 Claude Code、Cursor 等 Agent 调用。
- **编程领域**：针对 SWE-bench 软件工程任务的专用规划器（`read-file` → `edit-file` → `run-test` 动作类型）。
- **消融实验支持**：`--execution_mode` 参数（NAIVE / BDI_ONLY / FULL_VERIFIED）用于受控实验。

## PlanBench 评估结果

在三个规划领域上进行全量数据集评估。

### GPT-5（infiniteai，2026-02-27）— 全量数据集

| 领域 | 实例数 | 成功率 |
|------|--------|--------|
| Blocksworld | 1103/1103 | **90.8%**（FULL_VERIFIED） |
| Logistics | 572 | 进行中 |
| Depots | 501 | 进行中 |

### Gemini（2026-02-13）— 论文标准数据

| 领域 | 通过 | 总数 | 准确率 |
|------|------|------|--------|
| Blocksworld | ~200 | ~200 | ~99.8% |
| Logistics | 568 | 570 | **99.6%** |
| Depots | 497 | 500 | **99.4%** |

冻结证据快照：`artifacts/paper_eval_20260213/`（不可修改）。

### 消融实验（GPT-5，blocksworld 1103 实例）

| 模式 | 成功率 | 验证内容 |
|------|--------|----------|
| NAIVE | 91.6% | 无 — 原始 LLM 输出 |
| BDI_ONLY | 91.7% | 仅结构验证（DAG） |
| FULL_VERIFIED | 90.8% | 全部 3 层 — 可证明正确 |

NAIVE 与 FULL_VERIFIED 之间约 1% 的差距表明，验证开销极小，同时提供了形式化正确性保证。

## 安装

1. 克隆仓库：
   ```bash
   git clone https://github.com/alexj11324/BDI_LLM_Formal_Ver.git
   cd BDI_LLM_Formal_Ver
   ```

2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

3. 配置环境变量：
   ```bash
   cp .env.example .env
   # 编辑 .env：按 provider 设置凭据：
   # - OPENAI_API_KEY（OpenAI / NVIDIA 兼容网关）
   # - ANTHROPIC_API_KEY
   # - GOOGLE_API_KEY 或 GOOGLE_APPLICATION_CREDENTIALS
   # 可选：OPENAI_API_BASE（自定义网关）
   ```

## 使用方法

### 测试

```bash
pytest
pytest tests/test_verifier.py -v
pytest tests/test_integration.py -q  # 依赖 API；无可用 provider 凭据时会自动 skip
```

### 评估

```bash
python scripts/run_evaluation.py --mode unit       # 离线单元测试
python scripts/run_evaluation.py --mode demo       # 实时 LLM 演示
python scripts/run_evaluation.py --mode benchmark  # 完整基准测试
```

### PlanBench

```bash
# 单个领域
python scripts/run_planbench_full.py --domain blocksworld --max_instances 100

# 全部领域，并行，指定消融模式
python scripts/run_planbench_full.py --all_domains --execution_mode FULL_VERIFIED \
  --output_dir runs/my_run --parallel --workers 30

# 从 checkpoint 恢复（output_dir 中存在 checkpoint 时自动检测）
python scripts/run_planbench_full.py --domain blocksworld --output_dir runs/my_run
```

### MCP 服务器

```bash
python src/mcp_server_bdi.py
```

暴露 `generate_verified_plan(goal, domain, context, pddl_domain_file, pddl_problem_file)` 作为 MCP 工具。

## 项目结构

```
BDI_LLM_Formal_Ver/
├── src/bdi_llm/          # 核心模块（规划器、验证器、schemas、修复）
├── src/mcp_server_bdi.py # MCP 服务器入口
├── scripts/              # 评估和基准测试脚本
├── tests/                # 单元测试和集成测试
├── planbench_data/       # PlanBench PDDL 实例 + VAL 二进制（macOS arm64）
├── runs/                 # 可变基准输出（不作为论文依据）
├── artifacts/            # 冻结的论文证据快照（不可修改）
└── BDI_Paper/            # LaTeX 源码（AAAI 2026 格式）
```

## 文档

- [用户指南](docs/USER_GUIDE.md)
- [系统架构](docs/ARCHITECTURE.md)
- [基准测试](docs/BENCHMARKS.md)

## 许可证

MIT 许可证 — 详见 [LICENSE](LICENSE)。
