"""Help view widget — keyboard shortcuts and about info."""

from textual.containers import VerticalScroll
from textual.widgets import Static
from rich.text import Text
from rich.style import Style
from rich.panel import Panel
from rich.table import Table

from ..theme import ACCENT, SUCCESS, FG_PRIMARY, FG_DIM, FG_SECONDARY


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


class HelpViewWidget(VerticalScroll):
    """Keyboard shortcuts and about panel."""

    DEFAULT_CSS = """
    HelpViewWidget {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    HelpViewWidget Static {
        width: 100%;
        padding: 1 0;
    }
    """

    def on_mount(self) -> None:
        self._render()

    def _render(self) -> None:
        self.remove_children()

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

            self.mount(
                Static(
                    Panel(
                        table,
                        title=section,
                        title_align="left",
                        border_style=Style(color=FG_DIM),
                    )
                )
            )

        about = Text()
        about.append("LingMeng OS v3.0\n", Style(color=ACCENT, bold=True))
        about.append("terminal companion\n", Style(color=FG_PRIMARY))
        about.append("\n")
        about.append("AI maid spirit living inside your shell.\n", Style(color=FG_DIM))
        about.append(
            "Gentle, loyal, adorable — powered by Textual.\n",
            Style(color=FG_DIM),
        )

        self.mount(
            Static(
                Panel(
                    about,
                    title="💜 About",
                    title_align="left",
                    border_style=Style(color=FG_DIM),
                )
            )
        )
