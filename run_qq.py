#!/usr/bin/env python3
"""
QQ Bot 入口
用法：python run_qq.py [--config path/to/qq_config.json]

首次运行前请先编辑 data/qq_config.json，填入 owner_qq 和模型配置。
"""

import argparse
import asyncio
import json
import logging
import os
import sys

# 把 XiaoMeng 根目录加入 sys.path
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_qq")


def load_config(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"配置文件不存在: {path}")
        logger.info("请先复制 data/qq_config.example.json → data/qq_config.json 并填写配置")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"配置文件 JSON 格式错误: {e}")
        sys.exit(1)


def validate_config(cfg: dict) -> None:
    if not cfg.get("owner_qq"):
        logger.error("请在配置文件中填写 owner_qq（你的 QQ 号）")
        sys.exit(1)
    if not cfg.get("models"):
        logger.warning("未配置任何模型，bot 将无法回复消息")


async def main(config_path: str) -> None:
    cfg = load_config(config_path)
    validate_config(cfg)

    from core.qq.gateway import QQGateway

    gateway = QQGateway(cfg)

    logger.info("=" * 50)
    logger.info(f"  Bot 名称: {cfg.get('bot_name', '小萌')}")
    logger.info(f"  主人 QQ: {cfg.get('owner_qq')}")
    logger.info(f"  NapCat:  {cfg.get('napcat_ws_url', 'ws://127.0.0.1:3001')}")
    logger.info(f"  模型数量: {len(cfg.get('models', []))}")
    logger.info("=" * 50)
    logger.info("正在连接 NapCat...")

    try:
        await gateway.start()
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
        await gateway.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XiaoMeng QQ Bot")
    parser.add_argument(
        "--config",
        default="data/qq_config.json",
        help="配置文件路径（默认: data/qq_config.json）",
    )
    args = parser.parse_args()
    asyncio.run(main(args.config))
