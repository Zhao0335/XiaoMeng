"""
XiaoMengCore 使用示例

展示如何使用简洁的 API 创建自定义机器人
"""

import asyncio
from api import XiaoMengBot, BotConfig, Plugin, Tool, ToolResult, create_bot


class WeatherTool(Tool):
    """天气工具示例"""
    
    name = "weather"
    description = "获取指定城市的天气信息"
    
    async def execute(self, city: str) -> ToolResult:
        weather_data = {
            "北京": "晴天，温度 15°C",
            "上海": "多云，温度 18°C",
            "广州": "小雨，温度 22°C",
        }
        weather = weather_data.get(city, "未知城市")
        return ToolResult(True, f"{city}的天气: {weather}")


class LoggingPlugin(Plugin):
    """日志插件示例"""
    
    name = "logging"
    
    async def on_load(self, bot):
        print(f"[插件] {self.name} 已加载")
    
    async def on_message(self, message, response):
        print(f"[日志] 用户: {message.content}")
        print(f"[日志] 回复: {response}")
        return response


async def example_basic():
    """基础使用示例"""
    print("=" * 50)
    print("示例 1: 基础使用")
    print("=" * 50)
    
    bot = create_bot(name="小螃蟹")
    await bot.start()
    
    response = await bot.chat("你好，介绍一下自己")
    print(f"回复: {response}")
    
    await bot.stop()


async def example_custom_config():
    """自定义配置示例"""
    print("\n" + "=" * 50)
    print("示例 2: 自定义配置")
    print("=" * 50)
    
    config = BotConfig(
        name="小助手",
        llm_model="qwen2.5:3b",
        data_dir="./test_workspace"
    )
    
    bot = XiaoMengBot(config=config)
    await bot.start()
    
    response = await bot.chat("你叫什么名字？")
    print(f"回复: {response}")
    
    await bot.stop()


async def example_with_plugins():
    """插件示例"""
    print("\n" + "=" * 50)
    print("示例 3: 使用插件")
    print("=" * 50)
    
    bot = XiaoMengBot()
    bot.add_plugin(LoggingPlugin())
    
    await bot.start()
    
    response = await bot.chat("今天天气怎么样？")
    print(f"最终回复: {response}")
    
    await bot.stop()


async def example_with_tools():
    """工具示例"""
    print("\n" + "=" * 50)
    print("示例 4: 自定义工具")
    print("=" * 50)
    
    bot = XiaoMengBot()
    bot.add_tool(WeatherTool())
    
    await bot.start()
    
    response = await bot.chat("北京今天天气怎么样？")
    print(f"回复: {response}")
    
    await bot.stop()


async def main():
    """运行所有示例"""
    await example_basic()
    await example_custom_config()
    await example_with_plugins()
    await example_with_tools()
    
    print("\n" + "=" * 50)
    print("所有示例完成！")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
