---
description: 阅读 /init 和 /chat-summarize 工作流的所有交付物，构建项目全貌理解
---

# Project Overview（全局上下文构建）

基于目录扫描方式自动发现并阅读 `/init` 和 `/chat-summarize` 工作流的交付物，不依赖硬编码文件名。

---

## Phase 1: 扫描并阅读 /init 交付物

按以下顺序扫描项目根目录，找到并阅读对应的交付物。如果某个文件不存在，标注 `[NOT FOUND]` 并继续。

### 1.1 Wiki 文档目录
- 扫描: 项目根目录下 `wiki-catalogue.*` 或 `docs/wiki-catalogue.*`（优先 `.md`，回退 `.json`）
- 如找到则阅读全文：了解项目文档层次结构

### 1.2 C4 架构文档
- 扫描: `docs/c4/` 目录是否存在
- 如存在则按顺序阅读：
  1. `c4-context.md` — 系统上下文（最高层）
  2. `c4-container.md` — 容器层
  3. `c4-component.md` — 组件索引
  4. 按需阅读 `c4-code-*.md` 和 `c4-component-*.md`（深度文档）
  5. 浏览 `c4-components-detail.md`（如存在）

### 1.3 综合技术手册
- 扫描: `docs/` 目录下匹配 `*TECHNICAL*` 或 `*technical*` 的 `.md` 文件
- 预期文件名: `docs/TECHNICAL_REFERENCE.md`（由 `docs-architect` skill 生成）
- 如找到则阅读全文：包含 Executive Summary、Architecture、Design Decisions 等章节

### 1.4 Conductor 项目配置
- 扫描: `docs/conductor/` 目录是否存在
- 如存在则按顺序阅读：
  1. `docs/conductor/index.md` — 导航中心
  2. `docs/conductor/product.md` — 产品定义
  3. `docs/conductor/product-guidelines.md` — 产品指南
  4. `docs/conductor/tech-stack.md` — 技术栈
  5. `docs/conductor/workflow.md` — 工作流定义
  6. `docs/conductor/tracks.md` — Track 注册表
  7. 浏览 `configs/code_styleguides/` 下的代码风格指南

### 1.5 项目 README
- 扫描: 项目根目录下 `README.md`
- 如存在则阅读全文

### 1.6 其他技术文档
- 扫描: `docs/` 目录下所有 `.md` 文件
- 排除已在 1.3 中阅读的文件
- 按需阅读：
  - `docs/USER_GUIDE.md`
  - `docs/BENCHMARKS.md`
  - 其他找到的 `.md` 文件

---

## Phase 2: 扫描并阅读 /chat-summarize 交付物

### 2.1 扫描会话文档目录
- 扫描: `docs/sessions/` 目录是否存在
- 如不存在则标注 `[SKIPPED] /chat-summarize 交付物不存在` 并结束

### 2.2 阅读最新一组会话文档
- 列出 `docs/sessions/` 下所有 `.md` 文件
- 按日期前缀分组，取最新一组（同一日期的文件）
- 按以下优先级阅读：
  1. `*-compressed-summary.md` — 压缩摘要（最重要）
  2. `*-entity-memory-store.md` — 实体记忆存储
  3. `*-context-routing-manifest.md` — 上下文路由清单
  4. 其他同日期的 `.md` 文件

---

## Phase 3: 综合输出

阅读完所有交付物后，生成一份简要的项目全貌总结，包括：

1. **项目概述** — 一句话描述项目做什么
2. **技术栈** — 核心语言、框架、基础设施
3. **架构概要** — 关键组件和数据流
4. **当前进展** — 从会话文档中提取的最新状态
5. **待办事项** — 已知的阻塞点和下一步

---

## 扫描策略说明

> **为什么用扫描而非硬编码文件名？**
>
> `/init` 工作流调用的部分 skill（如 `docs-architect`、`wiki-architect`）在 SKILL.md 中
> 未定义具体输出文件名。虽然 `/init` 工作流已添加显式文件名约束（`wiki-catalogue.md`、
> `docs/TECHNICAL_REFERENCE.md`），但为防止 skill 执行时选择不同文件名，本工作流采用
> glob 模式扫描作为兜底策略，确保无论文件名如何变化都能找到交付物。
