"""
Bilibili Plugin — B站自主浏览与互动

提供完整的 B 站操作工具，支持有账号和无账号两种模式。
凭据存储在同目录下的 credentials.json：
{
  "SESSDATA": "...",
  "bili_jct": "...",
  "buvid3": "..."
}
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from core.plugins.base import PluginBase, PluginMetadata, ToolDefinition

_CRED_FILE = Path(__file__).parent / "credentials.json"


def _load_credential() -> Optional[Dict]:
    if not _CRED_FILE.exists():
        return None
    try:
        return json.loads(_CRED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _make_credential():
    """构造 bilibili_api Credential 对象，无凭据返回 None。"""
    try:
        from bilibili_api import Credential
        cred = _load_credential()
        if cred and cred.get("SESSDATA"):
            return Credential(
                sessdata=cred.get("SESSDATA", ""),
                bili_jct=cred.get("bili_jct", ""),
                buvid3=cred.get("buvid3", ""),
            )
    except Exception:
        pass
    return None


async def _run(coro):
    """运行 bilibili_api 协程（统一错误处理）。"""
    try:
        return await coro
    except Exception as e:
        return None, str(e)


def _fmt_video(v: dict) -> str:
    title = v.get("title") or v.get("bvid", "")
    author = v.get("owner", {}).get("name") if isinstance(v.get("owner"), dict) else v.get("author", "")
    stat = v.get("stat") or {}
    play = stat.get("view", 0)
    bvid = v.get("bvid", "")
    dur = v.get("duration", 0)
    minutes, secs = divmod(int(dur), 60)
    return (
        f"📹 {title}\n"
        f"   UP: {author}  播放: {_fmt_num(play)}  时长: {minutes}:{secs:02d}\n"
        f"   BV: {bvid}  https://www.bilibili.com/video/{bvid}"
    )


def _fmt_num(n: int) -> str:
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


class BilibiliPlugin(PluginBase):
    """B站自主浏览与互动插件"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="bilibili",
            version="1.0.0",
            description="B站自主浏览、搜索、评论、互动",
            author="XiaoMeng Project",
            tags=["video", "social", "entertainment"],
        )

    async def on_initialize(self) -> bool:
        try:
            import bilibili_api  # noqa: F401
        except ImportError:
            return False

        cred_ok = _load_credential() is not None
        auth_note = "（已配置账号）" if cred_ok else "（游客模式）"

        self.register_tool(ToolDefinition(
            name="bilibili_hot",
            description=f"获取 B 站今日全站热门视频 top10{auth_note}",
            parameters={"type": "object", "properties": {
                "limit": {"type": "integer", "description": "返回数量，默认10，最多20"}
            }, "required": []},
            min_user_level=0,
            progress_msg="（小萌在刷 B 站热门~）",
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_search",
            description="搜索 B 站内容（视频/用户/番剧/文章等）",
            parameters={"type": "object", "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "search_type": {"type": "string", "description": "搜索类型：video（默认）/user/bangumi/article", "default": "video"},
                "limit": {"type": "integer", "description": "返回数量，默认5"}
            }, "required": ["query"]},
            min_user_level=0,
            progress_msg="（小萌在搜 B 站~）",
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_video_info",
            description="获取 B 站视频详情（标题、简介、数据、热评）",
            parameters={"type": "object", "properties": {
                "bvid": {"type": "string", "description": "视频的 BV 号，如 BV1xx411c7mD"}
            }, "required": ["bvid"]},
            min_user_level=0,
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_get_comments",
            description="获取 B 站视频的热门评论",
            parameters={"type": "object", "properties": {
                "bvid": {"type": "string", "description": "视频 BV 号"},
                "limit": {"type": "integer", "description": "返回数量，默认10"}
            }, "required": ["bvid"]},
            min_user_level=0,
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_post_comment",
            description="在 B 站视频下发表评论",
            parameters={"type": "object", "properties": {
                "bvid": {"type": "string", "description": "视频 BV 号"},
                "content": {"type": "string", "description": "评论内容，要真诚友善"}
            }, "required": ["bvid", "content"]},
            min_user_level=0,
            progress_msg="（小萌在发评论~）",
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_like_video",
            description="给 B 站视频点赞",
            parameters={"type": "object", "properties": {
                "bvid": {"type": "string", "description": "视频 BV 号"}
            }, "required": ["bvid"]},
            min_user_level=0,
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_coin_video",
            description="给 B 站视频投币",
            parameters={"type": "object", "properties": {
                "bvid": {"type": "string", "description": "视频 BV 号"},
                "count": {"type": "integer", "description": "投币数量（1或2）", "default": 1}
            }, "required": ["bvid"]},
            min_user_level=0,
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_favorite",
            description="收藏 B 站视频",
            parameters={"type": "object", "properties": {
                "bvid": {"type": "string", "description": "视频 BV 号"}
            }, "required": ["bvid"]},
            min_user_level=0,
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_follow_user",
            description="关注 B 站 UP 主",
            parameters={"type": "object", "properties": {
                "uid": {"type": "integer", "description": "UP 主的 uid"}
            }, "required": ["uid"]},
            min_user_level=0,
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_get_feed",
            description="获取关注的 UP 主最新投稿动态（需要账号）",
            parameters={"type": "object", "properties": {
                "limit": {"type": "integer", "description": "返回条数，默认10"}
            }, "required": []},
            min_user_level=0,
            progress_msg="（小萌在看关注动态~）",
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_get_zone",
            description="浏览 B 站特定分区的最新/热门视频",
            parameters={"type": "object", "properties": {
                "zone": {"type": "string", "description": "分区名，如：动画、音乐、游戏、生活、科技、娱乐、影视"},
                "limit": {"type": "integer", "description": "返回数量，默认8"}
            }, "required": ["zone"]},
            min_user_level=0,
            progress_msg="（小萌在逛分区~）",
        ))
        self.register_tool(ToolDefinition(
            name="bilibili_get_recommend",
            description="获取 B 站为小萌个性化推荐的视频（需要账号）",
            parameters={"type": "object", "properties": {
                "limit": {"type": "integer", "description": "返回数量，默认10"}
            }, "required": []},
            min_user_level=0,
            progress_msg="（小萌在看 B 站推荐~）",
        ))
        return True

    async def on_shutdown(self) -> None:
        pass

    async def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> str:
        credential = _make_credential()
        if tool_name == "bilibili_hot":
            return await self._hot(int(arguments.get("limit", 10)))
        elif tool_name == "bilibili_search":
            return await self._search(
                arguments.get("query", ""),
                arguments.get("search_type", "video"),
                int(arguments.get("limit", 5)),
            )
        elif tool_name == "bilibili_video_info":
            return await self._video_info(arguments.get("bvid", ""), credential)
        elif tool_name == "bilibili_get_comments":
            return await self._get_comments(arguments.get("bvid", ""), int(arguments.get("limit", 10)))
        elif tool_name == "bilibili_post_comment":
            return await self._post_comment(arguments.get("bvid", ""), arguments.get("content", ""), credential)
        elif tool_name == "bilibili_like_video":
            return await self._like(arguments.get("bvid", ""), credential)
        elif tool_name == "bilibili_coin_video":
            return await self._coin(arguments.get("bvid", ""), int(arguments.get("count", 1)), credential)
        elif tool_name == "bilibili_favorite":
            return await self._favorite(arguments.get("bvid", ""), credential)
        elif tool_name == "bilibili_follow_user":
            return await self._follow(int(arguments.get("uid", 0)), credential)
        elif tool_name == "bilibili_get_feed":
            return await self._get_feed(int(arguments.get("limit", 10)), credential)
        elif tool_name == "bilibili_get_zone":
            return await self._get_zone(arguments.get("zone", ""), int(arguments.get("limit", 8)))
        elif tool_name == "bilibili_get_recommend":
            return await self._get_recommend(int(arguments.get("limit", 10)), credential)
        return f"未知 bilibili 工具: {tool_name}"

    # ── 实现 ─────────────────────────────────────────────

    async def _hot(self, limit: int = 10) -> str:
        try:
            from bilibili_api import hot
            data = await hot.get_hot_videos()
            videos = data.get("list", [])[:min(limit, 20)]
            if not videos:
                return "今天热门列表好像是空的……"
            lines = [f"🔥 B站今日热门 Top{len(videos)}：\n"]
            for i, v in enumerate(videos, 1):
                lines.append(f"{i}. {_fmt_video(v)}")
            return "\n".join(lines)
        except Exception as e:
            return f"获取热门失败: {e}"

    async def _search(self, query: str, search_type: str = "video", limit: int = 5) -> str:
        if not query:
            return "搜索词不能为空"
        try:
            from bilibili_api import search
            type_map = {
                "video": search.SearchObjectType.VIDEO,
                "user": search.SearchObjectType.USER,
                "bangumi": search.SearchObjectType.BANGUMI,
                "article": search.SearchObjectType.ARTICLE,
            }
            stype = type_map.get(search_type, search.SearchObjectType.VIDEO)
            data = await search.search_by_type(query, search_type=stype, page=1)
            results = data.get("result", [])[:min(limit, 10)]
            if not results:
                return f"没找到关于「{query}」的{search_type}内容"
            lines = [f"🔍 B站搜索「{query}」结果：\n"]
            for i, r in enumerate(results, 1):
                if search_type == "video":
                    title = r.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
                    author = r.get("author", "")
                    bvid = r.get("bvid", "")
                    play = _fmt_num(r.get("play", 0))
                    lines.append(f"{i}. 📹 {title}\n   UP: {author}  播放: {play}\n   https://www.bilibili.com/video/{bvid}")
                elif search_type == "user":
                    name = r.get("uname", "")
                    uid = r.get("mid", 0)
                    fans = _fmt_num(r.get("fans", 0))
                    lines.append(f"{i}. 👤 {name}  粉丝: {fans}  UID: {uid}")
                else:
                    lines.append(f"{i}. {r.get('title', str(r))}")
            return "\n".join(lines)
        except Exception as e:
            return f"搜索失败: {e}"

    async def _video_info(self, bvid: str, credential=None) -> str:
        if not bvid:
            return "需要提供 BV 号"
        try:
            from bilibili_api import video
            v = video.Video(bvid=bvid, credential=credential)
            info = await v.get_info()
            stat = info.get("stat", {})
            owner = info.get("owner", {})
            lines = [
                f"📹 {info.get('title', '')}",
                f"UP主: {owner.get('name', '')}  (UID: {owner.get('mid', '')})",
                f"播放: {_fmt_num(stat.get('view', 0))}  点赞: {_fmt_num(stat.get('like', 0))}  硬币: {_fmt_num(stat.get('coin', 0))}  收藏: {_fmt_num(stat.get('favorite', 0))}  弹幕: {_fmt_num(stat.get('danmaku', 0))}",
                f"简介: {info.get('desc', '（无）')[:200]}",
                f"链接: https://www.bilibili.com/video/{bvid}",
            ]
            # 热评
            try:
                comments_data = await v.get_comments(1)
                replies = (comments_data.get("replies") or [])[:5]
                if replies:
                    lines.append("\n💬 热门评论：")
                    for c in replies:
                        uname = c.get("member", {}).get("uname", "")
                        content = c.get("content", {}).get("message", "")[:100]
                        like = c.get("like", 0)
                        lines.append(f"  [{like}👍] {uname}: {content}")
            except Exception:
                pass
            return "\n".join(lines)
        except Exception as e:
            return f"获取视频信息失败: {e}"

    async def _get_comments(self, bvid: str, limit: int = 10) -> str:
        if not bvid:
            return "需要提供 BV 号"
        try:
            from bilibili_api import video
            v = video.Video(bvid=bvid)
            data = await v.get_comments(1)
            replies = (data.get("replies") or [])[:min(limit, 20)]
            if not replies:
                return "暂无评论"
            lines = [f"💬 {bvid} 的热门评论：\n"]
            for c in replies:
                uname = c.get("member", {}).get("uname", "")
                content = c.get("content", {}).get("message", "")[:150]
                like = c.get("like", 0)
                lines.append(f"[{like}👍] {uname}: {content}")
            return "\n".join(lines)
        except Exception as e:
            return f"获取评论失败: {e}"

    async def _post_comment(self, bvid: str, content: str, credential=None) -> str:
        if not credential:
            return "发评论需要先配置 B 站账号哦~（credentials.json）"
        if not bvid or not content:
            return "需要提供 BV 号和评论内容"
        try:
            from bilibili_api import video, comment, utils
            v = video.Video(bvid=bvid, credential=credential)
            info = await v.get_info()
            oid = info.get("aid", 0)
            await comment.send_comment(
                text=content,
                oid=oid,
                type_=comment.CommentResourceType.VIDEO,
                credential=credential,
            )
            return f"✅ 已在 {bvid} 发表评论：「{content[:50]}」"
        except Exception as e:
            return f"发评论失败: {e}"

    async def _like(self, bvid: str, credential=None) -> str:
        if not credential:
            return "点赞需要先配置 B 站账号哦~"
        try:
            from bilibili_api import video
            v = video.Video(bvid=bvid, credential=credential)
            await v.like(True)
            return f"✅ 已给 {bvid} 点赞~"
        except Exception as e:
            return f"点赞失败: {e}"

    async def _coin(self, bvid: str, count: int = 1, credential=None) -> str:
        if not credential:
            return "投币需要先配置 B 站账号哦~"
        count = max(1, min(count, 2))
        try:
            from bilibili_api import video
            v = video.Video(bvid=bvid, credential=credential)
            await v.coin(count, like=True)
            return f"✅ 已给 {bvid} 投了 {count} 枚硬币~"
        except Exception as e:
            return f"投币失败: {e}"

    async def _favorite(self, bvid: str, credential=None) -> str:
        if not credential:
            return "收藏需要先配置 B 站账号哦~"
        try:
            from bilibili_api import video, favorite_list
            v = video.Video(bvid=bvid, credential=credential)
            info = await v.get_info()
            aid = info.get("aid", 0)
            # 获取默认收藏夹
            fav_data = await favorite_list.get_video_favorite_list(
                uid=credential.dedeuserid if hasattr(credential, "dedeuserid") else 0,
                video=v,
                credential=credential,
            )
            folders = fav_data.get("list", [])
            if folders:
                folder_id = folders[0].get("id", 0)
                await favorite_list.add_video_favorite_list(
                    media_id=folder_id, aids=[aid], credential=credential
                )
                return f"✅ 已收藏 {bvid}~"
            return "找不到默认收藏夹，请先在 B 站创建一个收藏夹"
        except Exception as e:
            return f"收藏失败: {e}"

    async def _follow(self, uid: int, credential=None) -> str:
        if not credential:
            return "关注需要先配置 B 站账号哦~"
        try:
            from bilibili_api import user
            u = user.User(uid=uid, credential=credential)
            await u.modify_relation(user.RelationType.SUBSCRIBE)
            return f"✅ 已关注 UID {uid}~"
        except Exception as e:
            return f"关注失败: {e}"

    async def _get_feed(self, limit: int = 10, credential=None) -> str:
        if not credential:
            return "查看动态需要先配置 B 站账号哦~"
        try:
            from bilibili_api import dynamic
            data = await dynamic.get_dynamic_page_UPs_info(credential=credential)
            items = (data.get("items") or [])[:min(limit, 20)]
            if not items:
                return "关注的UP主暂时没有新动态~"
            lines = ["📰 关注UP主最新动态：\n"]
            for item in items:
                modules = item.get("modules", {})
                author = modules.get("module_author", {})
                name = author.get("name", "")
                content_mod = modules.get("module_dynamic", {})
                desc = content_mod.get("desc", {})
                text = (desc.get("text") or "")[:100] if desc else ""
                dyn_id = item.get("id_str", "")
                lines.append(f"👤 {name}: {text}\n   https://t.bilibili.com/{dyn_id}")
            return "\n".join(lines)
        except Exception as e:
            return f"获取动态失败: {e}"

    async def _get_zone(self, zone: str, limit: int = 8) -> str:
        zone_map = {
            "动画": 1, "番剧": 13, "国创": 167, "音乐": 3, "舞蹈": 129,
            "游戏": 4, "知识": 36, "科技": 188, "运动": 234, "汽车": 223,
            "生活": 160, "美食": 211, "动物": 217, "时尚": 155, "娱乐": 5,
            "影视": 181, "纪录片": 177, "电影": 23, "电视剧": 11,
        }
        rid = zone_map.get(zone)
        if rid is None:
            available = "、".join(zone_map.keys())
            return f"不认识「{zone}」分区，可用分区：{available}"
        try:
            from bilibili_api import video_zone
            data = await video_zone.get_zone_new_videos(rid)
            archives = (data.get("archives") or [])[:min(limit, 20)]
            if not archives:
                return f"「{zone}」分区暂时没有视频"
            lines = [f"📂 {zone}分区最新视频：\n"]
            for i, v in enumerate(archives, 1):
                lines.append(f"{i}. {_fmt_video(v)}")
            return "\n".join(lines)
        except Exception as e:
            return f"获取分区视频失败: {e}"

    async def _get_recommend(self, limit: int = 10, credential=None) -> str:
        try:
            from bilibili_api import homepage
            data = await homepage.get_videos(credential=credential)
            items = (data.get("item") or [])[:min(limit, 20)]
            if not items:
                return "暂时没有推荐视频"
            lines = ["✨ B站为你推荐：\n"]
            for i, v in enumerate(items, 1):
                lines.append(f"{i}. {_fmt_video(v)}")
            return "\n".join(lines)
        except Exception as e:
            return f"获取推荐失败: {e}"
