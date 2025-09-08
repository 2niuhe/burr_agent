
from nicegui import ui
from chat_bubble import ChatBubble

@ui.page('/')
def main():
    # Add the CSS for the chat bubbles
    ChatBubble.add_css()

    ui.label('Chat Bubble Examples').classes('text-h4')

    ui.label('Simple user message:')
    ChatBubble('Hello, this is a user message.', sent=True, avatar='person')

    ui.label('Simple assistant message:')
    ChatBubble('Hello, this is an assistant message.', sent=False, avatar='smart_toy')

    ui.label('Multi-part message:')
    ChatBubble(['This is the first part.', 'And this is the second part.'], sent=True, avatar='person')

    ui.label('Message with child elements:')
    with ChatBubble(sent=False, avatar='smart_toy'):
        ui.label('This is a custom child element.')
        ui.image('https://picsum.photos/id/249/320/180').classes('w-32')

    ui.label('Tool call confirmation:')
    tool_calls = [
        {
            'name': 'run_shell_command',
            'arguments': {'command': 'ls -l'}
        },
        {
            'name': 'read_file',
            'arguments': {'file_path': '/path/to/file'}
        }
    ]

    def handle_confirmation(allowed: bool):
        ui.notify(f'Tool execution {"allowed" if allowed else "denied"}.')

    ChatBubble(
        'I need to run some tools. Please confirm.',
        sent=False,
        avatar='smart_toy',
        tool_calls=tool_calls,
        on_tool_confirm=handle_confirmation
    )

    ui.label('Collapsible long message:')
    long_text = '''
# This is a long message with Markdown

Here is some introductory text. We are going to show a list and some code.

## An Unordered List
* Item 1
* Item 2
    * Sub-item 2.1
    * Sub-item 2.2
* Item 3

This is a paragraph after the list. Now for some code:

```python
def hello_world():
    """A simple function to greet the world."""
    greeting = "Hello, World!"
    print(greeting)

# Call the function
hello_world()
```

The code block above shows a simple Python function.

**And here is some bold text.**

*And this is italic.*

---

### More content to exceed the line limit

We need to add more lines to ensure the collapsible feature is triggered. Let's just repeat some content.

- Line 1
- Line 2
- Line 3
- Line 4
- Line 5
- Line 6
- Line 7
- Line 8
- Line 9
- Line 10
'''
    ChatBubble(long_text, sent=False, avatar='smart_toy')

if __name__ in {"__main__", "__mp_main__"}:
    ui.run()
