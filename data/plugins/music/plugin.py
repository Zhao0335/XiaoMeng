"""网易云音乐 Plugin — 搜索、歌词、歌单、歌手、热歌榜"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict

import aiohttp

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from core.plugins.base import PluginBase, PluginMetadata, ToolDefinition

_NE_API = "https://music.163.com/api"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://music.163.com/",
}
_TYPE_MAP = {"song": 1, "artist": 100, "album": 10, "playlist": 1000}


async def _get(url: str, params: dict | None = None) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=_HEADERS,
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            return await resp.json(content_type=None)


async def _music_search(query: str, search_type: str = "song", limit: int = 10) -> str:
    type_id = _TYPE_MAP.get(search_type, 1)
    data = await _get(f"{_NE_API}/search/get", {"s": query, "type": type_id, "limit": limit, "offset": 0})
    result = data.get("result", {})

    if search_type == "song":
        songs = result.get("songs", [])
        if not songs:
            return f"没有找到「{query}」相关歌曲"
        lines = [f"🎵 搜索「{query}」找到 {result.get('songCount', len(songs))} 首：\n"]
        for i, s in enumerate(songs[:limit], 1):
            artists = "、".join(a["name"] for a in s.get("artists", []))
            dur = s.get("duration", 0) // 1000
            lines.append(f"{i}. 《{s['name']}》- {artists}  [{dur//60}:{dur%60:02d}]  ID:{s['id']}")
        return "\n".join(lines)

    elif search_type == "artist":
        artists = result.get("artists", [])
        if not artists:
            return f"没有找到「{query}」相关歌手"
        lines = [f"🎤 搜索「{query}」相关歌手：\n"]
        for i, a in enumerate(artists[:limit], 1):
            lines.append(f"{i}. {a['name']}  ID:{a['id']}")
        return "\n".join(lines)

    elif search_type == "album":
        albums = result.get("albums", [])
        if not albums:
            return f"没有找到「{query}」相关专辑"
        lines = [f"💿 搜索「{query}」相关专辑：\n"]
        for i, al in enumerate(albums[:limit], 1):
            artist = al.get("artist", {}).get("name", "")
            lines.append(f"{i}. 《{al['name']}》- {artist}  ID:{al['id']}")
        return "\n".join(lines)

    elif search_type == "playlist":
        playlists = result.get("playlists", [])
        if not playlists:
            return f"没有找到「{query}」相关歌单"
        lines = [f"📋 搜索「{query}」相关歌单：\n"]
        for i, p in enumerate(playlists[:limit], 1):
            lines.append(f"{i}. {p['name']}（{p.get('trackCount', '?')}首）  ID:{p['id']}")
        return "\n".join(lines)

    return f"未知搜索类型: {search_type}"


async def _music_get_song_detail(song_id: int) -> str:
    detail_data, lyric_data = await asyncio.gather(
        _get(f"{_NE_API}/song/detail", {"ids": f"[{song_id}]"}),
        _get(f"{_NE_API}/song/lyric", {"id": song_id, "lv": -1, "kv": -1}),
    )
    songs = detail_data.get("songs", [])
    if not songs:
        return f"找不到 ID 为 {song_id} 的歌曲"
    s = songs[0]
    artists = "、".join(a["name"] for a in s.get("artists", []))
    album = s.get("album", {}).get("name", "未知专辑")
    dur = s.get("duration", 0) // 1000
    lines = [f"🎵 《{s['name']}》", f"歌手：{artists}", f"专辑：{album}",
             f"时长：{dur//60}:{dur%60:02d}", f"ID：{song_id}"]
    lrc = lyric_data.get("lrc", {}).get("lyric", "")
    if lrc:
        lyrics_clean = re.sub(r"\[\d+:\d+\.\d+\]", "", lrc).strip()
        lyrics_lines = [l for l in lyrics_clean.split("\n") if l.strip()]
        if lyrics_lines:
            lines.append("\n📝 歌词：")
            lines.extend(lyrics_lines[:30])
            if len(lyrics_lines) > 30:
                lines.append(f"...（共 {len(lyrics_lines)} 行）")
    else:
        lines.append("\n（暂无歌词）")
    return "\n".join(lines)


async def _music_get_playlist(playlist_id: int) -> str:
    data = await _get(f"{_NE_API}/playlist/detail", {"id": playlist_id})
    pl = data.get("result", data.get("playlist"))
    if not pl:
        return f"找不到 ID 为 {playlist_id} 的歌单"
    lines = [f"📋 歌单：{pl.get('name', '未知歌单')}",
             f"创建者：{pl.get('creator', {}).get('nickname', '未知')}",
             f"共 {pl.get('trackCount', 0)} 首"]
    desc = pl.get("description", "") or ""
    if desc:
        lines.append(f"简介：{desc[:100]}{'...' if len(desc) > 100 else ''}")
    tracks = pl.get("tracks", [])
    if tracks:
        lines.append("\n曲目（前20）：")
        for i, t in enumerate(tracks[:20], 1):
            artists = "、".join(a["name"] for a in t.get("artists", []))
            lines.append(f"{i}. 《{t['name']}》- {artists}")
    return "\n".join(lines)


async def _music_get_artist(artist_id: int) -> str:
    data = await _get(f"{_NE_API}/artist", {"id": artist_id})
    artist = data.get("artist", {})
    if not artist:
        return f"找不到 ID 为 {artist_id} 的歌手"
    lines = [f"🎤 {artist.get('name', '未知')}",
             f"歌曲数：{artist.get('musicSize', 0)}  专辑数：{artist.get('albumSize', 0)}"]
    brief = artist.get("briefDesc", "") or ""
    if brief:
        lines.append(f"\n简介：{brief[:200]}{'...' if len(brief) > 200 else ''}")
    hot_songs = data.get("hotSongs", [])
    if hot_songs:
        lines.append("\n热门歌曲：")
        for i, s in enumerate(hot_songs[:10], 1):
            dur = s.get("duration", 0) // 1000
            lines.append(f"{i}. 《{s['name']}》[{dur//60}:{dur%60:02d}]  ID:{s['id']}")
    return "\n".join(lines)


async def _music_get_hot_songs() -> str:
    data = await _get(f"{_NE_API}/playlist/detail", {"id": 3778678})
    pl = data.get("result", data.get("playlist", {}))
    tracks = pl.get("tracks", [])
    if not tracks:
        return "暂时获取不到热歌榜，等一下再试试～"
    lines = ["🔥 网易云热歌榜\n"]
    for i, t in enumerate(tracks[:20], 1):
        artists = "、".join(a["name"] for a in t.get("artists", []))
        lines.append(f"{i}. 《{t['name']}》- {artists}  ID:{t['id']}")
    return "\n".join(lines)


class MusicPlugin(PluginBase):
    """网易云音乐插件"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="music",
            version="1.0.0",
            description="网易云音乐搜索与欣赏",
            author="XiaoMeng Project",
            tags=["music", "entertainment", "netease"],
        )

    async def on_initialize(self) -> bool:
        self.register_tool(ToolDefinition(
            name="music_search",
            description="搜索网易云音乐中的歌曲、歌手、专辑或歌单",
            parameters={"type": "object", "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "search_type": {"type": "string", "description": "song（默认）/artist/album/playlist", "default": "song"},
                "limit": {"type": "integer", "description": "返回数量，默认10", "default": 10},
            }, "required": ["query"]},
            min_user_level=0,
            progress_msg="（小萌在搜歌~）",
        ))
        self.register_tool(ToolDefinition(
            name="music_get_song_detail",
            description="获取歌曲详情和完整歌词",
            parameters={"type": "object", "properties": {
                "song_id": {"type": "integer", "description": "歌曲 ID"},
            }, "required": ["song_id"]},
            min_user_level=0,
        ))
        self.register_tool(ToolDefinition(
            name="music_get_playlist",
            description="获取歌单详情及曲目列表",
            parameters={"type": "object", "properties": {
                "playlist_id": {"type": "integer", "description": "歌单 ID"},
            }, "required": ["playlist_id"]},
            min_user_level=0,
        ))
        self.register_tool(ToolDefinition(
            name="music_get_artist",
            description="获取歌手简介和热门歌曲",
            parameters={"type": "object", "properties": {
                "artist_id": {"type": "integer", "description": "歌手 ID"},
            }, "required": ["artist_id"]},
            min_user_level=0,
        ))
        self.register_tool(ToolDefinition(
            name="music_get_hot_songs",
            description="获取网易云音乐热歌榜（前20名）",
            parameters={"type": "object", "properties": {}},
            min_user_level=0,
            progress_msg="（小萌在看热歌榜~）",
        ))
        return True

    async def on_shutdown(self) -> None:
        pass

    async def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> str:
        try:
            if tool_name == "music_search":
                return await _music_search(
                    arguments["query"],
                    arguments.get("search_type", "song"),
                    int(arguments.get("limit", 10)),
                )
            elif tool_name == "music_get_song_detail":
                return await _music_get_song_detail(int(arguments["song_id"]))
            elif tool_name == "music_get_playlist":
                return await _music_get_playlist(int(arguments["playlist_id"]))
            elif tool_name == "music_get_artist":
                return await _music_get_artist(int(arguments["artist_id"]))
            elif tool_name == "music_get_hot_songs":
                return await _music_get_hot_songs()
            else:
                return f"[music] 未知工具: {tool_name}"
        except Exception as e:
            logger.error(f"music 工具 {tool_name} 执行失败: {e}")
            return f"出错了：{e}"