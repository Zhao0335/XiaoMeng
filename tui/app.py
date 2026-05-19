"""LingMeng TUI — Main Textual Application.

Modern terminal interface powered by Textual framework.
Features reactive state management, CSS theming, and modular architecture.
"""

import asyncio
from textual.app import App, ComposeResult
from textual.reactive import reactive

from .screens import SplashScreen, MainScreen
from .services import ChatEngine
from .utils import load_config
from .theme import BG_DEEP


class LingMengApp(App):
    """XiaoMeng Terminal v3 — Powered by Textual.

    Technology Stack:
    - Textual 8.x — Industry-leading Python TUI framework
    - Rich 14.x — Beautiful terminal rendering
    - Reactive data binding
    - CSS-based theming system
    - Async/await native architecture
    """

    TITLE = "LingMeng Terminal"
    SUB_TITLE = "AI Maid · Server Spirit"

    CSS = f"""
    Screen {{
        background: {BG_DEEP};
    }}
    """

    BINDINGS = []

    def __init__(self):
        super().__init__()
        self._engine = ChatEngine(load_config())
        self._engine.initialize()

    def on_mount(self) -> None:
        self.push_screen(SplashScreen(engine=self._engine))

    def get_engine(self) -> ChatEngine:
        return self._engine


def main() -> None:
    """Entry point for LingMeng TUI."""
    app = LingMengApp()
    app.run()


if __name__ == "__main__":
    main()
