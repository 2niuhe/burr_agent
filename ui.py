#!/usr/bin/env python3
"""
Vibe Workflow NiceGUI 应用实现
参照 vibe_workflow_ui_design.md 的设计方案
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from nicegui import app, ui
from pydantic import BaseModel

# 导入现有的模块
try:
    from agent.app import build_application
    from agent.state import ApplicationState, VibeStep
except ImportError:
    # 如果agent模块不可用，使用vibe_workflow中的定义
    from vibe_workflow import (
        ApplicationState,
    )
    from vibe_workflow import (
        application as build_application,
    )

from typing import Tuple

from burr.core import action
from burr.core.action import streaming_action

from logger import logger
from utils import llm
from utils.llm import ToolCall
from utils.mcp import StreamableMCPClient, connect_to_mcp


# 工作流模板数据模型
class WorkflowTemplate(BaseModel):
    """工作流模板定义"""

    name: str
    description: str
    initial_goal: str
    steps: List[Dict[str, str]] = []  # [{"goal": str, "hint": str}, ...]


# 全局状态管理
class UIState:
    """UI 全局状态管理"""

    def __init__(self):
        self.burr_app = None
        self.app_state: ApplicationState = ApplicationState()
        self.mcp_client: Optional[StreamableMCPClient] = None
        self.mcp_tools: List[Dict] = []
        self.workflow_templates: List[WorkflowTemplate] = []
        self.current_workflow: Optional[WorkflowTemplate] = None
        self.active_workflow_index: Optional[int] = None

        # UI 组件引用
        self.stepper = None
        self.chat_container = None
        self.tool_confirmation_card = None
        self.execution_mode_switch = None
        self.current_goal_display = None

        # 加载工作流模板
        self.load_workflows()

    def load_workflows(self):
        """从本地文件加载工作流模板"""
        workflows_file = Path("workflows.json")
        if workflows_file.exists():
            try:
                with open(workflows_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self.workflow_templates = [WorkflowTemplate(**wf) for wf in data]
            except Exception as e:
                logger.error(f"加载工作流模板失败: {e}")
                self.workflow_templates = []
        else:
            # 创建默认的工作流模板
            self.workflow_templates = [
                WorkflowTemplate(
                    name="代码审查助手",
                    description="帮助审查代码，检查潜在问题并提供改进建议",
                    initial_goal="请审查我的代码并提供改进建议",
                    steps=[
                        {
                            "goal": "读取和分析代码文件",
                            "hint": "使用 read_file 工具，关注代码结构和逻辑",
                        },
                        {
                            "goal": "检查代码质量和潜在问题",
                            "hint": "查找常见的编程错误、性能问题等",
                        },
                        {
                            "goal": "提供具体的改进建议",
                            "hint": "给出可操作的建议，包括具体的代码修改",
                        },
                    ],
                ),
                WorkflowTemplate(
                    name="文档生成器",
                    description="自动生成项目文档",
                    initial_goal="为我的项目生成完整的文档",
                    steps=[
                        {
                            "goal": "扫描项目结构",
                            "hint": "使用 list_dir 和相关工具了解项目组织",
                        },
                        {
                            "goal": "分析主要代码文件",
                            "hint": "重点分析核心模块和API接口",
                        },
                        {
                            "goal": "生成结构化文档",
                            "hint": "创建 README.md 和 API 文档",
                        },
                    ],
                ),
            ]
            self.save_workflows()

    def save_workflows(self):
        """保存工作流模板到本地文件"""
        try:
            workflows_file = Path("workflows.json")
            data = [wf.dict() for wf in self.workflow_templates]
            with open(workflows_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存工作流模板失败: {e}")


# 全局 UI 状态实例
# UI专用的prompt action，不等待命令行输入
@action.pydantic(reads=[], writes=["user_input", "exit_chat", "execution_mode"])
def ui_prompt(state: ApplicationState) -> ApplicationState:
    """UI版本的prompt，不等待命令行输入，而是使用已设置的user_input"""
    logger.info(f"ui_prompt called with user_input: {state.user_input}")
    # 在UI模式下，user_input已经由UI设置好了，我们只需要处理它
    # 不需要调用input()等待用户输入

    if state.user_input.lower() in ["exit", "quit"]:
        state.exit_chat = True
        return state

    # 检查是否是模式切换命令
    import re

    mode_match = re.match(r"/mode\s+(interactive|yolo)", state.user_input.lower())
    if mode_match:
        new_mode = mode_match.group(1)
        state.execution_mode = new_mode
        logger.info(f"执行模式切换到: {new_mode}")
        # 清空user_input，这样就不会继续处理这个命令
        state.user_input = ""

    return state


# UI专用的human_confirm action，用于替换命令行确认
@action.pydantic(
    reads=["pending_tool_calls", "active_step_id", "vibe_plan"],
    writes=["tool_execution_allowed", "vibe_plan"],
)
def ui_human_confirm(state: ApplicationState) -> ApplicationState:
    """UI版本的人工确认，不阻塞等待，而是设置状态等待UI交互"""
    # 在UI模式下，我们不在这里等待输入，而是返回状态让UI处理
    # UI会通过show_tool_confirmation()显示确认界面
    # 用户点击按钮后会调用approve_tools()或deny_tools()来更新状态

    # 确保有待确认的工具调用
    if not state.pending_tool_calls:
        state.tool_execution_allowed = False
        return state

    # 在UI模式下，我们暂停并等待UI交互
    # 不设置tool_execution_allowed，让UI按钮来设置
    logger.info(f"等待UI确认执行 {len(state.pending_tool_calls)} 个工具调用")
    return state


# 全局 UI 状态实例
def build_ui_application():
    """构建UI专用的Burr应用，使用UI版本的human_confirm"""
    try:
        # 尝试使用agent模块的构建方式，但替换human_confirm
        from burr.core import ApplicationBuilder, when
        from burr.integrations.pydantic import PydanticTypingSystem

        # 导入所有需要的actions
        try:
            from agent.actions import (
                execute_tools,
                exit_chat,
                router,
                step_summarizer,
                vibe_planner,
                vibe_result_analyzer,
                vibe_step_executor,
            )

            # 使用UI版本的actions
            prompt = ui_prompt
            chat_response = ui_chat_response  # 使用UI版本，不打印
            human_confirm = ui_human_confirm

            return (
                ApplicationBuilder()
                .with_typing(PydanticTypingSystem(ApplicationState))
                .with_state(ApplicationState())
                .with_actions(
                    prompt=prompt,
                    router=router,
                    chat_response=chat_response,
                    vibe_planner=vibe_planner,
                    vibe_step_executor=vibe_step_executor,
                    human_confirm=human_confirm,  # 使用UI版本
                    execute_tools=execute_tools,
                    vibe_result_analyzer=vibe_result_analyzer,
                    step_summarizer=step_summarizer,
                    exit_chat=exit_chat,
                )
                .with_transitions(
                    ("prompt", "router"),
                    ("prompt", "exit_chat", when(exit_chat=True)),
                    ("router", "chat_response", when(route_target="chat_response")),
                    (
                        "chat_response",
                        "human_confirm",
                        when(tool_execution_needed=True),
                    ),
                    ("chat_response", "prompt", when(tool_execution_needed=False)),
                    (
                        "human_confirm",
                        "execute_tools",
                        when(tool_execution_allowed=True),
                    ),
                    ("human_confirm", "prompt", when(tool_execution_allowed=False)),
                    ("router", "vibe_planner", when(route_target="vibe_planner")),
                    ("vibe_planner", "vibe_step_executor"),
                    (
                        "vibe_step_executor",
                        "human_confirm",
                        when(tool_execution_needed=True),
                    ),
                    (
                        "vibe_step_executor",
                        "vibe_result_analyzer",
                        when(tool_execution_needed=False),
                    ),
                    (
                        "human_confirm",
                        "execute_tools",
                        when(tool_execution_allowed=True),
                    ),
                    (
                        "human_confirm",
                        "vibe_result_analyzer",
                        when(tool_execution_allowed=False),
                    ),
                    ("execute_tools", "vibe_result_analyzer"),
                    ("vibe_result_analyzer", "step_summarizer"),
                    ("step_summarizer", "prompt", when(active_step_id=None)),
                    ("step_summarizer", "vibe_step_executor"),
                )
                .with_entrypoint("prompt")
                .with_tracker("local", project="burr_agent_ui")
                .build()
            )
        except ImportError:
            # 如果agent模块不可用，使用vibe_workflow的方式
            from vibe_workflow import (
                execute_tools,
                exit_chat,
                router,
                vibe_planner,
                vibe_step_executor,
            )

            # 使用UI版本的prompt
            prompt = ui_prompt

            return (
                ApplicationBuilder()
                .with_typing(PydanticTypingSystem(ApplicationState))
                .with_state(ApplicationState())
                .with_actions(
                    prompt=prompt,
                    router=router,
                    exit_chat=exit_chat,
                    vibe_planner=vibe_planner,
                    vibe_step_executor=vibe_step_executor,
                    human_confirm=ui_human_confirm,  # 使用UI版本
                    execute_tools=execute_tools,
                )
                .with_transitions(
                    ("prompt", "router", when(exit_chat=False)),
                    ("prompt", "exit_chat", when(exit_chat=True)),
                    ("router", "vibe_planner", when(workflow_mode="vibe")),
                    ("router", "prompt", when(workflow_mode="chat")),
                    ("vibe_planner", "vibe_step_executor"),
                    (
                        "vibe_step_executor",
                        "human_confirm",
                        when(tool_execution_needed=True, execution_mode="interactive"),
                    ),
                    (
                        "vibe_step_executor",
                        "execute_tools",
                        when(tool_execution_needed=True, execution_mode="yolo"),
                    ),
                    ("vibe_step_executor", "prompt", when(tool_execution_needed=False)),
                    (
                        "human_confirm",
                        "execute_tools",
                        when(tool_execution_allowed=True),
                    ),
                    ("human_confirm", "prompt", when(tool_execution_allowed=False)),
                    ("execute_tools", "vibe_step_executor"),
                )
                .with_entrypoint("prompt")
                .with_tracker("local", project="burr_agent_ui")
                .build()
            )
    except Exception as e:
        logger.error(f"构建UI应用失败: {e}")
        # 回退到默认应用
        return build_application()


# UI专用的chat_response action，不打印到命令行


@streaming_action.pydantic(
    reads=["user_input", "chat_history"],
    writes=["chat_history", "pending_tool_calls", "tool_execution_needed"],
    state_input_type=ApplicationState,
    state_output_type=ApplicationState,
    stream_type=dict,
)
async def ui_chat_response(
    state: ApplicationState,
) -> Tuple[dict, Optional[ApplicationState]]:
    """UI版本的chat_response，不打印到命令行"""
    # 添加用户消息到历史
    state.chat_history.append({"role": "user", "content": state.user_input})

    # 获取工具
    tools = ui_state.mcp_tools if ui_state.mcp_tools else []

    llm_stream = await llm.ask(state.chat_history, stream=True, tools=tools)

    # 不打印 "AI: "，只处理流式输出
    buffer: List[str] = []
    tool_calls_detected = False
    detected_tool_calls: List[ToolCall] = []

    async for chunk in llm_stream:
        if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
            tool_calls_detected = True
            detected_tool_calls.extend(chunk.get("tool_calls", []))
        elif isinstance(chunk, str):
            buffer.append(chunk)
            # 不打印到命令行，只yield给UI
            yield {"answer": chunk}, None

    final = "".join(buffer)
    state.chat_history.append({"role": "assistant", "content": final})

    if tool_calls_detected and detected_tool_calls:
        state.pending_tool_calls = detected_tool_calls
        state.tool_execution_needed = True
        yield {}, state
    else:
        state.tool_execution_needed = False
        yield {}, state


ui_state = UIState()


@ui.page("/")
def workflow_management_page():
    """工作流管理页面"""
    with ui.column().classes("w-full h-screen"):
        # 页面标题和导航
        with ui.row().classes("w-full items-center justify-between p-4 bg-blue-100"):
            ui.label("Vibe Workflow 管理").classes("text-2xl font-bold")
            ui.button("进入对话模式", on_click=lambda: ui.navigate.to("/chat")).classes(
                "bg-green-500 text-white"
            )

        # 主内容区域 - 两栏布局
        with ui.row().classes("w-full flex-1"):
            # 左栏：工作流列表
            with ui.column().classes("w-1/3 p-4 border-r"):
                with ui.row().classes("w-full items-center justify-between mb-4"):
                    ui.label("工作流列表").classes("text-xl font-semibold")
                    ui.button("+ 创建新工作流", on_click=create_new_workflow).classes(
                        "bg-blue-500 text-white"
                    )

                # 工作流列表容器
                workflow_list_container = ui.column().classes("w-full space-y-2")
                update_workflow_list(workflow_list_container)

            # 右栏：工作流编辑器
            with ui.column().classes("w-2/3 p-4"):
                workflow_editor_container = ui.column().classes("w-full")
                ui_state.workflow_editor = workflow_editor_container

                # 初始状态显示
                with workflow_editor_container:
                    ui.label("选择一个工作流进行编辑，或创建新的工作流").classes(
                        "text-gray-500 text-center mt-20"
                    )


def update_workflow_list(container):
    """更新工作流列表显示"""
    container.clear()

    for i, workflow in enumerate(ui_state.workflow_templates):
        with container:
            with ui.card().classes("w-full p-3"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("flex-1"):
                        ui.label(workflow.name).classes("font-semibold")
                        ui.label(workflow.description).classes("text-sm text-gray-600")

                    with ui.row().classes("space-x-2"):
                        ui.button(
                            "运行", on_click=lambda idx=i: run_workflow(idx)
                        ).classes("bg-green-500 text-white text-xs")
                        ui.button(
                            "编辑", on_click=lambda idx=i: edit_workflow(idx)
                        ).classes("bg-blue-500 text-white text-xs")
                        ui.button(
                            "删除", on_click=lambda idx=i: delete_workflow(idx)
                        ).classes("bg-red-500 text-white text-xs")


def create_new_workflow():
    """创建新工作流"""
    new_workflow = WorkflowTemplate(
        name="新工作流",
        description="描述你的工作流用途",
        initial_goal="设定初始目标",
        steps=[],
    )
    ui_state.workflow_templates.append(new_workflow)
    ui_state.active_workflow_index = len(ui_state.workflow_templates) - 1
    edit_workflow(ui_state.active_workflow_index)


def edit_workflow(index: int):
    """编辑工作流"""
    ui_state.active_workflow_index = index
    workflow = ui_state.workflow_templates[index]

    # 清空编辑器并重新构建
    ui_state.workflow_editor.clear()

    with ui_state.workflow_editor:
        ui.label("编辑工作流").classes("text-xl font-semibold mb-4")

        # 基本信息
        with ui.column().classes("w-full space-y-4"):
            name_input = ui.input("工作流名称", value=workflow.name).classes("w-full")
            desc_input = ui.textarea("工作流描述", value=workflow.description).classes(
                "w-full"
            )
            goal_input = ui.input("初始目标", value=workflow.initial_goal).classes("w-full")

            # 步骤编辑区域
            ui.label("步骤配置").classes("text-lg font-semibold mt-6")
            steps_container = ui.column().classes("w-full space-y-3")

            def update_steps_display():
                steps_container.clear()
                for i, step in enumerate(workflow.steps):
                    with steps_container:
                        with ui.card().classes("w-full p-3"):
                            with ui.row().classes(
                                "w-full items-center justify-between mb-2"
                            ):
                                ui.label(f"步骤 {i + 1}").classes("font-semibold")
                                ui.button(
                                    "删除", on_click=lambda idx=i: remove_step(idx)
                                ).classes("bg-red-500 text-white text-xs")

                            step_goal = ui.input(
                                "目标", value=step.get("goal", "")
                            ).classes("w-full mb-2")
                            step_hint = ui.textarea(
                                "提示 (可选)", value=step.get("hint", "")
                            ).classes("w-full")

                            # 绑定更新事件
                            step_goal.on(
                                "blur",
                                lambda e, idx=i: update_step_goal(idx, e.sender.value),
                            )
                            step_hint.on(
                                "blur",
                                lambda e, idx=i: update_step_hint(idx, e.sender.value),
                            )

            def update_step_goal(idx, value):
                if idx < len(workflow.steps):
                    workflow.steps[idx]["goal"] = value

            def update_step_hint(idx, value):
                if idx < len(workflow.steps):
                    workflow.steps[idx]["hint"] = value

            def remove_step(idx):
                if idx < len(workflow.steps):
                    workflow.steps.pop(idx)
                    update_steps_display()

            def add_step():
                workflow.steps.append({"goal": "", "hint": ""})
                update_steps_display()

            update_steps_display()

            # 添加步骤按钮
            ui.button("+ 添加步骤", on_click=add_step).classes(
                "bg-blue-500 text-white mt-2"
            )

            # 保存按钮
            def save_workflow():
                workflow.name = name_input.value
                workflow.description = desc_input.value
                workflow.initial_goal = goal_input.value
                ui_state.save_workflows()
                ui.notify("工作流已保存", type="positive")
                # 重新加载工作流列表
                ui.navigate.reload()

            ui.button("保存工作流", on_click=save_workflow).classes(
                "bg-green-500 text-white mt-4"
            )


def delete_workflow(index: int):
    """删除工作流"""
    if 0 <= index < len(ui_state.workflow_templates):
        workflow_name = ui_state.workflow_templates[index].name

        # 确认对话框
        with ui.dialog() as dialog:
            with ui.card():
                ui.label(f'确定要删除工作流 "{workflow_name}" 吗？')
                with ui.row().classes("justify-end mt-4"):
                    ui.button("取消", on_click=dialog.close).classes("mr-2")

                    def confirm_delete():
                        ui_state.workflow_templates.pop(index)
                        ui_state.save_workflows()
                        dialog.close()
                        ui.navigate.reload()

                    ui.button("删除", on_click=confirm_delete).classes(
                        "bg-red-500 text-white"
                    )

        dialog.open()


def run_workflow(index: int):
    """运行工作流"""
    if 0 <= index < len(ui_state.workflow_templates):
        ui_state.current_workflow = ui_state.workflow_templates[index]
        ui.navigate.to("/chat")


@ui.page("/chat")
def chat_execution_page():
    """对话与执行页面"""
    with ui.column().classes("w-full h-screen"):
        # 页面标题和导航
        with ui.row().classes("w-full items-center justify-between p-4 bg-green-100"):
            ui.label("Vibe Workflow 对话").classes("text-2xl font-bold")
            ui.button("返回管理", on_click=lambda: ui.navigate.to("/")).classes(
                "bg-blue-500 text-white"
            )

        # 主内容区域 - 三栏布局
        with ui.row().classes("w-full flex-1"):
            # 左栏：Vibe计划与状态
            with ui.column().classes("w-1/5 p-4 border-r bg-gray-50"):
                ui.label("Vibe 计划与状态").classes("text-lg font-semibold mb-4")

                # 当前目标显示
                ui_state.current_goal_display = ui.label("").classes(
                    "text-sm text-gray-600 mb-4 p-2 bg-white rounded"
                )

                # 步骤进度条
                ui_state.stepper = ui.stepper().classes("w-full")
                update_stepper_display()

            # 中栏：对话历史记录
            with ui.column().classes("w-3/5 p-4"):
                ui.label("对话历史").classes("text-lg font-semibold mb-4")

                # 聊天容器
                ui_state.chat_container = ui.column().classes(
                    "w-full flex-1 overflow-y-auto border rounded p-4 bg-white"
                )

                # 输入区域
                with ui.row().classes("w-full mt-4"):
                    chat_input = ui.input("输入您的请求...").classes("flex-1")
                    send_button = ui.button(
                        "发送",
                        on_click=lambda: send_message(chat_input.value, chat_input),
                    ).classes("bg-blue-500 text-white")

                # 绑定回车事件
                chat_input.on(
                    "keydown.enter", lambda: send_message(chat_input.value, chat_input)
                )

            # 右栏：上下文与控制
            with ui.column().classes("w-1/5 p-4 border-l bg-gray-50"):
                ui.label("控制面板").classes("text-lg font-semibold mb-4")

                # 执行模式切换
                ui.label("执行模式").classes("font-semibold mb-2")
                ui_state.execution_mode_switch = ui.switch("交互模式").classes("mb-4")
                ui_state.execution_mode_switch.value = True  # 默认交互模式

                # 可用工具列表
                ui.label("可用工具").classes("font-semibold mb-2")
                tools_container = ui.column().classes("w-full")
                update_tools_display(tools_container)

                # 状态监视器
                ui.label("状态监视").classes("font-semibold mb-2 mt-4")
                status_container = ui.column().classes("w-full text-xs")
                update_status_display(status_container)

    # 初始化时如果有当前工作流，自动设置目标
    if ui_state.current_workflow:
        ui_state.current_goal_display.text = (
            f"目标: {ui_state.current_workflow.initial_goal}"
        )
        add_chat_message("system", f"已加载工作流: {ui_state.current_workflow.name}")
        add_chat_message("system", f"初始目标: {ui_state.current_workflow.initial_goal}")


def update_stepper_display():
    """更新步骤进度条显示"""
    if ui_state.stepper:
        ui_state.stepper.clear()

        for i, step in enumerate(ui_state.app_state.vibe_plan):
            icon = "pending"
            color = "grey"

            if step.status == "in_progress":
                icon = "autorenew"
                color = "blue"
            elif step.status == "completed":
                icon = "done"
                color = "green"
            elif step.status == "failed":
                icon = "error"
                color = "red"

            with ui_state.stepper:
                with ui.step(f"步骤 {step.step_id + 1}"):
                    ui.label(step.description).classes("text-sm")
                    if step.analysis:
                        ui.label(f"结果: {step.analysis}").classes(
                            "text-xs text-gray-600"
                        )


def update_tools_display(container):
    """更新可用工具显示"""
    container.clear()

    with container:
        if ui_state.mcp_tools:
            for tool in ui_state.mcp_tools:
                tool_name = tool.get("function", {}).get("name", "Unknown")
                tool_desc = tool.get("function", {}).get("description", "")
                with ui.card().classes("w-full p-2 mb-2"):
                    ui.label(tool_name).classes("font-semibold text-xs")
                    ui.label(tool_desc).classes("text-xs text-gray-600")
        else:
            ui.label("暂无可用工具").classes("text-xs text-gray-500")


def update_status_display(container):
    """更新状态监视显示"""
    container.clear()

    with container:
        ui.label(f"工作流模式: {ui_state.app_state.workflow_mode}").classes("mb-1")
        ui.label(f"执行模式: {ui_state.app_state.execution_mode}").classes("mb-1")
        ui.label(f"活动步骤: {ui_state.app_state.active_step_id}").classes("mb-1")
        ui.label(f"工具执行需要: {ui_state.app_state.tool_execution_needed}").classes("mb-1")


def add_chat_message(role: str, content: str):
    """添加聊天消息"""
    if ui_state.chat_container:
        with ui_state.chat_container:
            if role == "user":
                with ui.row().classes("w-full justify-end mb-2"):
                    with ui.card().classes("bg-blue-500 text-white p-2 max-w-xl"):
                        ui.markdown(content).classes("text-sm")
            elif role == "assistant":
                with ui.row().classes("w-full justify-start mb-2"):
                    with ui.card().classes("bg-gray-200 p-2 max-w-xl"):
                        ui.markdown(content).classes("text-sm")
            elif role == "system":
                with ui.row().classes("w-full justify-center mb-2"):
                    with ui.card().classes("bg-yellow-100 p-2 max-w-md"):
                        ui.markdown(content).classes("text-xs text-gray-600")


def send_message(message: str, input_field):
    """发送用户消息"""
    logger.info(f"send_message called with: {message}")
    if not message.strip():
        return

    # 清空输入框
    input_field.value = ""

    # 添加用户消息到聊天
    add_chat_message("user", message)

    # 更新应用状态
    ui_state.app_state.user_input = message

    # 使用ui.timer来延迟执行异步任务，避免阻塞UI
    async def process_async():
        try:
            await process_user_input(message)
        except Exception as e:
            logger.error(f"异步处理失败: {e}")
            add_chat_message("system", f"处理失败: {e}")

    # 使用timer延迟执行异步函数
    ui.timer(0.1, process_async, once=True)


async def stream_and_render_response(result_container):
    """Helper to stream Burr result and render markdown response in the UI."""
    assistant_response = ""
    response_card = None

    if not ui_state.chat_container:
        # If there's no chat container, just consume the stream
        async for _ in result_container:
            pass
        return

    with ui_state.chat_container:
        with ui.row().classes("w-full justify-start mb-2"):
            response_card = ui.card().classes("bg-gray-200 p-2 max-w-xl")
            with response_card:
                ui.spinner(type="dots", size="sm")

    async for result in result_container:
        if isinstance(result, dict) and "answer" in result:
            chunk = result["answer"]
            assistant_response += chunk
            if response_card:
                response_card.clear()
                with response_card:
                    # Use a blinking cursor character to indicate streaming
                    ui.markdown(assistant_response + " ▌").classes("text-sm")

    # Final update without the cursor
    if response_card:
        response_card.clear()
        with response_card:
            if assistant_response:
                ui.markdown(assistant_response).classes("text-sm")
            else:
                # If there was no text response, the card will be empty and thus invisible
                pass


async def process_user_input(message: str):
    """处理用户输入并与Burr后端交互"""
    logger.info(f"process_user_input called with: {message}")
    try:
        # 设置用户输入
        if ui_state.current_workflow and not ui_state.app_state.current_goal:
            # 如果有当前工作流且这是第一次输入，使用工作流的初始目标
            actual_input = ui_state.current_workflow.initial_goal
            ui_state.app_state.current_goal = actual_input
            ui_state.current_goal_display.text = f"目标: {actual_input}"
        else:
            actual_input = message
        logger.info(f"actual_input: {actual_input}")

        # 设置执行模式
        execution_mode = "interactive"
        if ui_state.execution_mode_switch and hasattr(
            ui_state.execution_mode_switch, "value"
        ):
            execution_mode = (
                "interactive" if ui_state.execution_mode_switch.value else "yolo"
            )

        # 每次都重新创建Burr应用以确保状态正确
        # 这样避免了状态同步的复杂性
        # 在UI模式下，我们需要替换human_confirm action
        ui_state.burr_app = build_ui_application()

        # 手动设置应用状态的关键字段
        try:
            # 直接设置用户输入
            ui_state.burr_app.state.user_input = actual_input
            ui_state.burr_app.state.execution_mode = execution_mode
            ui_state.burr_app.state.current_goal = ui_state.app_state.current_goal
            ui_state.burr_app.state.vibe_plan = ui_state.app_state.vibe_plan
            ui_state.burr_app.state.chat_history = ui_state.app_state.chat_history

            logger.info(f"设置用户输入: {actual_input}")
            logger.info(f"设置执行模式: {execution_mode}")
        except Exception as e:
            logger.warning(f"设置应用状态时出错: {e}")

        # 设置停止条件 - 在chat_response结束后停止，让UI处理
        halt_conditions = ["chat_response", "human_confirm", "exit_chat"]

        # 运行应用直到需要人工干预或完成
        action, result_container = await ui_state.burr_app.astream_result(
            halt_after=halt_conditions
        )

        await stream_and_render_response(result_container)

        # 更新UI状态
        update_ui_from_burr_state()

        # 如果需要人工确认（存在待执行工具），显示工具确认UI
        if ui_state.app_state.tool_execution_needed:
            show_tool_confirmation()

    except Exception as e:
        logger.error(f"处理用户输入时出错: {e}")
        add_chat_message("system", f"处理出错: {e}")


def update_ui_from_burr_state():
    """从Burr应用状态更新UI状态"""
    try:
        if not ui_state.burr_app:
            return

        # 获取最新的应用状态
        burr_state = ui_state.burr_app.state

        # The burr_state should be a Pydantic model instance of ApplicationState
        # so we can just assign it.
        if isinstance(burr_state, ApplicationState):
            ui_state.app_state = burr_state.copy(deep=True)
        else:
            logger.warning(
                f"Burr state is not an ApplicationState instance, but {type(burr_state)}"
            )
            return

        # 更新UI组件
        if ui_state.current_goal_display:
            ui_state.current_goal_display.text = (
                f"目标: {ui_state.app_state.current_goal}"
            )

        # 更新步骤进度条
        update_stepper_display()

        # 更新状态监视器（如果页面上有相应容器）

    except Exception as e:
        logger.error(f"更新UI状态时出错: {e}")


def show_tool_confirmation():
    """显示工具调用确认UI"""
    if not ui_state.app_state.pending_tool_calls:
        return

    # 清除之前的确认卡片
    if ui_state.tool_confirmation_card:
        ui_state.tool_confirmation_card.delete()

    # 在聊天容器中添加工具确认卡片
    with ui_state.chat_container:
        with ui.card().classes(
            "w-full p-4 bg-yellow-100 border-yellow-400"
        ) as confirmation_card:
            ui_state.tool_confirmation_card = confirmation_card

            ui.label("🔧 需要您的授权来执行以下工具:").classes("font-semibold mb-3")

            # 列出所有待执行的工具
            for tool_call in ui_state.app_state.pending_tool_calls:
                with ui.row().classes("w-full mb-2"):
                    ui.icon("build").classes("text-blue-500 mr-2")
                    ui.label(
                        f"{tool_call.function.name}({tool_call.function.arguments})"
                    ).classes("text-sm font-mono")

            # 操作按钮
            with ui.row().classes("w-full justify-end mt-4 space-x-2"):

                def approve_handler():
                    ui.timer(0.1, approve_tools, once=True)

                def deny_handler():
                    ui.timer(0.1, deny_tools, once=True)

                approve_btn = ui.button("✅ 批准", on_click=approve_handler).classes(
                    "bg-green-500 text-white"
                )
                deny_btn = ui.button("❌ 拒绝", on_click=deny_handler).classes(
                    "bg-red-500 text-white"
                )


async def approve_tools():
    """批准工具执行"""
    try:
        # 设置批准状态
        ui_state.burr_app.state.tool_execution_allowed = True

        # 隐藏确认卡片
        if ui_state.tool_confirmation_card:
            ui_state.tool_confirmation_card.delete()
            ui_state.tool_confirmation_card = None

        add_chat_message("system", "工具执行已批准，正在执行...")

        # 继续执行Burr应用
        action, result_container = await ui_state.burr_app.astream_result(
            halt_after=["human_confirm", "exit_chat"]
        )

        await stream_and_render_response(result_container)

        # 更新UI状态
        update_ui_from_burr_state()

        # 如果又停在human_confirm，再次显示工具确认UI
        if action.name == "human_confirm":
            show_tool_confirmation()

    except Exception as e:
        logger.error(f"批准工具执行时出错: {e}")
        add_chat_message("system", f"执行出错: {e}")


async def deny_tools():
    """拒绝工具执行"""
    try:
        # 设置拒绝状态
        ui_state.burr_app.state.tool_execution_allowed = False

        # 隐藏确认卡片
        if ui_state.tool_confirmation_card:
            ui_state.tool_confirmation_card.delete()
            ui_state.tool_confirmation_card = None

        add_chat_message("system", "工具执行已拒绝")

        # 继续执行Burr应用
        action, result_container = await ui_state.burr_app.astream_result(
            halt_after=["human_confirm", "exit_chat"]
        )

        await stream_and_render_response(result_container)

        # 更新UI状态
        update_ui_from_burr_state()

    except Exception as e:
        logger.error(f"拒绝工具执行时出错: {e}")
        add_chat_message("system", f"处理出错: {e}")


async def initialize_mcp():
    """初始化MCP连接"""
    try:
        ui_state.mcp_client = await connect_to_mcp()
        if ui_state.mcp_client:
            ui_state.mcp_tools = ui_state.mcp_client.get_tools_for_llm()
            logger.info(f"MCP连接成功，可用工具: {len(ui_state.mcp_tools)}")

            # 如果vibe_workflow中有全局mcp_client和mcp_tools，也要更新它们
            try:
                import vibe_workflow

                vibe_workflow.mcp_client = ui_state.mcp_client
                vibe_workflow.mcp_tools = ui_state.mcp_tools
            except (ImportError, AttributeError):
                pass
        else:
            logger.warning("MCP连接失败")
    except Exception as e:
        logger.error(f"初始化MCP时出错: {e}")


# 应用启动时的初始化
@app.on_startup
async def startup():
    """应用启动时的初始化"""
    await initialize_mcp()
