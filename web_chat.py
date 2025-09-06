#!/usr/bin/env python3
import asyncio
from typing import Dict, Any, List
from burr.core import GraphBuilder, ApplicationBuilder
from burr.core import when, expr
from actions import get_user_input, exit_chat, human_confirm, execute_tools, ask_llm
from utils.schema import Role, Message
from nicegui import ui, app
import html

# System prompt for the assistant
system_prompt = """You are a helpful assistant.
"""

class ChatInterface:
    def __init__(self):
        self.burr_app = None
        self.message_container = None
        self.text_input = None
        self.current_response_message = None
        self.send_button = None
        self.current_spinner = None
        self.chat_history: List[Dict[str, str]] = []
        self.init_burr_application()
    
    def init_burr_application(self):
        """Initialize the Burr application"""
        graph = GraphBuilder().with_actions(
            get_init_input=get_user_input.bind(system_prompt=system_prompt),
            get_fellow_input=get_user_input,
            ask_llm=ask_llm
        ).with_transitions(
            ("get_init_input", "ask_llm", when(exit_chat=False)),
            ("get_fellow_input", "ask_llm", when(exit_chat=False)),
            ("ask_llm", "get_fellow_input", when(exit_chat=False)),
        ).build()
        
        self.burr_app = ApplicationBuilder().with_graph(
            graph).with_entrypoint("get_init_input").with_tracker("local", project="burr_agent_web").build()
    
    def clear_chat(self):
        """Clear chat history and reset the application"""
        self.chat_history.clear()
        self.message_container.clear()
        self.init_burr_application()
        ui.notify("Chat history cleared", type='info')
    
    def create_user_message(self, content: str):
        """Create a user message bubble with proper styling"""
        with ui.row().classes('w-full justify-end mb-3'):
            with ui.card().classes('user-message'):
                with ui.card_section().classes('py-2 px-3'):
                    ui.markdown(content).classes('text-white')
    
    def create_assistant_message(self, content: str = ""):
        """Create an assistant message bubble that can be updated"""
        with ui.row().classes('w-full justify-start mb-3'):
            card = ui.card().classes('assistant-message')
            with card:
                section = ui.card_section().classes('py-2 px-3')
                with section:
                    if content:
                        message_element = ui.markdown(content)
                    else:
                        message_element = ui.markdown("_Typing..._")
        return message_element
    
    async def send_message(self) -> None:
        """Send a message and handle the streaming response"""
        if not self.text_input.value.strip():
            return
            
        question = self.text_input.value.strip()
        self.text_input.value = ''
        
        # Disable send button during processing
        if self.send_button:
            self.send_button.props('disable')
        
        # Add user message to chat history
        self.chat_history.append({"role": "user", "content": question})
        
        # Add user message to UI with custom styling
        with self.message_container:
            self.create_user_message(question)
            
            # Add assistant message placeholder
            self.current_response_message = self.create_assistant_message()
            
            # Add spinner
            with ui.row().classes('w-full justify-center'):
                self.current_spinner = ui.spinner(type='dots', size='sm').classes('text-primary')
        
        try:
            # Get the action and result container from Burr
            action, result_container = await self.burr_app.astream_result(
                halt_after=["ask_llm"], 
                inputs={"user_input": question}
            )
            
            response_text = ""
            
            # Stream the response
            async for result in result_container:
                content = result.get("content", "")
                if content:
                    response_text += content
                    # Update the markdown content
                    self.current_response_message.content = response_text
                    
                    # Auto scroll to bottom
                    ui.run_javascript('window.scrollTo(0, document.body.scrollHeight)')
            
            # Add assistant response to chat history
            if response_text:
                self.chat_history.append({"role": "assistant", "content": response_text})
            
        except Exception as e:
            # Handle errors
            error_message = f"❌ Error: {str(e)}"
            self.current_response_message.content = error_message
            
            # Add error to chat history
            self.chat_history.append({"role": "assistant", "content": error_message})
            ui.notify(f"Error occurred: {str(e)}", type='negative')
            
        finally:
            # Remove spinner and re-enable send button
            if self.current_spinner:
                self.current_spinner.delete()
                self.current_spinner = None
            if self.send_button:
                self.send_button.props(remove='disable')
    
    def export_chat_history(self):
        """Export chat history as text"""
        if not self.chat_history:
            ui.notify("No chat history to export", type='warning')
            return
        
        history_text = "# Chat History\n\n"
        for message in self.chat_history:
            role = message["role"].title()
            content = message["content"]
            history_text += f"**{role}:** {content}\n\n"
        
        # Create a downloadable file
        ui.download(history_text.encode(), filename="chat_history.md")
        ui.notify("Chat history exported", type='positive')
    
    def create_ui(self):
        """Create the NiceGUI interface"""
        ui.add_css(r'''
            a:link, a:visited {color: inherit !important; text-decoration: none; font-weight: 500}
            .chat-container {
                max-height: 75vh; 
                overflow-y: auto;
                padding: 1rem 2rem;
                background: #f8f9fa;
            }
            .message-input {background: white; border-radius: 20px;}
            .user-message {
                background: #1976d2 !important;
                color: white !important;
                margin-left: 15%;
                max-width: 70% !important;
                border-radius: 18px 18px 4px 18px !important;
            }
            .assistant-message {
                background: white !important;
                border: 1px solid #e0e0e0 !important;
                margin-right: 15%;
                max-width: 70% !important;
                border-radius: 18px 18px 18px 4px !important;
            }
            .q-card {
                box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
            }
            .chat-layout {
                max-width: 100% !important;
                width: 100% !important;
                margin: 0 !important;
                padding: 0 1rem !important;
            }
            .history-container {
                max-height: 75vh;
                overflow-y: auto;
                padding: 1rem;
            }
        ''')
        
        # Layout setup for full height
        ui.query('.q-page').classes('flex')
        ui.query('.nicegui-content').classes('w-full')
        
        # Header
        with ui.header().classes('bg-primary text-white shadow-2'):
            with ui.row().classes('w-full items-center justify-between px-4'):
                ui.label('Burr Agent Web Chat').classes('text-h6')
                with ui.row():
                    ui.button('Clear Chat', icon='clear', on_click=self.clear_chat) \
                        .props('flat color=white')
                    ui.button('Export', icon='download', on_click=self.export_chat_history) \
                        .props('flat color=white')
        
        with ui.tabs().classes('w-full') as tabs:
            chat_tab = ui.tab('Chat')
            history_tab = ui.tab('History')
        
        with ui.tab_panels(tabs, value=chat_tab).classes('w-full chat-layout flex-grow items-stretch'):
            # Chat panel - 主要聊天区域
            self.message_container = ui.tab_panel(chat_tab).classes('items-stretch chat-container')
            
            # History panel - 聊天历史
            with ui.tab_panel(history_tab).classes('history-container'):
                ui.label('Chat History').classes('text-h6 mb-4')
                
                def refresh_history():
                    history_display.clear()
                    if not self.chat_history:
                        with history_display:
                            ui.label('No chat history yet.').classes('text-grey-6 text-center')
                    else:
                        with history_display:
                            for i, message in enumerate(self.chat_history):
                                role = message["role"]
                                content = message["content"]
                                
                                if role == 'user':
                                    with ui.row().classes('w-full justify-end mb-3'):
                                        with ui.card().classes('user-message'):
                                            with ui.card_section().classes('py-2 px-3'):
                                                ui.markdown(content).classes('text-white')
                                else:
                                    with ui.row().classes('w-full justify-start mb-3'):
                                        with ui.card().classes('assistant-message'):
                                            with ui.card_section().classes('py-2 px-3'):
                                                ui.markdown(content)
                
                history_display = ui.column().classes('w-full')
                refresh_history()
                
                ui.button('Refresh', icon='refresh', on_click=refresh_history) \
                    .props('color=primary') \
                    .classes('mt-4')
        
        # Footer with input - 全宽度布局
        with ui.footer().classes('bg-white border-t'), ui.column().classes('w-full my-4 px-4'):
            with ui.row().classes('w-full no-wrap items-center gap-2 max-w-6xl mx-auto'):
                self.text_input = ui.input(placeholder='Type your message here...') \
                    .props('rounded outlined dense') \
                    .classes('flex-grow message-input') \
                    .on('keydown.enter', self.send_message)
                
                self.send_button = ui.button('Send', icon='send', on_click=self.send_message) \
                    .props('color=primary rounded')
            
            ui.markdown('Built with [Burr](https://github.com/DAGWorks-Inc/burr) and [NiceGUI](https://nicegui.io)') \
                .classes('text-xs self-center mt-2 text-grey-6')


@ui.page('/')
async def main():
    """Main page setup"""
    chat_interface = ChatInterface()
    chat_interface.create_ui()


if __name__ == "__main__":
    # Enable async support in NiceGUI
    ui.run(
        title='Burr Agent Web Chat',
        port=8080,
        host='0.0.0.0',
        show=True,
        reload=False
    )
