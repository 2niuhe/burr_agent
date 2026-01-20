# 通用 Agent 架构与 Skill 集成路线图

## 1. 核心概念：Vibe Workflow 与 Skills
关键认知在于 **Vibe Workflow** 和 **Skills** 是互补的，而非互斥。

*   **Skills (定义 / 接口):**
    *   遵循 **Anthropic/Claude Skill 标准** (基于 Markdown)。
    *   定义 **"做什么 (What)"**。它充当“任务书”或用户界面。
    *   包含提示词 (Prompts)、元数据 (工具依赖) 和上下文。
    *   *特点：静态、声明式。*

*   **Vibe Workflow (运行时 / 引擎):**
    *   使用 **Burr** 状态机。
    *   定义 **"怎么做 (How)"**。它充当“大脑”和“执行引擎”。
    *   处理规划 (将复杂 Skill 拆解为步骤)、上下文管理 (子 Agent 隔离) 和鲁棒性控制。
    *   *特点：动态、操作性。*

**结论：** 不要废弃 Vibe Workflow。相反，应将其重构为执行标准 Skill 定义的 **运行时引擎 (Runtime Engine)**。

---

## 2. 架构对比

| 特性 | ReAct Loop (标准) | Task Queue (TODO) | Vibe Workflow (规划器) |
| :--- | :--- | :--- | :--- |
| **机制** | 思考 -> 行动 -> 观察 循环 | 动态列表 (添加/完成) | 规划 (列出步骤) -> 顺序执行 |
| **适用场景** | 简单、短查询 | 开放式探索 | 复杂工程、长程任务 |
| **上下文** | 单一共享上下文 (容易爆炸) | 难以隔离历史 | **子 Agent 隔离** (每步上下文干净) |
| **稳定性** | 低 (容易跑偏) | 低 (容易死循环) | **高** (结构刚性) |

**建议：** 采用 **双模式引擎 (Dual-Mode Engine)**：
1.  **ReAct 模式：** 针对简单 Skill/查询。
2.  **Vibe 规划器模式：** 针对复杂工程/代码 Skill (需要全局视角和上下文隔离)。

---

## 3. 实施路线图

### 第一阶段：Skill 标准化 (接口层)
*   建立遵循 Claude 规范的 `skills/` 目录结构。
*   示例结构：
    ```text
    skills/
    ├── calculator/
    │   └── SKILL.md
    └── data_analysis/
        ├── SKILL.md
        └── scripts/
    ```
*   实现 `SkillLoader` 以解析 Frontmatter 和 Markdown 提示词。

### 第二阶段：重构 Vibe (引擎层)
*   **解耦：** 移除 `config.yaml` 中硬编码的 `workflows`。
*   **注入：** 更新 `vibe_workflow.py` 以接受加载的 `Skill` 对象作为输入。
    *   Skill 的 `prompt` 成为 `current_goal`。
    *   Skill 的 `allowed-tools` 配置可用工具集。

### 第三阶段：能力升级
*   **重规划 (Replanning)：** 增强 Vibe Executor，当步骤卡住时触发“请求重规划”信号，而不是直接失败。
*   **路由 (Router)：** 实现意图分类器，将用户输入路由到正确的 `skills/{name}/SKILL.md`。

---

## 4. 总结
**"Skill 是卡带，Vibe 是游戏机。"**
通过采用 Claude Skill 格式标准化，Agent 获得了生态兼容性。通过保留 Vibe，Agent 保持了简单 ReAct 循环无法提供的、处理软件工程任务所需的鲁棒性。
