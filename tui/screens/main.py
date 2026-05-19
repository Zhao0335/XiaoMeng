"""Main screen — primary interface with side panel and tabbed content."""

import copy
from datetime import datetime
from typing import Any, Dict, List, Optional

from textual.screen import Screen
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Static, TabbedContent, TabPane,
)
from textual.binding import Binding
from textual.reactive import reactive

from rich.text import Text
from rich.style import Style

from ..theme import (
    ACCENT, SUCCESS, ERROR, WARNING, INFO,
    BG_DEEP, BG_PANEL, BG_SURFACE,
    FG_PRIMARY, FG_SECONDARY, FG_DIM,
    BORDER_COLOR, BORDER_ACCENT,
)
from ..events import (
    ChatSubmitted, StatusNotify,
)
from ..services import ChatEngine
from ..utils import load_config, save_config, set_nested, get_nested, parse_value, is_sensitive, mask_value, truncate
from ..widgets.mascot import MASCOT_TINY, MASCOT_SMALL, MASCOT_FULL, MOOD_FACES, MOOD_MAP
from ..widgets.chat_view import ChatView, ChatInput
from ..widgets.config_tree import ConfigTreeWidget
from ..widgets.status_view import StatusViewWidget
from ..widgets.help_view import HelpViewWidget


class MainScreen(Screen):
    """Main application screen with side panel and content tabs.

    Layout:
    ┌─────────────┬──────────────────────────────────┐
    │   Sidebar   │     Tabbed Content Area          │
    │  ┌───────┐  │  ┌────────────────────────────┐  │
    │  │Mascot │  │  │ 💬 Chat │⚙Config│📊Stat│📖│  │
    │  └───────┘  │  ├────────────────────────────┤  │
    │   Info      │  │                            │  │
    │   Status    │  │    Active Tab Content      │  │
    │   Mood      │  │                            │  │
    │   Keys      │  │                            │  │
    │             │  └────────────────────────────┘  │
    └─────────────┴──────────────────────────────────┘
    ┌────────────────────────────────────────────────┐
    │   Status Bar (key hints · time · dirty flag)   │
    └────────────────────────────────────────────────┘
    """

    DEFAULT_CSS = f"""
    MainScreen {{
        background: {BG_DEEP};
        layers: sidebar content status-bar;
    }}

    MainScreen > Horizontal {{
        width: 100%;
        height: 1fr;
    }}

    .sidebar {{
        width: 28;
        height: 100%;
        background: {BG_PANEL};
        border-right: heavy {BORDER_COLOR};
        padding: 0 1;
        layer: sidebar;
    }}
    .sidebar > Vertical {{
        width: 100%;
        height: 100%;
    }}
    .sidebar-mascot {{
        width: 100%;
        height: auto;
        min-height: 8;
        content-align: center middle;
        padding: 1 0;
        background: {BG_SURFACE};
        border: solid {BORDER_COLOR};
    }}
    .sidebar-info {{
        width: 100%;
        height: 1fr;
        padding: 1 0;
        margin-top: 1;
    }}

    .content-area {{
        width: 1fr;
        height: 100%;
        layer: content;
    }}
    .content-area TabbedContent {{
        width: 100%;
        height: 100%;
    }}
    TabPane {{
        width: 100%;
        height: 100%;
        background: {BG_DEEP};
        padding: 0;
    }}

    TabbedContent > .tabs {{
        background: {BG_PANEL};
        border-bottom: heavy {BORDER_COLOR};
    }}

    #chat-input {{
        dock: bottom;
        width: 100%;
        margin: 0 1 1 1;
        border: solid {BORDER_ACCENT};
        background: {BG_SURFACE};
        color: {FG_PRIMARY};
    }}
    #chat-input:focus {{
        border: solid {ACCENT};
    }}

    .status-bar {{
        dock: bottom;
        width: 100%;
        height: 1;
        background: {BG_SURFACE};
        color: {FG_DIM};
        border-top: solid {BORDER_COLOR};
        padding: 0 1;
        layer: status-bar;
    }}

    ScrollView > .scrollbar {{
        scrollbar-size: 1 0;
        scrollbar-color: rgb(51,51,102);
        scrollbar-color-hover: rgb(90,90,170);
        scrollbar-color-active: rgb(120,120,255);
        scrollbar-background: rgb(10,10,20);
    }}
    """

    BINDINGS = [
        Binding("ctrl+s", "save_config", "Save", show=True),
        Binding("ctrl+q", "quit_app", "Quit", show=True),
        Binding("tab", "next_tab", "Next Tab", show=False),
        Binding("shift+tab", "prev_tab", "Prev Tab", show=False),
        Binding("i", "focus_input", "Chat Input", show=True),
        Binding("escape", "blur_input", "Blur", show=False),
    ]

    config: reactive[Dict[str, Any]] = reactive({})
    dirty: reactive[bool] = reactive(False)
    mood: reactive[str] = reactive("idle")
    chat_messages: reactive[List[Dict]] = reactive(lambda: [])

    def __init__(self, engine: Optional[ChatEngine] = None):
        super().__init__()
        self._engine = engine
        self._engine_ready = False
        self._engine_error = ""
        self._last_streamed = ""

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Container(classes="sidebar"):
                yield Static(classes="sidebar-mascot", id="sidebar-mascot")
                with Vertical(classes="sidebar-info", id="sidebar-info"):
                    yield Static(id="info-title")
                    yield Static(id="info-status")
                    yield Static(id="info-mood")
                    yield Static(id="info-keys")

            with Container(classes="content-area"):
                with TabbedContent(initial="chat-tab", id="main-tabs"):
                    with TabPane("💬 Chat", id="chat-tab"):
                        yield ChatView(id="chat-view")
                        yield ChatInput(
                            placeholder="Type a message...",
                            id="chat-input",
                        )
                    with TabPane("⚙ Config", id="config-tab"):
                        pass
                    with TabPane("📊 Status", id="status-tab"):
                        pass
                    with TabPane("📖 Help", id="help-tab"):
                        pass

        yield Static(id="status-bar", classes="status-bar")

    def on_mount(self) -> None:
        self.config = load_config()

        if self._engine:
            if not self._engine.initialized:
                self._engine.initialize()
            self._engine_ready = self._engine.initialized
            self._engine_error = self._engine.init_error or ""

        self._update_sidebar()
        self._init_status_bar()
        self._populate_tabs()
        self._init_chat_greeting()
        self.set_interval(0.5, self._poll_engine)
        self.set_interval(60, self._update_status_bar)

    # ─── Sidebar ────────────────────────────────────────────────

    def _update_sidebar(self) -> None:
        mascot = self.query_one("#sidebar-mascot", Static)
        lines_html = [
            f'<span style="color:{color}">{line}</span>'
            for line, color in MASCOT_SMALL
        ]
        mascot.update("\n".join(lines_html))

        self.query_one("#info-title", Static).update(
            f"[bold {ACCENT}]  LingMeng[/]\n[dim {FG_DIM}]  terminal spirit[/]"
        )

        si = "●" if self._engine_ready else "✗"
        sc = SUCCESS if self._engine_ready else ERROR
        self.query_one("#info-status", Static).update(
            f"\n[{sc}]  {si} {'running' if self._engine_ready else 'error'}[/]"
        )

        face = MOOD_FACES.get(self.mood, MOOD_FACES["idle"])
        self.query_one("#info-mood", Static).update(
            f"\n[dim {FG_DIM}]  mood: {face}[/]"
        )

        self.query_one("#info-keys", Static).update(
            f"\n[dim {FG_DIM}]  ─── keys ───[/]\n"
            f"[dim {FG_DIM}]  Tab  | switch[/]\n"
            f"[dim {FG_DIM}]  i    | input[/]\n"
            f"[dim {FG_DIM}]  j/k  | scroll[/]\n"
            f"[dim {FG_DIM}]  q    | quit[/]"
        )

    # ─── Tabs ───────────────────────────────────────────────────

    def _populate_tabs(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)

        cpane = tabs.query_one("#config-tab", TabPane)
        cpane.mount(ConfigTreeWidget(self.config))

        spane = tabs.query_one("#status-tab", TabPane)
        spane.mount(
            StatusViewWidget(
                self.config,
                engine_initialized=self._engine_ready,
                engine_error=self._engine_error,
            )
        )

        hpane = tabs.query_one("#help-tab", TabPane)
        hpane.mount(HelpViewWidget())

    # ─── Chat ───────────────────────────────────────────────────

    def _init_chat_greeting(self) -> None:
        face = MOOD_FACES.get(self.mood, MOOD_FACES["idle"])
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_system_message(
            f"\n            {face}\n\n"
            "    Press i or Enter to start chatting\n"
            "    Tab to switch panels\n"
        )

    def on_chat_submitted(self, event: ChatSubmitted) -> None:
        if not event.text.strip():
            return
        self.mood = "excited"
        self._update_sidebar()

        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.clear_messages()
        self.chat_messages.append({"role": "user", "content": event.text})
        chat_view.add_user_message(event.text)

        if self._engine and self._engine_ready:
            self._engine.chat_stream(event.text)
        else:
            chat_view.add_system_message(
                "⚠ Engine not initialized. Check model configuration."
            )
        self._update_status_bar()

    # ─── Status bar ─────────────────────────────────────────────

    def _init_status_bar(self) -> None:
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        bar = self.query_one("#status-bar", Static)
        tabs = self.query_one("#main-tabs", TabbedContent)
        active = tabs.active or "chat-tab"

        hints = {
            "chat-tab": "[bold {a}]i[/]:input  [bold {a}]j/k[/]:scroll  [bold {a}]Ctrl+S[/]:save  [bold {a}]Tab[/]:switch  [bold {a}]Ctrl+Q[/]:quit",
            "config-tab": "[bold {a}]j/k[/]:navigate  [bold {a}]Enter[/]:edit  [bold {a}]Ctrl+S[/]:save  [bold {a}]Tab[/]:switch  [bold {a}]Ctrl+Q[/]:quit",
            "status-tab": "[bold {a}]j/k[/]:scroll  [bold {a}]r[/]:refresh  [bold {a}]Tab[/]:switch  [bold {a}]Ctrl+Q[/]:quit",
            "help-tab": "[bold {a}]j/k[/]:scroll  [bold {a}]Tab[/]:switch  [bold {a}]Ctrl+Q[/]:quit",
        }
        hint_raw = hints.get(active, "")
        hint = hint_raw.format(a=ACCENT)

        time_str = datetime.now().strftime("%H:%M:%S")
        dirty = " [bold yellow]*[/]" if self.dirty else ""

        spacer = " " * max(1, (self.size.width or 80) - 70)
        bar.update(f" {hint}[dim {FG_DIM}]{spacer}{dirty} {time_str} [/]")

    # ─── Polling ────────────────────────────────────────────────

    def _poll_engine(self) -> None:
        if not self._engine or not self._engine.generating:
            if self._last_streamed and not self._engine.generating:
                self.mood = "idle"
                self._update_sidebar()
                self._last_streamed = ""
            return

        text = self._engine.streaming_text
        if text and text != self._last_streamed:
            self._last_streamed = text
            chat_view = self.query_one("#chat-view", ChatView)
            chat_view.add_assistant_message(
                f"[dim {FG_DIM}]⏳ Generating...[/]\n[dim {FG_SECONDARY}]{text[:300]}[/]"
            )

    # ─── Actions ────────────────────────────────────────────────

    def action_save_config(self) -> None:
        if save_config(self.config):
            self.dirty = False
            self.notify("✓ Configuration saved", severity="information")
        else:
            self.notify("✗ Failed to save configuration", severity="error")
        self._update_status_bar()

    def action_quit_app(self) -> None:
        if self.dirty:
            self.notify(
                "Unsaved changes! Press Ctrl+Q again to force quit.",
                severity="warning",
            )
            self.dirty = False
        else:
            self.app.exit()

    def action_next_tab(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tab_ids = ["chat-tab", "config-tab", "status-tab", "help-tab"]
        try:
            idx = tab_ids.index(tabs.active)
            next_idx = (idx + 1) % len(tab_ids)
            tabs.active = tab_ids[next_idx]
        except (ValueError, IndexError):
            tabs.active = "chat-tab"
        self._update_status_bar()

    def action_prev_tab(self) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tab_ids = ["chat-tab", "config-tab", "status-tab", "help-tab"]
        try:
            idx = tab_ids.index(tabs.active)
            prev_idx = (idx - 1) % len(tab_ids)
            tabs.active = tab_ids[prev_idx]
        except (ValueError, IndexError):
            tabs.active = "help-tab"
        self._update_status_bar()

    def action_focus_input(self) -> None:
        try:
            inp = self.query_one("#chat-input", ChatInput)
            inp.focus()
        except Exception:
            pass

    def action_blur_input(self) -> None:
        try:
            inp = self.query_one("#chat-input", ChatInput)
            if inp.has_focus:
                self.set_focus(None)
        except Exception:
            pass

    # ─── Events ─────────────────────────────────────────────────

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._update_status_bar()
