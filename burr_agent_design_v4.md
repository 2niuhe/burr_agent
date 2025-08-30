# Burr Agent 设计方案 (V4 - 分层历史)

本方案旨在设计一个基于 `burr` 框架的、健壮且可扩展的智能代理。其核心是 **Vibe Workflow**，一个用于解决复杂、多步骤任务的自主循环，并引入了**分层历史**和**执行模式**等高级概念，以确保系统的稳定性、安全性和良好的用户体验。

## 核心概念

1.  **Vibe Workflow**: 一个“规划-执行-反思”的循环，用于将用户的宏大目标分解为一系列子任务（`VibeStep`），并利用 LLM 和工具集逐一完成。
2.  **分层历史 (Hierarchical History)**: 本方案的架构核心。系统维护一个高级别的、与用户交互的**全局历史**，同时为每一个子任务（`VibeStep`）创建一个独立的、临时的**步骤历史**。这使得上下文管理更高效，用户交互更清晰。
3.  **执行模式 (Execution Modes)**:
    *   `interactive` (默认): 在执行任何工具调用（特别是高风险命令）前，必须征得用户同意。安全第一。
    *   `yolo` (You Only Live Once): 自动执行所有工具调用，无需用户确认。适用于可信的、自动化的场景。

---

## 1. State (状态) 定义

状态模型是整个系统的基石，我们设计了 `ApplicationState` 和 `VibeStep` 两个核心模型。

```python
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
from utils.llm import ToolCall # 假设 ToolCall 定义在此

class VibeStep(BaseModel):
    """定义一个拥有独立记忆的子任务 (Sub-Agent)"""
    step_id: int
    description: str
    
    # 关键：每个步骤拥有自己的、独立的执行历史
    chat_history: List[Dict[str, Any]] = Field(default_factory=list, description="此子任务的独立聊天/执行历史")
    
    # 用于生成最终摘要的字段
    tool_calls: Optional[List[Dict]] = Field(default=None)
    tool_results: Optional[List[Dict]] = Field(default=None)
    analysis: Optional[str] = Field(default=None, description="对子任务最终结果的分析")
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"

class ApplicationState(BaseModel):
    # 全局/用户级的历史记录
    chat_history: List[Dict[str, Any]] = Field(default_factory=list, description="与用户交互的高级历史记录")
    
    # 关键：用于追踪当前活动的子任务ID
    active_step_id: Optional[int] = None
    
    # 工作流与模式控制
    user_input: str = ""
    workflow_mode: Literal["chat", "ops", "vibe"] = "chat"
    execution_mode: Literal["interactive", "yolo"] = "interactive"
    current_goal: str = ""
    exit_chat: bool = False
    
    # 工具调用相关
    pending_tool_calls: List[ToolCall] = Field(default_factory=list)
    
    # Vibe Workflow 的整体计划
    vibe_plan: List[VibeStep] = Field(default_factory=list)
```

---

## 2. Action (动作) 职责

每个 Action 都有明确、单一的职责。

| Action               | 职责                                                                                                                               |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `prompt`             | 获取用户输入，并处理内部命令（如 `/mode yolo`）以切换执行模式。                                                                    |
| `router`             | 分析用户意图，决定进入 `chat` 还是 `vibe` 工作流。                                                                                 |
| `vibe_planner`       | **规划师**: 将用户的 `current_goal` 分解为一系列 `VibeStep`（自然语言描述的子任务），形成 `vibe_plan`。                               |
| `vibe_step_executor` | **子任务启动器**: 启动一个 `pending` 的子任务，为其初始化独立的 `chat_history`，并调用 LLM 生成第一个工具请求。                      |
| `execute_tools`      | **执行者**: 执行 `pending_tool_calls` 中的工具，并将结果记录到**当前活动步骤的 `chat_history`** 中。                                 |
| `vibe_result_analyzer` | **分析师**: 在子任务的 `chat_history` 上下文中，分析工具执行结果，判断子任务是否完成，并更新 `VibeStep` 的状态。                   |
| `step_summarizer`    | **沟通者/清理者**: 当一个子任务完成或失败后，生成一个简明摘要，将其追加到**全局 `chat_history`** 中，并清理该步骤的详细历史。 |
| `human_confirm`      | **安全阀**: 在 `interactive` 模式下，等待用户对工具执行的授权。                                                                    |
| `context_compressor` | **内存管理器**: 在调用 LLM 前检查历史记录长度，并在必要时进行压缩（此方案中，由于分层历史，需求被大大降低）。                 |

---

## 3. 工作流与图逻辑 (Workflow & Graph)

Vibe Workflow 的核心循环如下：

1.  **启动**: `prompt` -> `router` -> `vibe_planner` 创建计划。
2.  **进入循环**:
    1.  `vibe_step_executor` 启动一个子任务（`step N`），生成工具请求。
    2.  根据 `execution_mode` 决定路径：
        *   `interactive`: -> `human_confirm` -> `execute_tools`
        *   `yolo`: -> `execute_tools`
    3.  `execute_tools` 执行工具，结果存入 `step N` 的历史。
    4.  `vibe_result_analyzer` 分析 `step N` 的结果，更新其状态。
3.  **承上启下**:
    1.  `step_summarizer` 总结 `step N` 的执行过程，并汇报到全局历史。
    2.  如果 `vibe_plan` 中还有未完成的步骤，循环回到 `vibe_step_executor` 处理 `step N+1`。
    3.  如果所有步骤都完成，流程结束，返回 `prompt`。

---

## 4. 示例：诊断网站缓慢问题

这个例子清晰地展示了分层历史的工作方式。

### 全局历史 (`ApplicationState.chat_history`) - 用户视角

> **User**: 我的网站响应很慢，帮我看看怎么回事。
>
> **Assistant**: 好的，我来诊断问题。我已经制定了计划：
> 1.  检查服务器的CPU和内存负载。
> 2.  分析Web服务器的访问日志和错误日志。
>
> *(...内部开始执行 Step 1...)*
>
> **Assistant**: ✅ **Step 1 完成**: 我通过 `top` 命令检查了服务器负载，发现CPU使用率高达98%。这很可能是问题所在。接下来我将检查日志以定位具体进程。
>
> *(...内部开始执行 Step 2...)*
>
> **Assistant**: ❌ **Step 2 失败**: 我尝试读取 `/var/log/nginx/error.log` 时遇到“权限拒绝”错误。我将尝试使用 `sudo` 来修正这一步。

### 步骤历史 (`VibeStep[0].chat_history`) - 内部视角 (Step 1)

这是一个临时的、详细的日志，在步骤完成后被总结并清理。

```json
[
  {
    "role": "system",
    "content": "Your sub-task is: '检查服务器的CPU和内存负载'. Use your tools to accomplish this."
  },
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [{
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "run_shell_command",
        "arguments": "{"command": "top -bn1 | head -n 5"}"
      }
    }]
  },
  {
    "role": "tool",
    "tool_call_id": "call_abc123",
    "name": "run_shell_command",
    "content": "top - ... Tasks: 234 total,   1 running, ... %Cpu(s): 98.0 us,  1.5 sy, ..."
  },
  {
    "role": "assistant",
    "content": "The tool output shows a CPU usage of 98.0% user space, which is extremely high. The sub-task is complete. The key finding is high CPU load."
  }
]
```

## 结论

该 V4 方案通过引入**分层历史**，将一个复杂的代理任务分解为一系列拥有独立上下文的、简单的子任务。这种设计不仅极大地简化了上下文管理和压缩，还通过在主流程中只保留高级摘要，为最终用户提供了清晰、简洁的交互体验，是构建高级、健壮 `burr` 应用的理想架构。
