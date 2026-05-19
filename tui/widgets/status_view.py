"""Status view widget — system and model status dashboard."""

from textual.containers import VerticalScroll
from textual.widgets import Static
from rich.text import Text
from rich.style import Style
from rich.panel import Panel
from rich.table import Table
from datetime import datetime

from ..theme import SUCCESS, ERROR, WARNING, INFO, ACCENT, FG_PRIMARY, FG_DIM
from ..utils import CONFIG_PATH


class StatusViewWidget(VerticalScroll):
    """System status dashboard showing runtime information."""

    DEFAULT_CSS = """
    StatusViewWidget {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    StatusViewWidget Static {
        width: 100%;
        padding: 1 0;
    }
    """

    def __init__(self, config: dict, engine_initialized: bool, engine_error: str = ""):
        super().__init__()
        self._config = config
        self._engine_initialized = engine_initialized
        self._engine_error = engine_error

    def on_mount(self) -> None:
        self._render_status()

    def _render_status(self) -> None:
        self.remove_children()

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
        sys_table.add_row(
            "Modified",
            "[bold yellow]yes[/]" if self._config.get("_dirty") else "no",
        )
        self.mount(Static(Panel(sys_table, border_style=Style(color=FG_DIM))))

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

        for m in self._config.get("models", []):
            status = "[bold green]●[/]" if m.get("enabled") else "[bold red]○[/]"
            model_table.add_row(
                status,
                m.get("model_id", "?"),
                m.get("layer", "?"),
                m.get("role", "?"),
                m.get("endpoint", "")[:30],
            )

        self.mount(Static(Panel(model_table, border_style=Style(color=FG_DIM))))

        # Engine panel
        eng_text = Text()
        if self._engine_initialized:
            eng_text.append("● Engine: initialized\n", Style(color=SUCCESS, bold=True))
        else:
            eng_text.append(
                f"✗ Engine: error - {self._engine_error}\n",
                Style(color=ERROR, bold=True),
            )
        self.mount(
            Static(
                Panel(
                    eng_text,
                    title="⚙ Engine",
                    title_align="left",
                    border_style=Style(color=FG_DIM),
                )
            )
        )

    def refresh_status(self, config: dict, initialized: bool, error: str = "") -> None:
        self._config = config
        self._engine_initialized = initialized
        self._engine_error = error
        self._render_status()
