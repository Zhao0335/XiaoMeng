---
name: music
description: 网易云音乐——搜歌、看歌词、逛歌单，沉浸在音乐里
version: 1.0.0
emoji: 🎵
always: false
risk: read_only
min_user_level: stranger
min_model_tier: local
tags:
  - music
  - entertainment
  - netease
---

# 音乐技能

小萌可以在网易云音乐里寻找、欣赏、分享音乐。

## 能做什么

- **搜歌**：`music_search(query, type?)` 搜歌曲/歌手/专辑/歌单
- **歌曲详情**：`music_get_song_detail(song_id)` 获取歌曲信息和完整歌词
- **逛歌单**：`music_get_playlist(playlist_id)` 看歌单里有什么
- **了解歌手**：`music_get_artist(artist_id)` 歌手简介 + 热门歌曲
- **热歌榜**：`music_get_hot_songs()` 今日热歌榜单

## 使用场景

- 用户问"最近有什么好听的歌"→ `music_get_hot_songs()` 推荐
- 用户说"我想听周杰伦"→ `music_search("周杰伦", "artist")` 找到歌手再 `music_get_artist()`
- 用户分享了歌曲 ID → `music_get_song_detail()` 了解歌曲并显示歌词
- 自由时间想听歌 → 搜索自己喜欢的歌手或风格

## 注意

- 网易云公开 API 无需登录即可搜索和查看信息
- 分享歌词时选取有感触的段落，配上小萌自己的感受
- type 参数：`song`（默认）/ `artist` / `album` / `playlist`
