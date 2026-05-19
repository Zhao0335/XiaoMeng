"""Status view widget — system and model status dashboard."""

from typing import Any, Dict

from textual.widgets import Static
from rich.text import Text
from rich.style import Style
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from datetime import datetime

from ..theme import SUCCESS, ERROR, WARNING, INFO, ACCENT, FG_PRIMARY, FG_DIM
from ..utils import CONFIG_PATH

_console = Console()


class StatusViewWidget(Static):
    """System status dashboard showing runtime information."""

    DEFAULT_CSS = """
    StatusViewWidget {
        width: 100%;
        height: 1fr;
        padding: 0 2;
    }
    """

    def __init__(self, config: dict, engine_initialized: bool, engine_error: str = ""):
        super().__init__(self._build_content(config, engine_initialized, engine_error))
        self._config = config
        self._engine_initialized = engine_initialized
        self._engine_error = engine_error

    @staticmethod
    def _build_content(config: dict, initialized: bool, error: str) -> str:
        parts: list[str] = []

        # System panel
        sys_table = Table(
            title="🖥  System",
            style=Style(color=FG_PRIMARY),
            title_style=Style(color=ACCENT, bold=True),
            border_style=Style(color=FG_DIM),
            show_header=False,
            expand=True,
        )
        sys_table.add_column("Key", style=Style(color=FG_DIM), width=12)
        sys_table.add_column("Value", style=Style(color=FG_PRIMARY))
        sys_table.add_row("Time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        sys_table.add_row("Config", CONFIG_PATH.name)
        sys_table.add_row("Modified", "no")
        parts.append(_render_panel(sys_table))

        # Models panel
        model_table = Table(
            title="🤖 Models",
            style=Style(color=FG_PRIMARY),
            title_style=Style(color=ACCENT, bold=True),
            border_style=Style(color=FG_DIM),
            show_header=True,
            expand=True,
        )
        model_table.add_column("Status", width=8)
        model_table.add_column("Model ID", width=20)
        model_table.add_column("Layer", width=8)
        model_table.add_column("Role", width=12)
        model_table.add_column("Endpoint", width=30)

        for m in config.get("models", []):
            status = "[bold green]●[/]" if m.get("enabled") else "[bold red]○[/]"
            model_table.add_row(
                status,
                m.get("model_id", "?"),
                m.get("layer", "?"),
                m.get("role", "?"),
                (m.get("endpoint", "") or "")[:30],
            )
        parts.append(_render_panel(model_table))

        # Engine panel
        if initialized:
            eng_text = "[bold green]●[/] Engine: initialized"
        else:
            eng_text = f"[bold red]✗[/] Engine: error - {error}"
        parts.append(_render_panel(eng_text, title="⚙ Engine"))

        return "\n\n".join(parts)

    def refresh_status(self, config: dict, initialized: bool, error: str = "") -> None:
        self._config = config
        self._engine_initialized = initialized
        self._engine_error = error
        self.update(self._build_content(config, initialized, error))


def _render_panel(renderable, title: str = "", **kwargs) -> str:
    segments = _console.render(Panel(renderable, title=title, **kwargs))
    return "\n".join(seg.text for seg in segments)
