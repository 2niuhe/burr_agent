# Vibe Workflow NiceGUI 应用设计方案

## 1. 总体设计理念

本方案旨在创建一个直观、模块化且高度互动的用户界面，将`vibe_workflow.py`中强大的后端逻辑以用户友好的方式呈现。我们将遵循以下设计原则：

*   **清晰分离**：将“工作流管理”和“对话执行”两大核心功能分离到不同的页面/视图中，使用户能专注于当前任务。
*   **状态可见**：实时、清晰地展示Agent的状态，包括当前的计划（Plan）、每一步骤（Step）的进展、以及对话历史，建立用户信任感。
*   **交互核心**：将人工确认（Human-in-the-loop）作为UI交互的核心部分，而非简单的命令行`y/n`，提供更丰富的上下文和更明确的操作选项。
*   **用户赋能**：提供强大的工作流自定义功能，让高级用户可以构建和微调自己的Agent行为模式。

## 2. 页面/视图设计

应用程序将主要包含两个核心页面：**工作流管理页 (Workflow Management Page)** 和 **对话与执行页 (Chat & Execution Page)**。

---

### 2.1. 工作流管理页 (Workflow Management Page)

这是应用的入口和控制中心。

**A. 目的**
*   展示所有可用的工作流模板。
*   允许用户创建新的工作流或编辑/删除现有工作流。
*   提供一个界面来定义工作流的元数据和步骤细节。

**B. 布局**
采用经典的两栏布局：
*   **左栏**：工作流列表。
*   **右栏**：选中工作流的编辑器。

**C. 组件详解**

*   **左栏：工作流列表 (Workflow List)**
    *   一个`ui.list`或`ui.table`，展示所有工作流的名称和简短描述。
    *   列表上方有一个醒目的 **“+ 创建新工作流”** 按钮。
    *   列表中每一项旁边都有“运行”、“编辑”、“删除”图标按钮。
        *   **运行 (Run)**：导航到“对话与执行页”，并加载该工作流的初始目标。
        *   **编辑 (Edit)**：在右栏加载该工作流进行编辑。
        *   **删除 (Delete)**：弹出确认对话框后删除。

*   **右栏：工作流编辑器 (Workflow Editor)**
    *   当创建或编辑一个工作流时，此区域变为活动状态。
    *   **工作流名称 (Workflow Name)**：一个`ui.input`用于设置工作流的名称（例如：“代码审查助手”）。
    *   **工作流描述 (Workflow Description)**：一个`ui.textarea`用于详细描述此工作流的用途。
    *   **初始目标 (Initial Goal)**：一个`ui.input`，定义当“运行”此工作流时，自动发送给Agent的第一个指令。这是`vibe_planner`的输入。
    *   **步骤自定义区域 (Steps Customization)**：这是自定义的核心。
        *   使用一个动态列表，允许用户添加、删除和重新排序步骤。
        *   每一个步骤都是一个`ui.card`，包含：
            *   **步骤编号**: 自动生成。
            *   **目标 (Goal)**: 一个`ui.input`，对应`VibeStep.description`。这是对该步骤任务的自然语言描述。
            *   **提示 (Hint)**: 一个`ui.textarea`（可选项），用于向执行该步骤的LLM提供额外的上下文或指令，例如：“在这一步，优先使用`read_file`工具”、“请以JSON格式输出结果”。这可以作为System Message的一部分。
    *   **保存按钮**: 一个`ui.button`，用于保存对工作流的所有更改。

---

### 2.2. 对话与执行页 (Chat & Execution Page)

这是应用的核心交互界面，用户在这里与Agent对话并观察其执行任务。

**A. 目的**
*   提供一个类似聊天机器人的界面进行人机交互。
*   实时可视化展示Vibe Plan的生成和执行过程。
*   在需要时，向用户请求工具执行的授权。
*   展示所有来自Agent和工具的输出。

**B. 布局**
建议采用三栏布局，以最大化信息密度和清晰度：
*   **左栏 (固定)**：Vibe计划与状态 (Vibe Plan & Status)。
*   **中栏 (主要)**：对话历史记录 (Chat History)。
*   **右栏 (可选/可折叠)**：上下文与控制 (Context & Controls)。

**C. 组件详解**

*   **左栏：Vibe计划与状态 (Vibe Plan & Status)**
    *   **当前总目标 (Current Goal)**：在顶部显眼位置展示`ApplicationState.current_goal`。
    *   **步骤进度条 (Steps Stepper)**：使用`ui.stepper`来完美映射`ApplicationState.vibe_plan`。
        *   每个`VibeStep`都是一个`ui.step`。
        *   **步骤标题**: `f"步骤 {step.step_id + 1}: {step.description}"`。
        *   **状态指示**: 通过步骤的图标和颜色来指示`step.status`：
            *   `pending`: 灰色图标 (e.g., `pending`)
            *   `in_progress`: 蓝色旋转图标 (e.g., `running`)
            *   `completed`: 绿色勾选图标 (e.g., `done`)
            *   `failed`: 红色错误图标 (e.g., `error`)
        *   当一个步骤完成后，可以在`ui.stepper`中展示其`analysis`（结果分析摘要）。

*   **中栏：对话历史记录 (Chat History)**
    *   使用`ui.chat_message`来构建对话流。
    *   **用户输入**: 用户在页面底部的`ui.input`中输入，点击发送后，作为`role: user`的消息显示。
    *   **Agent思考/回复**: Agent的流式输出（例如`vibe_planner`和`vibe_step_executor`的打印信息）作为`role: assistant`的消息显示。
    *   **工具调用确认 (Human Confirmation)**：这是最重要的交互改造。
        *   当`ApplicationState.tool_execution_needed`为`True`且模式为`interactive`时，**不应再等待命令行输入**。
        *   取而代之，在聊天流中插入一个特殊的`ui.card`。
        *   此卡片内清晰地列出所有`pending_tool_calls`：
            *   **标题**: "需要您的授权来执行以下工具："
            *   **列表**: `f"- {tool_call.function.name}({tool_call.function.arguments})"`
            *   **操作按钮**:
                *   一个绿色的 **“批准 (Approve)”** 按钮。点击后，在后端将`ApplicationState.tool_execution_allowed`设为`True`，并继续执行流程。
                *   一个红色的 **“拒绝 (Deny)”** 按钮。点击后，设为`False`，并终止当前步骤。
    *   **工具执行结果**: `execute_tools`中每个工具的执行结果，都应作为一条新的`role: tool`或`role: assistant`消息显示在聊天中。

*   **右栏：上下文与控制 (Context & Controls)**
    *   **执行模式切换**: 使用`ui.switch`或`ui.radio`来切换`execution_mode` ("interactive" vs "yolo")。
    *   **可用工具列表**: 显示从MCP获取的`mcp_tools`列表，让用户了解Agent的能力。
    *   **状态变量监视器 (可选)**: 对于调试，可以显示`ApplicationState`中关键字段的当前值。

## 3. 与 `vibe_workflow.py` 的逻辑映射

*   **`ApplicationState`**: 将成为NiceGUI应用的中央状态存储。可以使用一个响应式的类或字典来绑定UI组件和后端状态。
*   **`prompt` action**: 由“对话页”底部的输入框和发送按钮触发。
*   **`router` action**: 在用户提交输入后自动触发，其结果（`workflow_mode`的改变）会启动`vibe_planner`。
*   **`vibe_planner` action**: 触发后，左栏的Stepper会从空变为填充了计划步骤，中栏的对话框会显示“正在为您规划...”。
*   **`vibe_step_executor` action**: 触发时，左栏对应步骤的状态会变为“in_progress”，中栏会显示“正在执行步骤...”。
*   **`human_confirm` action**: 这个action的逻辑将被UI接管。Burr流程会在此暂停，等待UI按钮的点击事件来更新`tool_execution_allowed`状态，然后继续。
*   **`execute_tools` action**: 执行时，中栏会实时流式显示每个工具的调用结果。完成后，左栏对应步骤的状态更新为“completed”或“failed”。
*   **流式输出 (`yield {"answer": ...}`):** 所有`yield`出来的字典，其`answer`字段的内容都应该被捕获并实时推送到中栏的聊天界面中。

## 4. 实施建议与后续步骤

1.  **项目结构**:
    *   创建一个新的`ui.py`文件来存放NiceGUI应用代码。
    *   将`vibe_workflow.py`中的Burr应用构建逻辑（`application()`函数）和状态类（`ApplicationState`, `VibeStep`）提取到一个共享的模块中，以便UI和后端逻辑都能导入。
    *   主运行逻辑需要调整，不再是`while True`循环，而是由NiceGUI的事件循环驱动。

2.  **状态管理**:
    *   在NiceGUI应用中创建一个全局或会话级别的状态对象，其结构与`ApplicationState`匹配。
    *   使用`ui.timer`或NiceGUI的异步任务能力来运行Burr的`app.astream_result()`，并将返回的状态更新同步到UI状态对象。UI组件应绑定到这个状态对象上，以实现自动刷新。

3.  **开发路线图**:
    *   **第一步：构建静态布局**。先用NiceGUI搭建出上述所有页面的静态布局，确保外观符合设计。
    *   **第二步：集成对话功能**。实现基本的聊天输入和历史显示，暂时不连接Agent。
    *   **第三步：连接Burr后端**。将Burr应用实例与UI连接，实现用户输入 -> Agent处理 -> 结果返回UI的完整流程。
    *   **第四步：实现核心交互**。重点开发“工具调用确认”卡片和“步骤进度条”的动态更新。
    *   **第五步：实现工作流管理**。开发管理页面，实现工作流的CRUD（创建、读取、更新、删除）功能，并将其存储在文件或简单的数据库中。