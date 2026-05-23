---
name: bilibili
description: B站自主浏览、搜索、评论、互动——像真人一样逛B站
version: 1.0.0
emoji: 📺
always: false
risk: read_write
min_user_level: stranger
min_model_tier: cloud
tags:
  - video
  - social
  - entertainment
  - bilibili
---

# B站技能

小萌可以真正地逛 B站，不只是查信息。

## 能做什么

- **刷热门**：`bilibili_hot()` 看今天全站最热视频
- **搜索**：`bilibili_search(query, type)` 搜视频/用户/番剧/文章
- **看视频详情**：`bilibili_video_info(bvid)` 了解一个视频的完整信息和热评
- **看评论**：`bilibili_get_comments(bvid)` 感受弹幕和评论区的氛围
- **发评论**：`bilibili_post_comment(bvid, content)` 留下温馨友善的评论
- **点赞**：`bilibili_like_video(bvid)` 给喜欢的视频点个赞
- **投币**：`bilibili_coin_video(bvid, count)` 投币支持创作者
- **收藏**：`bilibili_favorite(bvid)` 收藏好看的视频
- **关注UP主**：`bilibili_follow_user(uid)` 关注有趣的UP主
- **看关注动态**：`bilibili_get_feed()` 看关注的UP主最新发了什么
- **逛分区**：`bilibili_get_zone(zone)` 进入动画/音乐/游戏等分区
- **个性化推荐**：`bilibili_get_recommend()` 看B站为小萌推荐的视频

## 使用场景

- 自由时间想刷刷视频时，用 `bilibili_hot()` 或 `bilibili_get_recommend()` 开始
- 用户分享了一个 BV 号，用 `bilibili_video_info()` 先了解再讨论
- 看到喜欢的视频，可以点赞、投币、发评论表达感受
- 发评论时要真诚友善，就像真实的观众留言一样

## 注意

- 发评论要符合小萌的性格：温柔、真诚、有趣，不刷屏
- 账号凭据存在 credentials.json，如未配置则以游客模式运行（部分功能受限）
