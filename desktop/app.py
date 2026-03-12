"""
XiaoMengCore 桌面应用
PyQt5 实现
"""

import sys
import os
import asyncio
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QTabWidget,
    QComboBox, QSpinBox, QFormLayout, QGroupBox, QListWidget,
    QListWidgetItem, QMessageBox, QSplitter, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon


class AsyncWorker(QThread):
    """异步工作线程"""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.func(*self.args, **self.kwargs))
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class StatusWidget(QWidget):
    """状态显示组件"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_status()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        group = QGroupBox("系统状态")
        form = QFormLayout(group)
        
        self.git_label = QLabel("检查中...")
        self.audit_label = QLabel("检查中...")
        self.tools_label = QLabel("检查中...")
        self.persona_label = QLabel("检查中...")
        
        form.addRow("Git 版本控制:", self.git_label)
        form.addRow("审计日志:", self.audit_label)
        form.addRow("已注册工具:", self.tools_label)
        form.addRow("人设加载:", self.persona_label)
        
        layout.addWidget(group)
        
        refresh_btn = QPushButton("刷新状态")
        refresh_btn.clicked.connect(self.load_status)
        layout.addWidget(refresh_btn)
    
    def load_status(self):
        from core.version_control import VersionControl
        from core.memory import MemoryManager
        from core.tools import ToolRegistry
        
        vc = VersionControl.get_instance()
        mm = MemoryManager.get_instance()
        registry = ToolRegistry.get_instance()
        
        git_ok = vc._git._enabled if vc._git else False
        self.git_label.setText("✅ 启用" if git_ok else "❌ 禁用")
        self.git_label.setStyleSheet("color: green;" if git_ok else "color: red;")
        
        audit_ok = vc._audit is not None
        self.audit_label.setText("✅ 启用" if audit_ok else "❌ 禁用")
        self.audit_label.setStyleSheet("color: green;" if audit_ok else "color: red;")
        
        self.tools_label.setText(f"{len(registry.get_all_tools())} 个")
        
        persona_ok = mm._persona_loader is not None
        self.persona_label.setText("✅ 已加载" if persona_ok else "❌ 未加载")
        self.persona_label.setStyleSheet("color: green;" if persona_ok else "color: red;")


class LLMConfigWidget(QWidget):
    """LLM 配置组件"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_config()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        group = QGroupBox("LLM 配置")
        form = QFormLayout(group)
        
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["local", "openai", "deepseek", "anthropic", "ollama"])
        form.addRow("提供商:", self.provider_combo)
        
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("Qwen2.5-7B")
        form.addRow("模型:", self.model_input)
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("sk-...")
        form.addRow("API Key:", self.api_key_input)
        
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("http://localhost:11434/v1")
        form.addRow("Base URL:", self.base_url_input)
        
        layout.addWidget(group)
        
        save_btn = QPushButton("保存配置")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)
    
    def load_config(self):
        import json
        config_path = Path("./data/config.json")
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            llm = config.get('llm', {})
            self.provider_combo.setCurrentText(llm.get('provider', 'local'))
            self.model_input.setText(llm.get('model', ''))
            self.api_key_input.setText(llm.get('api_key', ''))
            self.base_url_input.setText(llm.get('base_url', ''))
    
    def save_config(self):
        import json
        config_path = Path("./data/config.json")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}
        
        config['llm'] = {
            'provider': self.provider_combo.currentText(),
            'model': self.model_input.text(),
            'api_key': self.api_key_input.text(),
            'base_url': self.base_url_input.text()
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        QMessageBox.information(self, "成功", "LLM 配置已保存！")


class PersonaWidget(QWidget):
    """人设编辑组件"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_persona()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        
        self.soul_edit = QTextEdit()
        self.soul_edit.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.soul_edit, "SOUL.md")
        
        self.agents_edit = QTextEdit()
        self.agents_edit.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.agents_edit, "AGENTS.md")
        
        self.identity_edit = QTextEdit()
        self.identity_edit.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.identity_edit, "IDENTITY.md")
        
        self.memory_edit = QTextEdit()
        self.memory_edit.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.memory_edit, "MEMORY.md")
        
        self.user_edit = QTextEdit()
        self.user_edit.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.user_edit, "USER.md")
        
        layout.addWidget(self.tabs)
        
        btn_layout = QHBoxLayout()
        
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_persona)
        btn_layout.addWidget(save_btn)
        
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.load_persona)
        btn_layout.addWidget(refresh_btn)
        
        layout.addLayout(btn_layout)
    
    def load_persona(self):
        from core.memory import MemoryManager
        
        mm = MemoryManager.get_instance()
        persona = mm.load_persona()
        
        self.soul_edit.setPlainText(persona.soul or "")
        self.agents_edit.setPlainText(persona.agents or "")
        self.identity_edit.setPlainText(persona.identity or "")
        self.memory_edit.setPlainText(persona.memory or "")
        self.user_edit.setPlainText(persona.user_info or "")
    
    def save_persona(self):
        from core.memory import MemoryManager
        from core.version_control import VersionControl
        
        mm = MemoryManager.get_instance()
        
        files = {
            "SOUL.md": self.soul_edit.toPlainText(),
            "AGENTS.md": self.agents_edit.toPlainText(),
            "IDENTITY.md": self.identity_edit.toPlainText(),
            "MEMORY.md": self.memory_edit.toPlainText(),
            "USER.md": self.user_edit.toPlainText()
        }
        
        for file, content in files.items():
            mm._persona_loader.save_file(file, content)
        
        vc = VersionControl.get_instance()
        if vc.is_enabled():
            for file in files.keys():
                vc._git.add(file)
            vc._git.commit("Update persona from desktop app")
        
        QMessageBox.information(self, "成功", "人设已保存！")


class ChatWidget(QWidget):
    """对话组件"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.messages = []
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.chat_display)
        
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("输入消息...")
        self.message_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.message_input)
        
        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)
        
        layout.addLayout(input_layout)
    
    def send_message(self):
        text = self.message_input.text().strip()
        if not text:
            return
        
        self.add_message("你", text, is_user=True)
        self.message_input.clear()
        
        self.worker = AsyncWorker(self._get_response, text)
        self.worker.finished.connect(lambda r: self.add_message("小螃蟹", r, is_user=False))
        self.worker.error.connect(lambda e: self.add_message("系统", f"错误: {e}", is_user=False))
        self.worker.start()
    
    async def _get_response(self, message: str) -> str:
        from core.memory import MemoryManager
        from core.llm_client import LLMClient
        
        mm = MemoryManager.get_instance()
        persona = mm.load_persona()
        
        system_prompt = f"""{persona.identity if persona.identity else ''}

{persona.soul if persona.soul else ''}

{persona.agents if persona.agents else ''}

{persona.user_info if persona.user_info else ''}
"""
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": message})
        
        llm = LLMClient.get_instance()
        response = await llm.chat(messages=messages)
        
        return response
    
    def add_message(self, sender: str, text: str, is_user: bool = False):
        color = "#667eea" if is_user else "#333"
        self.chat_display.append(f'<p><b style="color:{color}">{sender}:</b> {text}</p>')
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )


class ToolsWidget(QWidget):
    """工具列表组件"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.load_tools()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.tools_list = QListWidget()
        layout.addWidget(self.tools_list)
        
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.load_tools)
        layout.addWidget(refresh_btn)
    
    def load_tools(self):
        from core.tools import ToolRegistry
        
        registry = ToolRegistry.get_instance()
        tools = registry.get_all_tools()
        
        self.tools_list.clear()
        for tool in tools:
            item = QListWidgetItem(f"{tool.name}: {tool.description}")
            if getattr(tool, 'requires_owner', False):
                item.setForeground(Qt.red)
            self.tools_list.addItem(item)


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("XiaoMengCore - 多端 AI 桌宠/伴侣框架")
        self.setGeometry(100, 100, 1000, 700)
        self.init_ui()
    
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout(central)
        
        header = QLabel("🦀 XiaoMengCore")
        header.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        tabs = QTabWidget()
        
        tabs.addTab(ChatWidget(), "💬 对话")
        tabs.addTab(StatusWidget(), "📊 状态")
        tabs.addTab(LLMConfigWidget(), "⚙️ LLM配置")
        tabs.addTab(PersonaWidget(), "📝 人设")
        tabs.addTab(ToolsWidget(), "🔧 工具")
        
        layout.addWidget(tabs)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
