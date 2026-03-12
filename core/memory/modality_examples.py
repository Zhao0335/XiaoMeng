"""
多模态插件系统使用示例

演示：
1. 注册/注销插件
2. 并行分析
3. 自定义融合策略
4. 动态扩展新模态
"""

import asyncio
from .modality_plugin import (
    ModalityPluginSystem,
    ModalityPlugin,
    ModalityResult,
    FusionStrategy,
    FusedResult,
    create_plugin_system
)
from .builtin_plugins import (
    TextModalityPlugin,
    VoiceModalityPlugin,
    FaceModalityPlugin,
    create_default_plugins
)
from typing import Dict, Any, List


class CustomLLMVisionPlugin(ModalityPlugin):
    """
    自定义 LLM 视觉插件示例
    
    这是一个如何创建新模态插件的示例
    """
    
    def __init__(self, model_name: str = "gpt-4-vision"):
        self._model_name = model_name
        self._client = None
    
    @property
    def modality_id(self) -> str:
        return "llm_vision"
    
    @property
    def modality_name(self) -> str:
        return "LLM 视觉分析"
    
    @property
    def description(self) -> str:
        return f"使用 {self._model_name} 分析图像内容"
    
    @property
    def input_types(self) -> List[str]:
        return ["image_path", "image_data", "text"]
    
    @property
    def default_weight(self) -> float:
        return 0.3
    
    async def initialize(self) -> bool:
        return True
    
    async def analyze(self, input_data: Dict[str, Any]) -> ModalityResult:
        image_path = input_data.get("image_path")
        text = input_data.get("text", "描述这张图片")
        
        return ModalityResult(
            modality_id=self.modality_id,
            modality_name=self.modality_name,
            success=True,
            data={
                "description": "LLM 视觉分析结果",
                "model": self._model_name,
                "note": "需要配置 LLM API"
            },
            confidence=0.8
        )


class PriorityFusionStrategy(FusionStrategy):
    """
    优先级融合策略
    
    按优先级选择结果，高优先级模态的结果优先
    """
    
    def __init__(self, priority_order: List[str] = None):
        self._priority_order = priority_order or []
    
    @property
    def strategy_name(self) -> str:
        return "priority"
    
    def fuse(self, results: List[ModalityResult], weights: Dict[str, float]) -> FusedResult:
        import uuid
        from datetime import datetime
        
        if not results:
            return FusedResult(
                result_id=str(uuid.uuid4()),
                primary_data={},
                modality_results=[],
                fusion_strategy=self.strategy_name,
                total_latency_ms=0,
                confidence=0
            )
        
        successful_results = [r for r in results if r.success]
        if not successful_results:
            return FusedResult(
                result_id=str(uuid.uuid4()),
                primary_data={},
                modality_results=results,
                fusion_strategy=self.strategy_name,
                total_latency_ms=sum(r.latency_ms for r in results),
                confidence=0
            )
        
        sorted_results = sorted(
            successful_results,
            key=lambda r: self._priority_order.index(r.modality_id) 
            if r.modality_id in self._priority_order 
            else len(self._priority_order)
        )
        
        primary_result = sorted_results[0]
        
        merged_data = {}
        for result in sorted_results:
            merged_data.update(result.data)
        
        return FusedResult(
            result_id=str(uuid.uuid4()),
            primary_data=merged_data,
            modality_results=results,
            fusion_strategy=self.strategy_name,
            total_latency_ms=sum(r.latency_ms for r in results),
            confidence=primary_result.confidence,
            metadata={"primary_modality": primary_result.modality_id}
        )


async def demo_basic_usage():
    """基础使用示例"""
    print("=== 基础使用示例 ===\n")
    
    system = create_plugin_system(
        default_fusion="attention",
        timeout_ms=3000,
        parallel=True
    )
    
    for plugin in create_default_plugins():
        system.register_plugin(plugin)
        print(f"注册插件: {plugin.modality_name}")
    
    print("\n--- 分析纯文本 ---")
    result = await system.analyze({"text": "今天天气真好，我很开心！"})
    print(f"融合策略: {result.fusion_strategy}")
    print(f"主要数据: {result.primary_data}")
    print(f"总延迟: {result.total_latency_ms:.2f}ms")
    print(f"置信度: {result.confidence:.2f}")
    
    print("\n--- 分析多模态输入 ---")
    result = await system.analyze({
        "text": "我有点难过",
        "audio_path": None,
        "image_path": None
    })
    print(f"参与的模态: {[r.modality_name for r in result.modality_results if r.success]}")
    print(f"融合结果: {result.primary_data}")
    
    print("\n--- 插件信息 ---")
    info = system.get_plugin_info()
    print(f"已注册插件数: {len(info['plugins'])}")
    print(f"可用融合策略: {info['fusion_strategies']}")
    
    print("\n--- 健康检查 ---")
    health = system.health_check()
    print(f"系统状态: {health['system_status']}")
    print(f"活跃插件数: {health['active_count']}/{health['total_count']}")


async def demo_dynamic_plugins():
    """动态扩展插件示例"""
    print("\n=== 动态扩展插件示例 ===\n")
    
    system = create_plugin_system()
    
    system.register_plugin(TextModalityPlugin())
    print("初始: 仅文本插件")
    
    result = await system.analyze({"text": "测试"})
    print(f"参与模态: {[r.modality_name for r in result.modality_results]}")
    
    print("\n动态添加语音插件...")
    system.register_plugin(VoiceModalityPlugin(), weight=0.5)
    
    print("动态添加视觉插件...")
    vision_plugin = CustomLLMVisionPlugin("gpt-4-vision")
    system.register_plugin(vision_plugin)
    
    info = system.get_plugin_info()
    print(f"当前插件数: {len(info['plugins'])}")
    for p in info['plugins']:
        print(f"  - {p['name']} (权重: {p['weight']}, 状态: {p['status']})")
    
    print("\n动态移除插件...")
    system.unregister_plugin("voice")
    
    info = system.get_plugin_info()
    print(f"移除后插件数: {len(info['plugins'])}")


async def demo_custom_fusion():
    """自定义融合策略示例"""
    print("\n=== 自定义融合策略示例 ===\n")
    
    system = create_plugin_system(default_fusion="weighted")
    
    for plugin in create_default_plugins():
        system.register_plugin(plugin)
    
    priority_strategy = PriorityFusionStrategy(
        priority_order=["face", "voice", "text"]
    )
    system.register_fusion_strategy(priority_strategy)
    
    print("使用默认加权融合:")
    result = await system.analyze({"text": "测试文本"})
    print(f"策略: {result.fusion_strategy}")
    
    print("\n使用优先级融合:")
    result = await system.analyze(
        {"text": "测试文本"},
        fusion_strategy="priority"
    )
    print(f"策略: {result.fusion_strategy}")
    print(f"主模态: {result.metadata.get('primary_modality')}")


async def demo_parallel_performance():
    """并行性能示例"""
    print("\n=== 并行性能示例 ===\n")
    
    system_parallel = create_plugin_system(parallel=True)
    system_sequential = create_plugin_system(parallel=False)
    
    for plugin in create_default_plugins():
        system_parallel.register_plugin(plugin)
        system_sequential.register_plugin(plugin)
    
    input_data = {"text": "性能测试"}
    
    print("并行模式:")
    result = await system_parallel.analyze(input_data)
    print(f"  总延迟: {result.total_latency_ms:.2f}ms")
    
    print("\n顺序模式:")
    result = await system_sequential.analyze(input_data)
    print(f"  总延迟: {result.total_latency_ms:.2f}ms")


async def demo_hooks():
    """钩子系统示例"""
    print("\n=== 钩子系统示例 ===\n")
    
    system = create_plugin_system()
    system.register_plugin(TextModalityPlugin())
    
    def before_analyze(data):
        print(f"  [钩子] 开始分析，输入类型: {list(data.keys())}")
    
    def after_analyze(result):
        print(f"  [钩子] 分析完成，置信度: {result.confidence:.2f}")
    
    def on_plugin_register(plugin):
        print(f"  [钩子] 插件注册: {plugin.modality_name}")
    
    system.add_hook("before_analyze", before_analyze)
    system.add_hook("after_analyze", after_analyze)
    system.add_hook("on_plugin_register", on_plugin_register)
    
    print("执行分析（钩子会自动触发）:")
    await system.analyze({"text": "钩子测试"})


def create_custom_plugin_example():
    """
    创建自定义插件的模板代码
    
    复制此代码并修改以创建新的模态插件
    """
    template = '''
class MyCustomPlugin(ModalityPlugin):
    """自定义模态插件"""
    
    @property
    def modality_id(self) -> str:
        return "my_custom"  # 唯一标识
    
    @property
    def modality_name(self) -> str:
        return "我的自定义模态"
    
    @property
    def description(self) -> str:
        return "描述这个模态的功能"
    
    @property
    def input_types(self) -> List[str]:
        return ["custom_data"]  # 支持的输入类型
    
    @property
    def default_weight(self) -> float:
        return 0.2  # 默认权重
    
    async def initialize(self) -> bool:
        # 初始化代码（加载模型等）
        return True
    
    async def analyze(self, input_data: Dict[str, Any]) -> ModalityResult:
        custom_data = input_data.get("custom_data")
        
        if not custom_data:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=False,
                data={},
                error="No custom data"
            )
        
        # 分析逻辑
        result_data = {
            "analysis": "分析结果",
            # ... 更多数据
        }
        
        return ModalityResult(
            modality_id=self.modality_id,
            modality_name=self.modality_name,
            success=True,
            data=result_data,
            confidence=0.8
        )

# 使用
system = create_plugin_system()
system.register_plugin(MyCustomPlugin())
'''
    return template


async def main():
    """运行所有示例"""
    await demo_basic_usage()
    await demo_dynamic_plugins()
    await demo_custom_fusion()
    await demo_parallel_performance()
    await demo_hooks()
    
    print("\n=== 自定义插件模板 ===")
    print(create_custom_plugin_example())


if __name__ == "__main__":
    asyncio.run(main())
