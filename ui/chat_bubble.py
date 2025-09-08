
import json
from typing import Any, Callable, Dict, List, Union

from nicegui import ui


class ChatBubble(ui.row):
    """A chat bubble component that can be used to display messages.

    It supports multi-part messages, markdown rendering, and tool calls with confirmation.
    It can also be used as a context manager to add custom child elements.
    """

    def __init__(
        self,
        content: Union[str, List[str]] = None,
        sent: bool = False,
        avatar: str = None,
        tool_calls: List[Dict[str, Any]] = None,
        on_tool_confirm: Callable[[bool], None] = None,
    ) -> None:
        """
        Initialize a ChatBubble.

        :param content: The message content, can be a string or a list of strings for multi-part messages.
        :param sent: True if the message was sent by the user, False for assistant.
        :param avatar: An optional avatar icon for the message.
        :param tool_calls: A list of tool calls to display.
        :param on_tool_confirm: A callback function to handle tool confirmation (Allow/Deny).
        """
        super().__init__()
        self.sent = sent
        self.classes(f"w-full justify-{'end' if sent else 'start'} mb-1 items-start")

        if not self.sent and avatar:
            ui.avatar(icon=avatar, size="md").classes("mt-1")

        self.card = ui.card().classes(
            f"{'user-message' if self.sent else 'assistant-message'} message-bubble"
        )
        with self.card:
            self.section = ui.card_section()
            with self.section:
                if content:
                    self._render_content(content)

                if tool_calls:
                    self._render_tool_calls(tool_calls, on_tool_confirm)

        if self.sent and avatar:
            ui.avatar(icon=avatar, size="md").classes("mt-1")

    def _render_content(self, content: Union[str, List[str]]):
        """Render the message content."""
        text_color = "text-white" if self.sent else ""
        if isinstance(content, list):
            for part in content:
                ui.markdown(part).classes(text_color)
        else:
            ui.markdown(content).classes(text_color)

    def _render_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        on_tool_confirm: Callable[[bool], None],
    ):
        """Render the tool call requests and confirmation buttons."""
        with ui.element("div").classes("my-2 p-2 rounded-lg"):
            ui.label("🔧 Tool Call(s) Requested:").classes(
                "text-sm font-bold mb-2"
            )
            for tool_call in tool_calls:
                with ui.card().classes("my-1 w-full bg-gray-100 shadow-inner"):
                    with ui.card_section().classes("py-2 px-3"):
                        ui.label(f"Function: `{tool_call['name']}`").classes(
                            "text-xs font-mono"
                        )
                        args = tool_call.get("arguments", {})
                        if args:
                            # Pretty print arguments using a code block
                            ui.code(
                                json.dumps(args, indent=2), language="json"
                            ).classes("text-xs w-full")

        if on_tool_confirm:
            with ui.row().classes("w-full justify-center gap-2 mt-2"):
                ui.button(
                    "✅ Allow",
                    color="positive",
                    on_click=lambda: on_tool_confirm(True),
                ).props("size=sm")
                ui.button(
                    "❌ Deny",
                    color="negative",
                    on_click=lambda: on_tool_confirm(False),
                ).props("size=sm")

    def __enter__(self):
        self.card.__enter__()
        self.section.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.section.__exit__(exc_type, exc_val, exc_tb)
        self.card.__exit__(exc_type, exc_val, exc_tb)

    @staticmethod
    def add_css() -> None:
        """Add the necessary CSS for styling chat bubbles."""
        ui.add_css(
            r'''
            :root {
                --primary: #2563eb;
                --primary-light: #3b82f6;
                --surface: #ffffff;
                --border: #e2e8f0;
                --shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
                --radius: 12px;
            }
            .message-bubble {
                max-width: 75%;
                margin-bottom: 0.5rem;
                animation: slideIn 0.2s ease-out;
                box-shadow: var(--shadow) !important;
            }
            @keyframes slideIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .user-message {
                background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%) !important;
                color: white !important;
                border-radius: var(--radius) var(--radius) 4px var(--radius) !important;
            }
            .assistant-message {
                background: var(--surface) !important;
                border: 1px solid var(--border) !important;
                color: var(--text) !important;
                border-radius: var(--radius) var(--radius) var(--radius) 4px !important;
            }
            .message-bubble .q-card__section {
                padding: 0.5rem 0.75rem !important;
            }
            .message-bubble p {
                margin: 0 !important;
                line-height: 1.5;
            }
            '''
        )
