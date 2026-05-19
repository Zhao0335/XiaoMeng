"""Config tree widget — interactive configuration editor.

Single Static with pre-rendered Rich Text — zero child mounting,
zero timing issues.
"""

from typing import Any, Dict

from textual.widgets import Static
from rich.text import Text
from rich.style import Style

from ..theme import ACCENT, SUCCESS, ERROR, FG_PRIMARY, FG_SECONDARY, FG_DIM
from ..utils import is_sensitive, mask_value, truncate


class ConfigTreeWidget(Static):
    """Config display as an indented, scrollable list of key-value pairs."""

    DEFAULT_CSS = """
    ConfigTreeWidget {
        width: 100%;
        height: 1fr;
        padding: 0 2;
    }
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(self._build_text(config))
        self._config = config

    @staticmethod
    def _build_text(config: Dict[str, Any]) -> Text:
        lines: list[tuple[str, str | Style]] = []
        ConfigTreeWidget._walk(config, lines, depth=0)
        text = Text()
        for i, (content, style) in enumerate(lines):
            if i > 0:
                text.append("\n")
            if isinstance(style, str):
                text.append(content, style=Style(color=style))
            else:
                text.append(content, style=style)
        return text

    @staticmethod
    def _walk(data: Any, lines: list, depth: int = 0) -> None:
        if not isinstance(data, dict):
            return
        indent = "  " * depth
        for k, v in sorted(data.items()):
            if isinstance(v, dict):
                lines.append((f"{indent}▸ {k}", Style(color=ACCENT, bold=True)))
                ConfigTreeWidget._walk(v, lines, depth + 1)
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    label = f"{indent}  📋 {k} [{len(v)} models]"
                else:
                    preview = ", ".join(str(x)[:15] for x in v[:3])
                    label = f"{indent}  📋 {k} [{len(v)}]: {preview}"
                lines.append((label, FG_SECONDARY))
            else:
                ConfigTreeWidget._leaf(lines, indent, k, v)

    @staticmethod
    def _leaf(lines: list, indent: str, key: str, value: Any) -> None:
        if is_sensitive(key):
            display = f"{indent}  🔒 {key}: {mask_value(str(value))}"
            color = ERROR
        elif isinstance(value, bool):
            icon = "✅" if value else "❌"
            display = f"{indent}  {icon} {key}"
            color = FG_PRIMARY
        elif isinstance(value, int):
            display = f"{indent}  🔢 {key}: {value}"
            color = SUCCESS
        elif value is None:
            display = f"{indent}  ○ {key}: null"
            color = FG_DIM
        else:
            display = f"{indent}  📝 {key}: {truncate(str(value), 50)}"
            color = FG_PRIMARY
        lines.append((display, color))

    def rebuild(self, config: Dict[str, Any]) -> None:
        self._config = config
        self.update(self._build_text(config))
