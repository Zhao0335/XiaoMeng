"""Mascot widget — renders LingMeng ASCII art with mood support."""

from textual.widget import Widget
from textual.strip import Strip
from rich.style import Style
from rich.text import Text

from ..theme import (
    MASCOT_BODY,
    MASCOT_EYES,
    MASCOT_HAIR,
    MASCOT_HOOD,
    MASCOT_TAG,
)

MASCOT_FULL = [
    ("     .      *     .         .    ", MASCOT_TAG),
    ("  .    .       .   .    .        ", MASCOT_TAG),
    ("        ╱▲╲       ╱▲╲           ", MASCOT_BODY),
    ("       ╱    ╲   ╱    ╲          ", MASCOT_BODY),
    ("      ╱  ✦   ╲ ╱   ✦  ╲         ", MASCOT_HAIR),
    ("     ╱─────────╳─────────╲      ", MASCOT_BODY),
    ("    ╱   ◉     ││     ◉   ╲     ", MASCOT_EYES),
    ("   ╱    ╲_◡╲ ││ ╱◡_╱    ╲     ", MASCOT_BODY),
    ("  │         ╲││╱          │     ", MASCOT_BODY),
    ("  │    ◇     ╰╯    ▽      │     ", MASCOT_HAIR),
    ("  ╲   ╱╲           ╱╲    ╱      ", MASCOT_BODY),
    ("   ╲╱   ╲_________╱   ╲╱       ", MASCOT_BODY),
    ("    ┃  ┌───────────┐  ┃        ", MASCOT_HOOD),
    ("    ┃  │  ░░░░░░░  │  ┃        ", MASCOT_HOOD),
    ("    ┃  │  ░░░░░░░  │  ┃        ", MASCOT_HOOD),
    ("    ┗━━┷━━━━━━━━━━━┷━━┛        ", MASCOT_HOOD),
    ("                                 ", MASCOT_TAG),
    ("     xiaomeng  ·  terminal      ", MASCOT_TAG),
]

MASCOT_SMALL = [
    ("    ╱▲╲   ╱▲╲    ", MASCOT_BODY),
    ("   ╱ ◉ ╲╱ ◉ ╲   ", MASCOT_EYES),
    ("  │  ╲_◡╱  │    ", MASCOT_BODY),
    ("  ╲  ╱────╲  ╱    ", MASCOT_HOOD),
    ("   ┷━━━━━━━━┷    ", MASCOT_HOOD),
]

MASCOT_TINY = "(=◉ᆽ◉=)"

MOOD_MAP = {
    "idle": 0,
    "happy": 1,
    "thinking": 2,
    "excited": 3,
    "typing": 4,
    "processing": 5,
    "success": 6,
    "error": 7,
    "sleepy": 8,
    "sad": 9,
    "surprised": 10,
    "confused": 11,
}

MOOD_FACES = {
    "idle": "(=◉ᆽ◉=)",
    "happy": "(=◕‿◕=)",
    "thinking": "(=ↀ⍘ↀ=)",
    "excited": "(=✧▽✧=)",
    "typing": "(=ᵕ_ᵕ=)",
    "processing": "(=⏒﹏⏒=)",
    "success": "(=✿‿✿=)",
    "error": "(=⚆_⚆=)",
    "sleepy": "(=￣ρ￣=)",
    "sad": "(=；ω；=)",
    "surprised": "(=⊙⍘⊙=)",
    "confused": "(=ↀ⍘ↀ=)?",
}


class MascotWidget(Widget):
    """Displays LingMeng ASCII mascot with mood-based expressions."""

    DEFAULT_CSS = """
    MascotWidget {
        width: 100%;
        height: auto;
        content-align: center middle;
        padding: 1 0;
    }
    """

    mood: str = "idle"

    def __init__(self, mood: str = "idle", compact: bool = False):
        super().__init__()
        self.mood = mood
        self.compact = compact

    def set_mood(self, mood: str) -> None:
        self.mood = mood
        self.refresh()

    def render_line(self, y: int) -> Strip:
        lines = MASCOT_SMALL if self.compact else MASCOT_FULL
        if y < 0 or y >= len(lines):
            return Strip.blank(self.size.width if self.size else 80)

        text, color = lines[y]
        return Strip([(text, Style(color=color))])
