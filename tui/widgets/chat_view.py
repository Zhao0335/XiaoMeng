"""Chat view widget — message display with styled bubbles."""

from textual.containers import VerticalScroll
from textual.widgets import Static, Input
from textual.message import Message
from rich.text import Text
from rich.style import Style
from rich.panel import Panel
from rich.markdown import Markdown

from ..theme import (
    BUBBLE_USER_BG,
    BUBBLE_USER_FG,
    BUBBLE_ASST_BG,
    BUBBLE_ASST_FG,
    BUBBLE_SYS_BG,
    BUBBLE_SYS_FG,
    SUCCESS,
    ERROR,
    ACCENT,
)

from ..events import ChatSubmitted


class ChatView(VerticalScroll):
    """Scrollable chat message view with styled bubbles."""

    DEFAULT_CSS = """
    ChatView {
        width: 100%;
        height: 1fr;
        padding: 0 1;
        overflow-y: auto;
    }
    ChatView > .chat-user {
        width: 100%;
        padding: 0 1;
        margin: 1 0;
        text-align: right;
    }
    ChatView > .chat-asst {
        width: 100%;
        padding: 0 1;
        margin: 1 0;
        text-align: left;
    }
    ChatView > .chat-system {
        width: 100%;
        padding: 0 2;
        margin: 0;
        text-align: center;
    }
    ChatView > .chat-empty {
        width: 100%;
        height: 1fr;
        content-align: center middle;
    }
    """

    def add_user_message(self, text: str) -> None:
        bubble = Static(
            Panel(
                Text(text, style=Style(color=BUBBLE_USER_FG)),
                border_style=Style(color=BUBBLE_USER_BG),
                style=Style(bgcolor=BUBBLE_USER_BG),
                expand=False,
                padding=(0, 1),
            ),
            classes="chat-user",
        )
        self.mount(bubble)
        self.scroll_end(animate=False)

    def add_assistant_message(self, text: str) -> None:
        bubble = Static(
            Panel(
                Text(text, style=Style(color=BUBBLE_ASST_FG)),
                border_style=Style(color=BUBBLE_ASST_BG),
                style=Style(bgcolor=BUBBLE_ASST_BG),
                expand=False,
                padding=(0, 1),
            ),
            classes="chat-asst",
        )
        self.mount(bubble)
        self.scroll_end(animate=False)

    def add_system_message(self, text: str) -> None:
        bubble = Static(
            Panel(
                Text(text, style=Style(color=BUBBLE_SYS_FG)),
                border_style=Style(color=BUBBLE_SYS_BG),
                style=Style(bgcolor=BUBBLE_SYS_BG),
                expand=False,
                padding=(0, 1),
            ),
            classes="chat-system",
        )
        self.mount(bubble)
        self.scroll_end(animate=False)

    def clear_messages(self) -> None:
        for child in list(self.children):
            if child.id != "chat-input":
                child.remove()


class ChatInputBar(Input):
    """Chat input bar with submit handling."""

    DEFAULT_CSS = """
    ChatInputBar {
        dock: bottom;
        width: 100%;
        margin: 1 2;
        border: solid rgb(90,90,170);
        background: rgb(18,18,42);
        color: rgb(224,224,240);
    }
    ChatInputBar:focus {
        border: solid rgb(184,160,255);
    }
    """

    def on_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.post_message(ChatSubmitted(text))
            self.value = ""
