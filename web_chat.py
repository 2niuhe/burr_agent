#!/usr/bin/env python3

import asyncio
import json
from typing import Dict, List

from nicegui import native, ui

from graphs.async_talk_with_tool import get_application
from logger import logger

# TODO:
# 1. 集成工作流，包括工作流列表、编辑
# 2. 支持选择工作流
# 3. 支持yolo模式
# 4. 支持vibe planner模式
# 5. 支持配置mcp服务
# 6. 优化提示词
# 7. 支持内存压缩
# 8. memory消息合并
# 9. 简化代码


class ChatInterface:
    def __init__(self):
        self.burr_app = None
        self.message_container = None
        self.text_input = None
        self.current_response_message = None
        self.send_button = None
        self.current_spinner = None
        self.pending_tool_confirmation = None
        self.current_pending_tools = []

    async def init_burr_application(self):
        """Initialize the Burr application with tool support"""
        self.burr_app = await get_application()

    async def clear_chat(self):
        """Clear chat and reset the application"""
        self.message_container.clear()
        await self.init_burr_application()
        ui.notify("Chat cleared", type="info")

    def create_user_message(self, content: str):
        """Create a user message bubble with proper styling"""
        with ui.row().classes("w-full justify-end mb-1"):
            with ui.card().classes("user-message message-bubble"):
                with ui.card_section():
                    ui.markdown(content).classes("text-white")

    def create_assistant_message(self, content: str = ""):
        """Create an assistant message bubble that can be updated"""
        with ui.row().classes("w-full justify-start mb-1"):
            card = ui.card().classes("assistant-message message-bubble")
            with card:
                section = ui.card_section()
                with section:
                    if content:
                        message_element = ui.markdown(content)
                    else:
                        message_element = ui.markdown("_Typing..._")
        return message_element

    def create_tool_confirmation_ui(self, pending_tools: List[Dict]):
        """Create UI for tool execution confirmation"""
        with ui.row().classes("w-full justify-center mb-1"):
            with ui.card().classes("tool-confirmation"):
                with ui.card_section().classes("py-3 px-4"):
                    ui.label("🔧 Tool Execution Request").classes("text-h6 mb-2")
                    ui.label(
                        f"The assistant wants to execute {len(pending_tools)} tool(s):"
                    ).classes("mb-3")

                    # Display tool details
                    for i, tool_call in enumerate(pending_tools, 1):
                        with ui.expansion(
                            f"{i}. {tool_call['name']}", icon="build"
                        ).classes("w-full mb-2"):
                            ui.code(
                                json.dumps(
                                    tool_call["arguments"], indent=2, ensure_ascii=False
                                )
                            ).classes("text-xs")

                    # Confirmation buttons
                    with ui.row().classes("w-full justify-center gap-4 mt-4"):

                        async def handle_allow():
                            await self.handle_tool_confirmation(True)

                        async def handle_deny():
                            await self.handle_tool_confirmation(False)

                        allow_btn = ui.button(
                            "✅ Allow", color="positive", on_click=handle_allow
                        )
                        deny_btn = ui.button(
                            "❌ Deny", color="negative", on_click=handle_deny
                        )

                    return allow_btn, deny_btn

    async def handle_tool_confirmation(self, allowed: bool):
        """Handle user's tool execution confirmation"""
        logger.debug(f"Tool confirmation: {'allowed' if allowed else 'denied'}")

        # Remove the confirmation UI first
        if self.pending_tool_confirmation:
            try:
                self.pending_tool_confirmation.delete()
            except:
                pass  # Ignore if already deleted
            self.pending_tool_confirmation = None

        # Create new response message for tool execution results
        with self.message_container:
            self.current_response_message = self.create_assistant_message()

            # Add spinner for tool execution
            with ui.row().classes("w-full justify-center"):
                self.current_spinner = ui.spinner(type="dots", size="sm").classes(
                    "text-primary"
                )

        # Continue with Burr application
        try:
            user_input = "y" if allowed else "n"
            action, result_container = await self.burr_app.astream_result(
                halt_after=["execute_tools", "get_fellow_input"],
                halt_before=[],
                inputs={"user_input": user_input},
            )

            response_text = ""

            # Stream the response
            async for result in result_container:
                content = result.get("content", "")
                if content:
                    response_text += content
                    # Update the markdown content
                    if self.current_response_message:
                        self.current_response_message.content = response_text

                    # Skip auto scroll during tool execution to avoid context issues
                    pass

            # Ensure we have content to display
            if not response_text:
                if not allowed:
                    response_text = "❌ Tool execution was denied by user. I cannot proceed with the requested operation."
                else:
                    response_text = "⚠️ No response received from the system."

                # Update the UI message
                if self.current_response_message:
                    self.current_response_message.content = response_text

        except Exception as e:
            error_message = f"❌ Error: {str(e)}"
            if self.current_response_message:
                self.current_response_message.content = error_message
            try:
                ui.notify(f"Error occurred: {str(e)}", type="negative")
            except:
                logger.error(f"Error occurred: {str(e)}")

        finally:
            # Remove spinner and re-enable send button
            if self.current_spinner:
                try:
                    self.current_spinner.delete()
                except:
                    pass  # Ignore if already deleted
                self.current_spinner = None

            # Ensure message is not stuck in "Typing..." state
            if (
                self.current_response_message
                and self.current_response_message.content == "_Typing..._"
            ):
                self.current_response_message.content = "❌ Operation completed."

            if self.send_button:
                try:
                    self.send_button.props(remove="disable")
                except:
                    pass  # Ignore if send button is not available

    async def send_message(self) -> None:
        """Send a message and handle the streaming response"""
        if not self.text_input.value.strip():
            return

        question = self.text_input.value.strip()
        self.text_input.value = ""

        # Disable send button during processing
        if self.send_button:
            self.send_button.props("disable")

        # Add user message to UI with custom styling
        with self.message_container:
            self.create_user_message(question)

            # Add assistant message placeholder
            self.current_response_message = self.create_assistant_message()

            # Add spinner
            with ui.row().classes("w-full justify-center"):
                self.current_spinner = ui.spinner(type="dots", size="sm").classes(
                    "text-primary"
                )

        try:
            # Get the action and result container from Burr
            action, result_container = await self.burr_app.astream_result(
                halt_after=["ask_llm_with_tool"], inputs={"user_input": question}
            )

            response_text = ""
            detected_tool_calls = []

            # Stream the response
            async for result in result_container:
                # Handle different types of result objects
                if hasattr(result, "get"):
                    content = result.get("content", "")
                elif hasattr(result, "content"):
                    content = result.content
                else:
                    content = ""

                if content:
                    response_text += content
                    # Update the markdown content
                    self.current_response_message.content = response_text

                    # Auto scroll to bottom
                    ui.run_javascript("window.scrollTo(0, document.body.scrollHeight)")

                # Check if tool calls are detected in the stream message
                if hasattr(result, "tool_calls") and result.tool_calls:
                    try:
                        # Ensure tool_calls is iterable and contains valid objects
                        if isinstance(result.tool_calls, list):
                            detected_tool_calls.extend(result.tool_calls)
                            logger.debug(
                                f"Tool calls detected in stream: {len(result.tool_calls)} tools"
                            )
                        else:
                            logger.debug(
                                f"Tool calls is not a list: {type(result.tool_calls)}"
                            )
                    except Exception as e:
                        logger.error(f"Error processing tool calls: {e}")

            # Check if we need to handle tool confirmation
            next_action = self.burr_app.get_next_action()
            logger.debug(f"Next action: {next_action.name if next_action else 'None'}")
            logger.debug(
                f"Detected tool calls in stream: {len(detected_tool_calls)} tools"
            )

            if (
                next_action and next_action.name == "human_confirm"
            ) or detected_tool_calls:
                pending_tools = []

                # First, try to use tool calls from the stream
                if detected_tool_calls:
                    logger.debug(
                        f"Using tool calls from stream: {len(detected_tool_calls)} tools"
                    )
                    for tool_call in detected_tool_calls:
                        try:
                            # Extract tool information from ToolCall object
                            arguments = tool_call.function.arguments
                            if isinstance(arguments, str):
                                arguments = json.loads(arguments)

                            pending_tools.append(
                                {
                                    "name": tool_call.function.name,
                                    "arguments": arguments,
                                }
                            )
                            logger.debug(
                                f"Added tool from stream: {tool_call.function.name} with args: {arguments}"
                            )
                        except Exception as e:
                            logger.error(f"Error processing tool call from stream: {e}")

                # If no tools from stream, try application state as fallback
                if not pending_tools:
                    app_state = self.burr_app.state
                    logger.debug(
                        f"App state has pending_tool_calls: {hasattr(app_state, 'pending_tool_calls')}"
                    )
                    if (
                        hasattr(app_state, "pending_tool_calls")
                        and app_state.pending_tool_calls
                    ):
                        logger.debug(
                            f"Pending tool calls from state: {len(app_state.pending_tool_calls)}"
                        )
                        for tool_call in app_state.pending_tool_calls:
                            try:
                                arguments = tool_call.function.arguments
                                if isinstance(arguments, str):
                                    arguments = json.loads(arguments)

                                pending_tools.append(
                                    {
                                        "name": tool_call.function.name,
                                        "arguments": arguments,
                                    }
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error processing tool call from state: {e}"
                                )

                if pending_tools:
                    logger.debug(
                        f"Creating tool confirmation UI for {len(pending_tools)} tools"
                    )
                    try:
                        # Create tool confirmation UI
                        with self.message_container:
                            self.pending_tool_confirmation = ui.column().classes(
                                "w-full"
                            )
                            with self.pending_tool_confirmation:
                                self.create_tool_confirmation_ui(pending_tools)

                        # Remove spinner when showing confirmation UI
                        if self.current_spinner:
                            self.current_spinner.delete()
                            self.current_spinner = None

                        logger.debug("Tool confirmation UI created successfully")
                        # Don't continue processing - wait for user confirmation
                        return
                    except Exception as e:
                        logger.error(f"Error creating tool confirmation UI: {e}")
                else:
                    logger.debug("No pending tools found")

        except Exception as e:
            # Handle errors
            error_message = f"❌ Error: {str(e)}"
            self.current_response_message.content = error_message

            ui.notify(f"Error occurred: {str(e)}", type="negative")

        finally:
            # Remove spinner and re-enable send button
            if self.current_spinner:
                self.current_spinner.delete()
                self.current_spinner = None
            if self.send_button:
                self.send_button.props(remove="disable")

    def create_ui(self):
        """Create the NiceGUI interface"""
        ui.add_css(
            r"""
            :root {
                --primary: #2563eb;
                --primary-light: #3b82f6;
                --secondary: #f1f5f9;
                --background: #fafafa;
                --surface: #ffffff;
                --text: #1e293b;
                --text-light: #64748b;
                --border: #e2e8f0;
                --shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
                --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
                --radius: 12px;
                --radius-sm: 8px;
            }

            /* Chat container */
            .chat-container {
                height: calc(100vh - 120px);
                overflow-y: auto;
                padding: 1rem;
                background: var(--background);
                scroll-behavior: smooth;
            }

            /* Message bubbles */
            .message-bubble {
                max-width: 75%;
                margin-bottom: 0.75rem;
                animation: slideIn 0.2s ease-out;
            }

            @keyframes slideIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .user-message {
                background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%) !important;
                color: white !important;
                margin-left: auto;
                border-radius: var(--radius) var(--radius) 4px var(--radius) !important;
                box-shadow: var(--shadow) !important;
            }

            .assistant-message {
                background: var(--surface) !important;
                border: 1px solid var(--border) !important;
                color: var(--text) !important;
                margin-right: auto;
                border-radius: var(--radius) var(--radius) var(--radius) 4px !important;
                box-shadow: var(--shadow) !important;
            }

            .message-bubble .q-card__section {
                padding: 0.75rem 1rem !important;
            }

            .message-bubble p {
                margin: 0 !important;
                line-height: 1.5;
            }

            /* Tool confirmation */
            .tool-confirmation {
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%) !important;
                border: 1px solid #f59e0b !important;
                border-radius: var(--radius) !important;
                box-shadow: var(--shadow-lg) !important;
                max-width: 80% !important;
                margin: 1rem auto !important;
            }

            .tool-confirmation .q-card__section {
                border-radius: var(--radius) !important;
            }

            /* Input area */
            .input-container {
                background: var(--surface);
                border-top: 1px solid var(--border);
                padding: 1rem;
                box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
            }

            .message-input {
                background: var(--surface) !important;
                border: 1px solid var(--border) !important;
                border-radius: 4px !important;
                transition: all 0.2s ease;
            }

            .message-input:focus-within {
                border-color: var(--primary) !important;
                box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1) !important;
            }

            /* Header */
            .app-header {
                background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%) !important;
                box-shadow: var(--shadow) !important;
            }

            /* Responsive design */
            @media (max-width: 768px) {
                .message-bubble { max-width: 90%; }
                .chat-container { padding: 0.5rem; }
                .input-container { padding: 0.75rem; }
            }

            /* Loading states */
            .typing-indicator {
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }

            .typing-dot {
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background: var(--text-light);
                animation: typing 1.4s infinite;
            }

            .typing-dot:nth-child(2) { animation-delay: 0.2s; }
            .typing-dot:nth-child(3) { animation-delay: 0.4s; }

            @keyframes typing {
                0%, 60%, 100% { opacity: 0.3; }
                30% { opacity: 1; }
            }
        """
        )

        # App layout setup
        ui.query(".q-page").classes("flex column")
        ui.query(".nicegui-content").classes("w-full h-full")

        # Compact header
        with ui.header().classes("app-header").style("height: 56px"):
            with ui.row().classes("w-full items-center justify-between px-4"):
                ui.label("🤖 Burr Agent").classes("text-h6 font-medium")
                ui.button(
                    icon="refresh",
                    on_click=lambda: asyncio.create_task(self.clear_chat()),
                ).props("flat round size=sm").tooltip("Clear chat")

        # Main chat area
        self.message_container = ui.column().classes("chat-container w-full")

        # Input area
        with ui.footer().classes("input-container"):
            with ui.row().classes("w-full items-end gap-3 max-w-4xl mx-auto"):
                self.text_input = (
                    ui.input(placeholder="Ask me anything...")
                    .props("outlined autogrow")
                    .classes("flex-grow message-input")
                )

                self.send_button = (
                    ui.button(icon="send", on_click=self.send_message)
                    .props("round color=primary size=md")
                    .style("min-width: 48px")
                )


@ui.page("/")
async def main():
    """Main page setup"""
    chat_interface = ChatInterface()
    # Initialize Burr application asynchronously
    await chat_interface.init_burr_application()
    chat_interface.create_ui()


if __name__ == "__main__":
    # Enable async support in NiceGUI
    ui.run(
        title="Burr Agent Web Chat with Tools",
        native=False,
        port=native.find_open_port(start_port=8080),
        host="127.0.0.1",
        favicon="./favicon.ico",
        show=True,
        reload=False,
    )
