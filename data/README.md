# XiaoMeng - 灵萌Moe

> 一个住在服务器里的 AI 女仆 ✨

自家用的 QQ Bot，基于 NoneBot2 + LLM，本地部署运行。

## 开启自启服务

### SoVITS 语音合成

小萌的语音功能依赖 SoVITS，**已配置 systemd 服务实现开机自启**：

```bash
sudo systemctl status sovits.service  # 查看状态
sudo systemctl start sovits.service    # 手动启动
sudo systemctl stop sovits.service     # 停止
```

配置文件统一从 `qq_config.json` 的 `tts` 块读取，换端口/权重只需改 JSON，无需动代码。
