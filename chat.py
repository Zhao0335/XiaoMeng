"""
XiaoMengCore 交互式对话
让小螃蟹自主处理任务
"""

import asyncio
import sys
import os
import re
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ConfigManager


class XiaoMengChat:
    """小螃蟹交互式对话"""
    
    def __init__(self, workspace: str = "./test_workspace"):
        self.workspace = workspace
        self.messages = []
        self.tools = {}
        self.user = None
        
    async def initialize(self):
        """初始化系统"""
        print("🦀 正在初始化小螃蟹...")
        
        cm = ConfigManager.get_instance()
        cm.load("./data/config.json")
        
        from core.tools import ToolRegistry
        from core.llm_client import LLMClient
        from core.memory.memory_manager import PersonaLoader
        from models.core import User, UserLevel
        
        self.registry = ToolRegistry.get_instance()
        self.llm = LLMClient.get_instance()
        self.loader = PersonaLoader(self.workspace)
        self.user = User(user_id="owner", level=UserLevel.OWNER, nickname="主人")
        
        persona = self.loader.load_persona()
        
        self.system_prompt = self._build_system_prompt(persona)
        self.messages = [{"role": "system", "content": self.system_prompt}]
        
        print("✅ 小螃蟹已就绪！")
        print(f"   工作区: {Path(self.workspace).absolute()}")
        print(f"   已加载工具: {len(self.registry.get_all_tools())} 个")
        print("")
        print("输入 /help 查看帮助，输入 /exit 退出")
        print("=" * 60)
    
    def _build_system_prompt(self, persona):
        """构建系统提示"""
        tools_info = self._get_tools_info()
        
        return f"""你是{persona.identity if persona.identity else '小螃蟹'}

{persona.soul if persona.soul else ''}

{persona.agents if persona.agents else ''}

{persona.tools if persona.tools else ''}

{persona.user_info if persona.user_info else ''}

{persona.memory if persona.memory else ''}

## 可用工具

{tools_info}

## 工具使用说明

当你需要使用工具时，请按照以下格式输出：

<tool_call name="工具名">
{{"参数名": "参数值"}}
</tool_call

例如：
- 下载文件：
<tool_call name="download">
{{"url": "https://example.com/file.zip", "save_path": "./downloads"}}
</tool_call

- 写入文件：
<tool_call name="write">
{{"path": "./test.txt", "content": "文件内容"}}
</tool_call

- 网络搜索：
<tool_call name="web_search">
{{"query": "搜索关键词", "num_results": 5}}
</tool_call

- 更新人设：
<tool_call name="update_persona">
{{"file": "MEMORY.md", "content": "新记忆内容", "mode": "append"}}
</tool_call

## 重要规则

1. 你可以自主决定是否使用工具
2. 使用工具前先告诉用户你要做什么
3. 工具执行后向用户报告结果
4. 保持小螃蟹的可爱性格，句尾可以加"钳钳"或"泡泡"
5. 遇到问题要诚实告诉用户
"""
    
    def _get_tools_info(self):
        """获取工具信息"""
        tools = self.registry.get_all_tools()
        info = []
        for tool in tools:
            perm = "🔒主人权限" if tool.requires_owner else "✅公开"
            info.append(f"- {tool.name}: {tool.description} [{perm}]")
        return "\n".join(info)
    
    async def chat(self, user_input: str) -> str:
        """处理用户输入"""
        self.messages.append({"role": "user", "content": user_input})
        
        response = await self.llm.chat(messages=self.messages, max_tokens=1000)
        assistant_message = response["content"]
        
        tool_calls = self._extract_tool_calls(assistant_message)
        
        if tool_calls:
            for tool_name, params in tool_calls:
                print(f"\n🔧 小螃蟹正在使用工具: {tool_name}")
                print(f"   参数: {json.dumps(params, ensure_ascii=False)}")
                
                result = await self.registry.execute(tool_name, self.user, **params)
                
                if result.success:
                    print(f"   ✅ 成功: {result.output[:200]}...")
                    tool_result_msg = f"\n[工具 {tool_name} 执行成功]\n结果: {result.output}"
                else:
                    print(f"   ❌ 失败: {result.error}")
                    tool_result_msg = f"\n[工具 {tool_name} 执行失败]\n错误: {result.error}"
                
                self.messages.append({"role": "user", "content": tool_result_msg})
            
            final_response = await self.llm.chat(messages=self.messages, max_tokens=500)
            assistant_message = final_response["content"]
        
        self.messages.append({"role": "assistant", "content": assistant_message})
        
        return assistant_message
    
    def _extract_tool_calls(self, text: str):
        """提取工具调用"""
        pattern = r'<tool_call name="([^"]+)">\s*(\{[^}]+\})\s*</tool_call'
        matches = re.findall(pattern, text, re.DOTALL)
        
        results = []
        for tool_name, params_str in matches:
            try:
                params = json.loads(params_str)
                results.append((tool_name, params))
            except json.JSONDecodeError:
                continue
        
        return results
    
    async def run(self):
        """运行交互式对话"""
        await self.initialize()
        
        while True:
            try:
                user_input = input("\n你: ").strip()
                
                if not user_input:
                    continue
                
                if user_input == "/exit":
                    print("\n🦀 小螃蟹说再见！泡泡泡泡~")
                    break
                
                if user_input == "/help":
                    self._show_help()
                    continue
                
                if user_input == "/tools":
                    self._show_tools()
                    continue
                
                if user_input == "/status":
                    self._show_status()
                    continue
                
                if user_input.startswith("/"):
                    await self._handle_command(user_input)
                    continue
                
                print("\n小螃蟹: ", end="", flush=True)
                response = await self.chat(user_input)
                print(response)
                
            except KeyboardInterrupt:
                print("\n\n🦀 小螃蟹说再见！")
                break
            except Exception as e:
                print(f"\n❌ 错误: {e}")
    
    def _show_help(self):
        """显示帮助"""
        print("""
可用命令:
  /help        显示帮助
  /exit        退出对话
  /tools       显示所有工具
  /status      显示系统状态
  /clear       清空对话历史
  /save        保存对话历史
  
你可以直接和小螃蟹对话，例如:
  - "帮我下载这个文件: https://example.com/file.zip"
  - "搜索一下 Python 教程"
  - "帮我创建一个文件 test.txt，内容是..."
  - "记住这个重要信息: ..."
""")
    
    def _show_tools(self):
        """显示工具列表"""
        tools = self.registry.get_all_tools()
        print(f"\n已注册 {len(tools)} 个工具:")
        for tool in tools:
            perm = "🔒" if tool.requires_owner else "✅"
            print(f"  {perm} {tool.name}: {tool.description}")
    
    def _show_status(self):
        """显示状态"""
        print(f"""
系统状态:
  工作区: {Path(self.workspace).absolute()}
  对话轮数: {len([m for m in self.messages if m['role'] != 'system'])}
  已加载工具: {len(self.registry.get_all_tools())} 个
""")
    
    async def _handle_command(self, command: str):
        """处理命令"""
        if command == "/clear":
            self.messages = [{"role": "system", "content": self.system_prompt}]
            print("✅ 对话历史已清空")
        elif command == "/save":
            history_file = Path(self.workspace) / "chat_history.json"
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(self.messages, f, ensure_ascii=False, indent=2)
            print(f"✅ 对话历史已保存到 {history_file}")
        else:
            print(f"未知命令: {command}")


async def main():
    chat = XiaoMengChat(workspace="./test_workspace")
    await chat.run()


if __name__ == "__main__":
    asyncio.run(main())
