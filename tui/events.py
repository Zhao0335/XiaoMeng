"""Custom Textual messages for inter-component communication."""

from textual.message import Message


class TabSelected(Message):
    """Emitted when a tab is selected."""
    def __init__(self, tab_index: int, tab_name: str) -> None:
        self.tab_index = tab_index
        self.tab_name = tab_name
        super().__init__()


class ChatSubmitted(Message):
    """Emitted when user submits a chat message."""
    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class ChatStreamUpdate(Message):
    """Emitted during streaming chat response."""
    def __init__(self, text: str, done: bool = False) -> None:
        self.text = text
        self.done = done
        super().__init__()


class ConfigChanged(Message):
    """Emitted when configuration is modified."""
    def __init__(self, key: str, value) -> None:
        self.key = key
        self.value = value
        super().__init__()


class ConfigSaved(Message):
    """Emitted when config is saved successfully."""


class MascotMoodChanged(Message):
    """Emitted to change mascot mood."""
    def __init__(self, mood: str) -> None:
        self.mood = mood
        super().__init__()


class StatusNotify(Message):
    """Emitted for status bar notifications."""
    def __init__(self, message: str, level: str = "info") -> None:
        self.message = message
        self.level = level
        super().__init__()


class EngineStateChanged(Message):
    """Emitted when chat engine state changes."""
    def __init__(self, state: str) -> None:
        self.state = state
        super().__init__()
