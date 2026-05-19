"""Config tree widget — interactive configuration editor."""

from typing import Any, Dict, List

from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from rich.text import Text
from rich.style import Style

from ..theme import TREE_NODE, TREE_LEAF, SUCCESS, WARNING, ERROR, ACCENT
from ..utils import is_sensitive, mask_value, truncate


class ConfigTreeWidget(Tree):
    """Interactive config tree with inline editing capabilities."""

    DEFAULT_CSS = """
    ConfigTreeWidget {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
        scrollbar-size-vertical: 1;
        scrollbar-color: rgb(51,51,102);
        scrollbar-color-hover: rgb(90,90,170);
        scrollbar-color-active: rgb(120,120,255);
        scrollbar-background: rgb(10,10,20);
        scrollbar-background-hover: rgb(10,10,20);
        scrollbar-background-active: rgb(10,10,20);
    }
    ConfigTreeWidget > .tree--guides {
        color: rgb(40,40,80);
    }
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("📋 Configuration")
        self._config = config
        self._build_tree()
        self.show_root = True
        self.show_guides = True
        self.guide_depth = 4
        self.auto_expand = True
        self.root.expand()

    def _build_tree(self) -> None:
        self.root.remove_children()
        self._add_node(self.root, self._config, "")

    def _add_node(
        self, parent: TreeNode, data: Any, prefix: str = "", key: str = ""
    ) -> None:
        if isinstance(data, dict):
            for k, v in sorted(data.items()):
                full_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    node = parent.add(
                        f"📁 {k}",
                        data={"kind": "node", "key": k, "full_key": full_key, "value": v},
                    )
                    self._add_node(node, v, full_key, k)
                elif isinstance(v, list):
                    if v and isinstance(v[0], dict):
                        label = f"📋 {k} [{len(v)} models]"
                    else:
                        items_preview = ", ".join(
                            str(x)[:20] for x in v[:3]
                        )
                        label = f"📋 {k} [{len(v)}]: {items_preview}"
                    parent.add_leaf(
                        label,
                        data={"kind": "list", "key": k, "full_key": full_key, "value": v},
                    )
                else:
                    self._add_leaf_node(parent, k, full_key, v)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._add_node(parent, item, f"{prefix}[{i}]", f"[{i}]")

    def _add_leaf_node(
        self, parent: TreeNode, key: str, full_key: str, value: Any
    ) -> None:
        if is_sensitive(key):
            display = f"🔒 {key}: {mask_value(str(value))}"
        elif isinstance(value, bool):
            icon = "✅" if value else "❌"
            display = f"{icon} {key}"
        elif isinstance(value, (int, float)):
            display = f"🔢 {key}: {value}"
        elif value is None:
            display = f"○ {key}: null"
        else:
            display = f"📝 {key}: {truncate(str(value), 40)}"

        parent.add_leaf(
            display,
            data={"kind": "leaf", "key": key, "full_key": full_key, "value": value},
        )

    def rebuild(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._build_tree()
        self.root.expand()
