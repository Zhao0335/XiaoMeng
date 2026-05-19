"""Help view widget — keyboard shortcuts and about info."""

from textual.widgets import Static
from rich.style import Style
from rich.panel import Panel
from rich.table import Table
from rich.console import Console

from ..theme import ACCENT, SUCCESS, FG_PRIMARY, FG_DIM

_console = Console()

HELP_SECTIONS = {
    "🌐 Global": [
        ("Tab", "Switch between panels"),
        ("Ctrl+C / q", "Quit application"),
        ("Ctrl+S", "Save configuration"),
    ],
    "💬 Chat": [
        ("i / Enter", "Start input mode"),
        ("Esc", "Cancel input"),
        ("j / ↓", "Scroll down"),
        ("k / ↑", "Scroll up"),
        ("PgDn", "Page down"),
        ("PgUp", "Page up"),
    ],
    "⚙ Config": [
        ("j / ↓", "Move cursor down"),
        ("k / ↑", "Move cursor up"),
        ("Enter", "Expand node / Edit leaf"),
        ("Space", "Toggle boolean"),
    ],
    "📊 Status": [
        ("j / ↓", "Scroll down"),
        ("k / ↑", "Scroll up"),
        ("r", "Refresh"),
    ],
}


class HelpViewWidget(Static):
    """Keyboard shortcuts and about panel."""

    DEFAULT_CSS = """
    HelpViewWidget {
        width: 100%;
        height: 1fr;
        padding: 0 2;
    }
    """

    def __init__(self):
        super().__init__(self._build_content())

    @staticmethod
    def _build_content() -> str:
        parts: list[str] = []

        for section, shortcuts in HELP_SECTIONS.items():
            table = Table(
                show_header=False,
                expand=True,
                border_style=Style(color=FG_DIM),
                padding=(0, 1),
            )
            table.add_column("Key", style=Style(color=SUCCESS, bold=True), width=14)
            table.add_column("Action", style=Style(color=FG_PRIMARY))

            for key, action in shortcuts:
                table.add_row(key, action)

            parts.append(_render_panel(table, title=section))

        about = (
            "[bold #b8a0ff]LingMeng OS v3.0[/]\n"
            "terminal companion\n"
            "\n"
            "[dim]AI maid spirit living inside your shell.[/]\n"
            "[dim]Gentle, loyal, adorable — powered by Textual.[/]"
        )
        parts.append(_render_panel(about, title="💜 About"))

        return "\n\n".join(parts)


def _render_panel(renderable, title: str = "", **kwargs) -> str:
    segments = _console.render(Panel(renderable, title=title, **kwargs))
    return "\n".join(seg.text for seg in segments)
