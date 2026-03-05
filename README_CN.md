# BDI-LLM 形式化验证框架 (PNSV)

[English](README.md) | 简体中文

本框架是一个神经符号规划框架，通过将大语言模型（LLM）的生成能力与严格的形式化验证进行结合，从而生成可被数学与逻辑证明完全正确、零幻觉的最优执行计划。

## 核心特性

- **混合 BDI + LLM 规划引擎**：能够使用 DSPy 思维链推理（Chain-of-Thought）将自然语言意图直接转化为有向无环图（DAG）形式的 BDI（信念-愿望-意图）规划执行流。
- **三层递进验证流水线**：
  1. **结构验证 (Structural Verification)**：针对图结构执行硬错误检查（空图、闭环）以及发布子图断裂警告。
  2. **符号验证 (Symbolic Verification)**：使用行业金标准二进制引擎 `VAL` 进行纯粹的 PDDL 前置与效果条件评估。
  3. **领域物理模拟 (Physics Simulation)**：在细分领域注入深度验证器（例：Blocksworld 堆叠物理逻辑与 SWE-bench 沙盒环境测试），从业务底层保障逻辑闭环。
- **自修复引擎 (Auto-Repair)**：能够无缝截获各层验证引擎报错，并引导 LLM 进行 DAG 重拓扑、死锁消除与参数修正，全程不会对用户端发生由于 Prompt 信息泄漏导致的混乱。
- **MCP 服务直通互操作**：框架的底层引擎已整体暴装为标准化的 Model Context Protocol (MCP) 服务器，允许诸如 Claude Code, Cursor 等第三方智能代理直接调用，将其作为高权限安全“特洛伊木马”验证拦截器。
- **R1 学生蒸馏输出格式**：能够原生拦截被证明有效的推理轨迹，将验证流记录转化为严格挂载 `<think>` 标签的 `JSONL`，从而用以进行低成本小尺度的离线端侧模型微调。

---

## 技术栈

- **主要语言**: Python 3.10+
- **构建层/提示词框架**: DSPy
- **校验器**: Pydantic V2
- **形式化组件**: Z3 Solver, `VAL` (PDDL)
- **互联代理**: Model Context Protocol (MCP) Python SDK
- **自动化测试**: Pytest
- **打包部署**: Docker

---

## 本地前置要求

在本地启动前，你需要确保已安装一下基础组件：
- **Python 3.10+** (强烈推荐 3.11 稳定版)
- **Git**
- **Docker** (强烈推荐：用于无痛启动含有隔离层的 MCP server 和 C++ 编译插件)
- 至少拥有一个可被调用的 OpenAI、Anthropic 或是 Google 控制台 LLM API 密钥。

---

## 快速入门指南

### 1. 克隆代码仓库

```bash
git clone https://github.com/alexj11324/BDI_LLM_Formal_Ver.git
cd BDI_LLM_Formal_Ver
```

### 2. 安装内部依赖项

推荐始终为机器学习与编译项目创建隔离环境（使用 `venv`, `conda` 等）：

```bash
pip install -r requirements.txt
```

### 3. 配置本地环境变量

将预置的示例凭证文件拷贝为可工作模式：

```bash
cp .env.example .env
```

依据你要集成的提供商，在 `.env` 中补充以下密钥（必须配置至少一个）：

| 环境变量参数 | 用途描述 | 示例值 |
| -------- | ----------- | ------- |
| `OPENAI_API_KEY` | OpenAI 或者 OpenAI 标准接口映射端 (例如 CMU 网关) | `sk-xxxx...` |
| `ANTHROPIC_API_KEY` | Anthropic Claude 的 API 请求端 | `sk-ant-xxxx...` |
| `GOOGLE_API_KEY` | 谷歌 Gemini 原生服务的 API 请求端 | `AIza...` |
| `LLM_MODEL` | 告诉 DSPy 使用的实际调用大模型名称 | `gpt-5`, `gemini-2.0-flash` |
| `OPENAI_API_BASE` | 用于配置反向代理或内部自定义网关 | `https://ai-gateway...` |

### 4. 赋予 VAL 二进制编译系统运行权限 (如果需要进行本地测试)

如果你的操作系统是 macOS (ARM64环境)，请赋予本地代码库内自带的 VAL 程序执行权：
```bash
chmod +x planbench_data/planner_tools/VAL/validate
```
*(如果运行在包含特殊动态库的 Linux 或者 Windows 的非标环境，建议跳过此问题，直接按照下一节通过 Docker 构建)*

---

## 核心架构概览

### 目录功能划分

```text
BDI_LLM_Formal_Ver/
├── src/
│   ├── bdi_llm/             # 核心模块层
│   └── interfaces/          # MCP 服务网关与 CLI
├── scripts/                 # 按功能分类的评估/批量/重规划/论文脚本
│   ├── evaluation/          # PlanBench 评估脚本
│   ├── batch/               # 批量推理脚本
│   ├── replanning/          # 动态重规划脚本
│   └── paper/               # 论文图表生成脚本
├── tests/                   # 按类型分类的测试
│   ├── unit/                # 单元测试
│   ├── integration/         # 集成测试
│   └── smoke/               # 冒烟测试
├── docs/                    # 所有文档（C4架构、Conductor、归档等）
├── configs/                 # 配置文件与代码风格指南
└── planbench_data/          # 静态的大型基础 Blocksworld/Logistics PDDL 参照数据集
```

### PNSV 运行全生命周期

1. **初始调度**: Agent 输出抽象意向指令（例如“整理积木”）。由 DSPy 层发起请求转化为附有特定 Schema 格式的初期 JSON 意图动作。
2. **Pydantic 排异截留**: 系统会在解析第一环实施数据隔离转化，异常文本即刻被扔出。
3. **Core Engine 指派**: 数据将被成功具象为 `IntentionDAG` 对象传递给验证总线层（VerificationBus）。
4. **并线式多级验证**: 总线把有向无环图和基础世界状态传递至插件库。在这里它遭遇结构、PDDL与专有领域的反复拷打（并行化排错与拓扑分析）。
5. **修复或记录轨迹**: 
   - **错误修复**: 对触发隔离底线的 `EpistemicDeadlockError` 错误，进行堆栈回溯，提示大模型修复。
   - **轨迹蒸馏**: 对 0 Error 通关的，流向模型 R1 转换口并进入蒸馏数据集输出区进行落盘。

---

## 操作常用脚本矩阵

你可以使用提供的独立脚本来运行不同细分领域的框架控制体：

| 指令 | 描述 |
| ------- | ----------- |
| `python scripts/evaluation/run_planbench_full.py --domain blocksworld` | 触发所有积木世界数据集并自动开启自我对抗评估跑分 |
| `python scripts/evaluation/run_evaluation.py --mode demo` | 启用实时 CLI 会话模式。输入日常对话让验证器当场执行任务判断 |
| `python scripts/evaluation/run_verification_only.py` | 纯净的线下校验模式。用以断开网络连接专门检查给定的静态输出能否过审 |
| `python src/interfaces/mcp_server.py` | 把该工作流作为一个守护进程端口暴露出基于 MCP 路由的智能服务 |

*支持向部分跑分命令附加 `--execution_mode FULL_VERIFIED` 来触发完整的三层防伪机制，或是采用 `--execution_mode NAIVE` 开启纯野生大模型幻觉率对比测算。*

---

## 自动化测试验收网络

依赖于 Pytest 组件执行测试闭门。拥有超 90 个精细的单元覆盖。

### 本地无请求式组件运行

```bash
# 测试各类模型映射状态机防伪系统和节点验证器的逻辑正确性
pytest tests/
```

### 云端综合大模型模拟联调

```bash
# 执行涉及 DSPy 发包的核心逻辑
pytest tests/test_integration.py -q
```
*(出于自动熔断安全，任何未提供 .env 合法凭证链的机器将会显示自动标记全部联调集成跳过 `skip` 而并非崩溃报错)。*

---

## 线上环境部署 (基于 Docker 的 MCP 服务器)

如果是出于让其他 Agent 作为外外接脑调用的前提，强烈建议优先使用容器化发行版。这将无缝构建原本在部分系统极难编译成功的本地 `VAL` 库！

### 1. 编译基础环境层

```bash
docker build -t bdi-verifier .
```

### 2. 自包含运行

```bash
docker run -i --rm -e OPENAI_API_KEY=$OPENAI_API_KEY bdi-verifier
```

### (进阶) 集成至 Claude 桌面应用全自动服务

如果你使用的是官方的 Claude Desktop APP，可以将这段配置塞入在自己的 `claude_desktop_config.json` 目录使其成为内嵌 MCP 调用链落点。注意：请一定要记得把里面的大模型密钥自行补全：

```json
{
  "mcpServers": {
    "bdi-pnsv-verifier": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "OPENAI_API_KEY=修改为真实的串", "bdi-verifier"]
    }
  }
}
```

---

## 问题与疑难解答指南

### 1: 关于 VAL 环境缺少以及权限执行报错
**表现**: 后端抛出 `subprocess.CalledProcessError` 或执行无权限。
**修复**: Mac 跑 `chmod +x planbench_data/planner_tools/VAL/validate`。而遇到任何与 macOS 环境无关的架构崩溃，最明智的办法是不去单独编译，而是直接用 `docker build` 进行自动包含部署。

### 2: "Graph Validation Warning: Components disconnected"
**背景**: 此处代表发生了警告而非严重错误。第一层校验引擎（结构节点安全校验）检测到动作图中包含两个以上完全独立平行的子行动路径（可能两个步骤由于大模型认为全能被平行而并没有任何关系衔接）。
**响应流**: 这无毒无害，你完全不需要任何干预。第 2 与 3 层验证将会正常放行接受平行请求。

---

## 扩展深度开发文献

欲了解详尽设计逻辑和代码设计缘由请查阅我们的核心知识图谱体系：

- [**Conductor 设计档案**](docs/conductor/index.md): 工作习惯与设计初衷
- [**C4 级别系统全架构定义**](docs/c4/c4-context.md): 快速鸟瞰各大类容器关系链图
- [**终极技术白皮书卷宗**](docs/TECHNICAL_REFERENCE.md): 共十个章节总计上万字的极端详细工程师入职读物
- [**跑分成绩公告板**](docs/BENCHMARKS.md): 记录在纯自然状态和受系统拦截干预情况下的具体 AI 评测差额
- [**项目文档综合导航引擎 (Wiki)**](docs/wiki-catalogue.md): 全仓储文件的中心引导目录位
