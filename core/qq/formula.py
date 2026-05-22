"""
LaTeX 公式渲染 + 发图模块

渲染策略（两级 fallback）：
  Stage 1 — matplotlib usetex=True（系统 LaTeX + dvipng）
            支持完整 LaTeX 语法，含 \begin{pmatrix} 等环境
  Stage 2 — matplotlib mathtext（内置，无需系统 LaTeX）
            支持大多数常见公式，但不支持 \begin 环境

- latex_to_png():            同步渲染（在线程池中调用）
- send_formulas_from_text(): 异步提取 + 渲染 + 发送所有公式图片
- strip_formula_markers():   把 $$...$$ 替换为占位符
"""

import asyncio
import base64
import hashlib
import logging
import re
import shutil
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_FORMULA_RE = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)

# 检测系统 LaTeX 是否可用（启动时一次性检测）
_USETEX_AVAILABLE: Optional[bool] = None

def _check_usetex() -> bool:
    global _USETEX_AVAILABLE
    if _USETEX_AVAILABLE is None:
        _USETEX_AVAILABLE = bool(shutil.which("latex") and shutil.which("dvipng"))
    return _USETEX_AVAILABLE


# ─────────────────────────────────────────────
# 缓存目录
# ─────────────────────────────────────────────

def init_cache_dir(data_dir: str) -> Path:
    """在 data_dir/formula_cache 下创建缓存目录并返回路径"""
    cache = Path(data_dir) / "formula_cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _clean_old_cache(cache_dir: Path, max_age: int = 3600) -> None:
    """删除超过 max_age 秒的旧缓存文件"""
    now = time.time()
    for f in cache_dir.glob("formula_*.png"):
        try:
            if now - f.stat().st_mtime > max_age:
                f.unlink()
        except Exception:
            pass


# ─────────────────────────────────────────────
# 渲染（内部）
# ─────────────────────────────────────────────

def _render_usetex(latex_str: str, out: Path) -> bool:
    """Stage 1：用系统 LaTeX 渲染，支持完整 LaTeX 环境语法"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "text.usetex": True,
        "text.latex.preamble": r"\usepackage{amsmath}\usepackage{amssymb}",
        "font.family": "serif",
    })

    fig = plt.figure(figsize=(7, 2.2))
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_facecolor("none")

    # \begin{...} 环境必须在 display math \[...\] 中才合法（aligned/cases/pmatrix等）
    # 普通公式用 $\displaystyle ...$ 确保大号展示样式
    if r"\begin{" in latex_str:
        wrapped = f"\\[\n{latex_str}\n\\]"
    else:
        wrapped = f"$\\displaystyle {latex_str}$"

    ax.text(
        0.5, 0.5,
        wrapped,
        ha="center", va="center",
        fontsize=20, color="black",
        transform=ax.transAxes,
    )

    fig.savefig(str(out), dpi=300, transparent=True, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)

    # 关闭 usetex，避免影响后续 mathtext 渲染
    plt.rcParams["text.usetex"] = False
    return True


def _render_mathtext(latex_str: str, out: Path) -> bool:
    """Stage 2：用 matplotlib mathtext 渲染，无需系统 LaTeX"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    plt.rcParams["text.usetex"] = False
    available = {f.name for f in fm.fontManager.ttflist}
    plt.rcParams["font.family"] = "CMU Serif" if "CMU Serif" in available else "DejaVu Serif"

    fig = plt.figure(figsize=(7, 1.8))
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_facecolor("none")

    ax.text(
        0.5, 0.5,
        f"${latex_str}$",
        ha="center", va="center",
        fontsize=22, color="black",
        transform=ax.transAxes,
    )

    fig.savefig(str(out), dpi=300, transparent=True, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return True


# ─────────────────────────────────────────────
# 公共渲染接口
# ─────────────────────────────────────────────

def latex_to_png(latex_str: str, cache_dir: Path) -> Optional[str]:
    """
    渲染 LaTeX 公式为透明背景 PNG（300 DPI）。
    优先使用系统 LaTeX（支持完整语法），失败后降级到 mathtext。
    相同公式命中缓存直接返回。

    同步函数，应在线程池（run_in_executor）中调用。
    """
    h = hashlib.md5(latex_str.encode()).hexdigest()[:16]
    out = cache_dir / f"formula_{h}.png"
    if out.exists():
        return str(out)

    _clean_old_cache(cache_dir)

    # Stage 1：usetex
    if _check_usetex():
        try:
            _render_usetex(latex_str, out)
            logger.debug(f"usetex 渲染完成: {out.name}")
            return str(out)
        except Exception as e:
            logger.debug(f"usetex 渲染失败，降级 mathtext: {e}")
            try:
                import matplotlib.pyplot as plt
                plt.rcParams["text.usetex"] = False
                plt.close("all")
            except Exception:
                pass
            out.unlink(missing_ok=True)

    # Stage 2：mathtext
    try:
        _render_mathtext(latex_str, out)
        logger.debug(f"mathtext 渲染完成: {out.name}")
        return str(out)
    except Exception as e:
        logger.error(f"公式渲染失败 {latex_str!r}: {e}")
        try:
            import matplotlib.pyplot as plt
            plt.close("all")
        except Exception:
            pass
        out.unlink(missing_ok=True)
        return None


# ─────────────────────────────────────────────
# 文本处理
# ─────────────────────────────────────────────

def extract_formulas(text: str) -> List[str]:
    """提取文本中所有 $$...$$ 包裹的公式字符串"""
    return _FORMULA_RE.findall(text)


def strip_formula_markers(text: str) -> str:
    """将 $$...$$ 替换为 [见下方公式图] 提示，保留其余文字"""
    return _FORMULA_RE.sub("[见下方公式图]", text).strip()


# ─────────────────────────────────────────────
# 发送
# ─────────────────────────────────────────────

async def send_formulas_from_text(
    text: str,
    napcat,
    is_group: bool,
    target_id: int,
    cache_dir: Path,
) -> None:
    """
    从 text 中提取所有 $$...$$ 公式，依次渲染并通过 NapCat 发送为图片消息。
    渲染在线程池中执行，不阻塞事件循环。
    """
    formulas = extract_formulas(text)
    if not formulas:
        return

    loop = asyncio.get_event_loop()

    for formula in formulas:
        formula = formula.strip()
        if not formula:
            continue

        img_path = await loop.run_in_executor(None, latex_to_png, formula, cache_dir)
        if img_path is None:
            logger.warning(f"公式渲染失败，跳过: {formula[:40]!r}")
            continue

        try:
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            # OneBot v11 CQ 码格式发送 base64 图片
            cq = f"[CQ:image,file=base64://{b64}]"
            if is_group:
                await napcat.send_group_msg(target_id, cq)
            else:
                await napcat.send_private_msg(target_id, cq)
            logger.info(f"公式图片已发送 ({'群' if is_group else '私聊'} {target_id})")
        except Exception as e:
            logger.error(f"发送公式图片失败: {e}")
