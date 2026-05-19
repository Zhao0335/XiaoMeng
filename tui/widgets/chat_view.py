"""Chat view widget — message display with styled bubbles."""

from textual.widgets import Static, Input
from textual.message import Message
from rich.text import Text
from rich.style import Style

from ..theme import (
    BUBBLE_USER_BG,
    BUBBLE_USER_FG,
    BUBBLE_ASST_BG,
    BUBBLE_ASST_FG,
    BUBBLE_SYS_BG,
    BUBBLE_SYS_FG,
)
from ..events import ChatSubmitted


class ChatView(Static):
    """Chat message view — accumulates messages into a single Rich Text."""

    DEFAULT_CSS = """
    ChatView {
        width: 100%;
        height: 1fr;
        padding: 0 2;
        overflow-y: auto;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(Text(), *args, **kwargs)
        self._lines: list[Text] = []

    def add_user_message(self, text: str) -> None:
        self._append_bubble(text, BUBBLE_USER_BG, BUBBLE_USER_FG)

    def add_assistant_message(self, text: str) -> None:
        self._append_bubble(text, BUBBLE_ASST_BG, BUBBLE_ASST_FG)

    def add_system_message(self, text: str) -> None:
        lines = Text()
        for line in text.split("\n"):
            if line.strip():
                lines.append(f"  {line}\n", style=Style(color=BUBBLE_SYS_FG))
            else:
                lines.append("\n")
        self._lines.append(lines)
        self._refresh()

    def clear_messages(self) -> None:
        self._lines.clear()
        self.update(Text())

    def _append_bubble(self, text: str, bg: str, fg: str) -> None:
        bubble = Text()
        for line in text.split("\n"):
            if line.strip():
                bubble.append(
                    f"  {line}\n",
                    style=Style(color=fg, bgcolor=bg),
                )
            else:
                bubble.append("\n")
        self._lines.append(bubble)
        self._refresh()

    def _refresh(self) -> None:
        result = Text()
        for i, line in enumerate(self._lines):
            if i > 0:
                result.append("\n")
            result.append(line)
        self.update(result)


class ChatInput(Input):
    """Chat input bar with submit handling."""

    DEFAULT_CSS = """
    ChatInput {
        dock: bottom;
        width: 100%;
        margin: 0 1 1 1;
        border: solid rgb(90,90,170);
        background: rgb(18,18,42);
        color: rgb(224,224,240);
    }
    ChatInput:focus {
        border: solid rgb(184,160,255);
    }
    """

    def on_submit(self, event) -> None:
        text = event.value.strip()
        if text:
            self.post_message(ChatSubmitted(text))
            self.value = ""
