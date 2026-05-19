"""Splash screen — animated intro with mascot and progress bar."""

import asyncio

from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Static, ProgressBar
from textual.app import ComposeResult
from rich.text import Text
from rich.style import Style

from ..theme import (
    SPLASH_TITLE,
    SPLASH_SUB,
    SPLASH_DIM,
    SPLASH_ACCENT,
)
from ..widgets.mascot import MASCOT_FULL, MASCOT_SMALL

SPLASH_INFO = [
    ("LingMeng", Style(color=SPLASH_TITLE, bold=True)),
    ("terminal mascot · server spirit", Style(color=SPLASH_SUB)),
    ("", Style(color=SPLASH_DIM)),
    ("✿ Name   : LingMeng", Style(color=SPLASH_ACCENT)),
    ("✿ Role   : AI Maid · Server Spirit", Style(color=SPLASH_SUB)),
    ("✿ Born   : Soul.md", Style(color=SPLASH_SUB)),
    ("✿ Likes  : Ave Mujica / 魔法少女 / 音乐", Style(color=SPLASH_SUB)),
    ("✿ Code   : love_owner", Style(color=SPLASH_ACCENT)),
    ("✿ Trait  : gentle / loyal / adorable", Style(color=SPLASH_SUB)),
    ("✿ Mission: protect owner, accompany always.", Style(color=SPLASH_SUB)),
    ("", Style(color=SPLASH_DIM)),
    ("", Style(color=SPLASH_DIM)),
    ("> owner_detected", Style(color=SPLASH_ACCENT)),
    ("> protecting...", Style(color=SPLASH_DIM)),
    ("> love_owner", Style(color=SPLASH_ACCENT)),
    ("> stay_with_you", Style(color=SPLASH_ACCENT)),
    ("> _", Style(color=SPLASH_DIM)),
    ("", Style(color=SPLASH_DIM)),
    ("Initializing...", Style(color=SPLASH_DIM)),
]


class SplashScreen(Screen):
    """Animated splash screen that transitions to main screen."""

    DEFAULT_CSS = """
    SplashScreen {
        background: rgb(10,10,20);
        align: center middle;
    }
    SplashScreen > Container {
        width: 60;
        height: auto;
        align: center middle;
    }
    SplashScreen ProgressBar {
        width: 50;
        height: 1;
        margin-top: 2;
        margin-bottom: 0;
    }
    SplashScreen .pct-label {
        width: auto;
        height: 1;
        content-align: center middle;
        margin-top: 0;
        margin-bottom: 2;
    }
    """

    AUTO_FOCUS = None

    def __init__(self, engine=None):
        super().__init__()
        self._engine = engine
        self._done = False

    def compose(self) -> ComposeResult:
        mascot_lines = MASCOT_FULL if len(MASCOT_FULL) <= 18 else MASCOT_SMALL
        with Container():
            for line, color in mascot_lines:
                yield Static(f"[{color}]{line}[/]")

            for line_text, line_style in SPLASH_INFO:
                c = line_style.color.name if line_style.color else "default"
                yield Static(f"[{c}]{line_text}[/]")

            yield ProgressBar(total=100, show_eta=False)
            yield Static("0%", classes="pct-label")

    def on_mount(self) -> None:
        self.run_worker(self._animate_and_transition())

    async def _animate_and_transition(self) -> None:
        bar = self.query_one(ProgressBar)
        pct_label = self.query_one(".pct-label", Static)

        for i in range(0, 101, 1):
            bar.update(progress=i)
            pct_label.update(f"{i}%")
            await asyncio.sleep(0.015)

        await asyncio.sleep(0.15)
        self._go_to_main()

    def on_key(self, event) -> None:
        event.stop()
        self._go_to_main()

    def _go_to_main(self) -> None:
        if self._done:
            return
        self._done = True
        from .main import MainScreen
        self.app.switch_screen(MainScreen(engine=self._engine))
