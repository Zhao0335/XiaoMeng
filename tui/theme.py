"""Design tokens and color system for LingMeng TUI.

A carefully crafted dark cyber-fantasy theme inspired by
modern terminal aesthetics with warm accent colors.
"""

from rich.color import Color
from rich.style import Style

# Primary palette
CYBER_PURPLE = "#c0a0ff"
CYBER_PINK = "#ff87af"
CYBER_CYAN = "#87d7ff"
CYBER_GREEN = "#87ffaf"
CYBER_YELLOW = "#ffd787"
CYBER_ORANGE = "#ffaf5f"
CYBER_RED = "#ff8787"

# Neutral palette
BG_DEEP = "#0a0a14"
BG_PANEL = "#12122a"
BG_SURFACE = "#1a1a3e"
BG_HOVER = "#222255"

FG_PRIMARY = "#e0e0f0"
FG_SECONDARY = "#8888aa"
FG_DIM = "#555577"
FG_MUTED = "#333355"

BORDER_COLOR = "#2a2a55"
BORDER_ACTIVE = "#5a5aaa"
BORDER_ACCENT = "#7a7aff"

# Semantic colors
ACCENT = "#b8a0ff"
SUCCESS = "#5fd7af"
WARNING = "#ffaf5f"
ERROR = "#ff5f87"
INFO = "#5fafff"

# Mascot colors
MASCOT_BODY = "#e0c0a0"
MASCOT_EYES = "#5fffaf"
MASCOT_HAIR = "#c0d0ff"
MASCOT_HOOD = "#f0f0ff"
MASCOT_TAG = "#b8a0ff"

# Bubble colors
BUBBLE_USER_BG = "#2a2a55"
BUBBLE_USER_FG = "#c0d0ff"
BUBBLE_ASST_BG = "#1a2a2a"
BUBBLE_ASST_FG = "#c0e0d0"
BUBBLE_SYS_BG = "#1a1a2a"
BUBBLE_SYS_FG = "#8888aa"

# Tab colors
TAB_ACTIVE_FG = "#c0d0ff"
TAB_ACTIVE_BG = "#1a1a3e"
TAB_INACTIVE_FG = "#555577"
TAB_INACTIVE_BG = ""

# Splash colors
SPLASH_TITLE = "#c0d0ff"
SPLASH_SUB = "#e0e0f0"
SPLASH_DIM = "#555577"
SPLASH_ACCENT = "#b8a0ff"

# Tree colors
TREE_NODE = "#c0d0ff"
TREE_LEAF = "#e0e0f0"

# Scrollbar
SCROLLBAR_TRACK = "#12122a"
SCROLLBAR_THUMB = "#333366"

# Progress bar
PROGRESS_BG = "#1a1a3e"
PROGRESS_FILL = "#b8a0ff"

# Chart / data colors
DATA_COLORS = [CYBER_PURPLE, CYBER_CYAN, CYBER_GREEN, CYBER_YELLOW, CYBER_PINK, CYBER_ORANGE]


def style_splash_title() -> Style:
    return Style(color=SPLASH_TITLE, bold=True)


def style_splash_sub() -> Style:
    return Style(color=SPLASH_SUB)


def style_splash_dim() -> Style:
    return Style(color=SPLASH_DIM)


def style_splash_accent() -> Style:
    return Style(color=SPLASH_ACCENT)
