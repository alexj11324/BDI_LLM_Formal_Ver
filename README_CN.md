# BDI-LLM 形式化验证框架

[English](README.md) | 简体中文

一个使用大语言模型生成并验证 BDI 计划的框架，提供形式化验证保证。

## 概述

本项目实现了一个混合规划架构，将大语言模型的生成能力与严格的形式化验证方法相结合。通过强制执行结构和语义约束，解决了 LLM 生成计划中的幻觉和逻辑不一致问题。

### 核心特性

*   **混合 BDI + LLM 规划**：从自然语言目标生成结构化的 BDI 计划（信念、愿望、意图）。
*   **多层验证**：
    1.  **结构验证**：确保计划形成有效的有向无环图（DAG）且弱连通。
    2.  **符号验证**：集成基于 PDDL 的验证（使用 VAL）来检查逻辑一致性。
    3.  **物理验证**：领域特定的物理验证器（如 Blocksworld）确保动作可行性。
*   **自动修复机制**：自动修复常见的结构错误（如断开的子图），无需重新查询 LLM。
*   **基准测试**：内置支持在 PlanBench 数据集上进行评估。

## PlanBench 评估结果

使用 `vertex_ai/gemini-3-flash-preview` 模型在三个规划领域上进行评估（冻结快照：2026-02-13）。

| 领域 | 通过 | 总数 | 准确率 |
|---|---|---|---|
| Blocksworld | 200 | 200 | **100.0%** |
| Logistics | 568 | 570 | **99.6%** |
| Depots | 497 | 500 | **99.4%** |
| **总计** | **1265** | **1270** | **99.6%** |

所有领域中仅有 5 个实例失败。详细的结果溯源和 SHA256 校验和请参见[论文结果溯源](docs/PAPER_RESULT_PROVENANCE.md)。

## 安装

1.  克隆仓库：
    ```bash
    git clone https://github.com/alexj11324/BDI_LLM_Formal_Ver.git
    cd BDI_LLM_Formal_Ver
    ```

2.  安装依赖：
    ```bash
    pip install -r requirements.txt
    ```

3. 设置环境变量：
    ```bash
    cp .env.example .env
    # 编辑 .env 添加你的 API_KEY，可选配置 API_BASE
    nano .env
    ```
    或者直接导出：
    ```bash
    export OPENAI_API_KEY="your-api-key"
    # 可选：如果使用网关，设置自定义 API base URL
    export OPENAI_API_BASE="https://your-gateway-url/v1"
    ```

## 使用方法

### 运行评估

运行主评估脚本来测试框架：

```bash
python scripts/run_evaluation.py --mode [unit|demo|benchmark]
```

*   `unit`：运行核心组件的单元测试。
*   `demo`：运行带自动修复的实时 LLM 演示。
*   `benchmark`：在 PlanBench 数据集上运行评估。

### 项目结构

```
BDI_LLM_Formal_Ver/
├── src/bdi_llm/                          # 核心规划器 + 验证模块
├── scripts/                              # 评估和工具脚本
├── tests/                                # 单元测试和集成测试
├── docs/                                 # 用户/系统/溯源文档
├── planbench_data/                       # PlanBench 数据集 + VAL 二进制文件
├── runs/                                 # 可变输出 + 历史运行记录（见 runs/README.md）
│   └── legacy/planbench_results_20260211/  # 冻结前的历史输出
├── artifacts/paper_eval_20260213/        # 冻结的论文证据快照
├── planbench_results_archive.tar.gz      # 原始归档实验包
└── requirements.txt                      # 项目依赖
```

## 文档

*   [用户指南](docs/USER_GUIDE.md)：详细的使用和配置指南。
*   [系统架构](docs/ARCHITECTURE.md)：系统架构和验证层。
*   [基准测试](docs/BENCHMARKS.md)：评估方法和结果。
*   [论文结果溯源](docs/PAPER_RESULT_PROVENANCE.md)：冻结的论文结果证据链和验证流程。
*   [仓库组织](docs/REPO_ORGANIZATION.md)：目录职责和清理规则。

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。
