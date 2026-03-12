"""
XiaoMengCore 简单命令行交互
"""

import asyncio
import sys
import os
import re
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ConfigManager


async def main():
    print("=" * 60)
    print("🦀 XiaoMengCore 命令行 - 小螃蟹")
    print("   输入 /exit 退出")
    print("=" * 60)
    
    cm = ConfigManager.get_instance()
    cm.load("./data/config.json")
    
    from core.tools import ToolRegistry
    from core.llm_client import LLMClient
    from core.memory.memory_manager import PersonaLoader
    from models.core import User, UserLevel
    
    registry = ToolRegistry.get_instance()
    llm = LLMClient.get_instance()
    loader = PersonaLoader("./data")
    user = User(user_id="owner", level=UserLevel.OWNER)
    
    persona = loader.load_persona()
    
    identity = persona.identity if persona.identity else '小螃蟹'
    soul = persona.soul if persona.soul else ''
    agents = persona.agents if persona.agents else ''
    tools_desc = persona.tools if persona.tools else ''
    
    system_prompt = f"""你是{identity}

{soul}

{agents}

{tools_desc}

## 可用工具

- write: 写入文件 {{"path": "路径", "content": "内容"}}
- read: 读取文件 {{"path": "路径"}}
- ls: 列出目录 {{"path": "路径"}}
- download: 下载文件 {{"url": "链接", "save_path": "路径"}}
- web_fetch: 获取网页 {{"url": "链接"}}
- web_search: 网络搜索 {{"query": "关键词"}}
- add_memory: 添加记忆 {{"content": "内容"}}
- get_history: 查看历史 {{"limit": 10}}

## 工具调用格式

当你需要使用工具时，必须使用以下格式：

<tool_call name="工具名">
{{"参数": "值"}}
</tool_call

例如下载文件：
<tool_call name="download">
{{"url": "https://example.com/file.pdf", "save_path": "./papers"}}
</tool_call

重要：使用工具后，等待工具执行结果，然后再回复用户。不要只是说"我会执行"，而是真正调用工具！

保持小螃蟹的可爱性格！
"""
    
    messages = [{"role": "system", "content": system_prompt}]
    
    while True:
        try:
            user_input = input("\n你: ").strip()
            
            if not user_input:
                continue
            
            if user_input == "/exit":
                print("\n🦀 再见！")
                break
            
            messages.append({"role": "user", "content": user_input})
            
            response = await llm.chat(messages=messages, max_tokens=500)
            assistant_message = response["content"]
            
            pattern = r'<tool_call\s+name="([^"]+)">\s*(\{[^}]+\})\s*</tool_call\s*>'
            tool_calls = re.findall(pattern, assistant_message, re.DOTALL)
            
            if tool_calls:
                for tool_name, params_str in tool_calls:
                    try:
                        params = json.loads(params_str)
                        print(f"\n🔧 使用工具: {tool_name}")
                        result = await registry.execute(tool_name, user, **params)
                        if result.success:
                            print(f"   ✅ {result.output[:200]}")
                            messages.append({"role": "user", "content": f"[工具成功] {result.output}"})
                        else:
                            print(f"   ❌ {result.error}")
                            messages.append({"role": "user", "content": f"[工具失败] {result.error}"})
                    except Exception as e:
                        print(f"   ❌ 错误: {e}")
                
                final = await llm.chat(messages=messages, max_tokens=300)
                assistant_message = final["content"]
            
            messages.append({"role": "assistant", "content": assistant_message})
            print(f"\n小螃蟹: {assistant_message}")
            
        except KeyboardInterrupt:
            print("\n\n🦀 再见！")
            break
        except Exception as e:
            print(f"\n错误: {e}")


if __name__ == "__main__":
    asyncio.run(main())
