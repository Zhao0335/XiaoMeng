"""
内置模态插件实现

包含：
1. TextModalityPlugin - 文本情感/意图分析
2. VoiceModalityPlugin - 语音情感分析
3. FaceModalityPlugin - 面部表情识别
4. ImageModalityPlugin - 图像场景分析
5. SensorModalityPlugin - 传感器数据分析（示例）
"""

from .modality_plugin import ModalityPlugin, ModalityResult
from typing import Dict, Any, List
import time


class TextModalityPlugin(ModalityPlugin):
    """文本模态插件"""
    
    @property
    def modality_id(self) -> str:
        return "text"
    
    @property
    def modality_name(self) -> str:
        return "文本分析"
    
    @property
    def description(self) -> str:
        return "分析文本的情感、意图和实体"
    
    @property
    def input_types(self) -> List[str]:
        return ["text"]
    
    @property
    def default_weight(self) -> float:
        return 0.4
    
    async def analyze(self, input_data: Dict[str, Any]) -> ModalityResult:
        text = input_data.get("text", "")
        
        if not text:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=False,
                data={},
                error="No text input"
            )
        
        emotion = self._analyze_emotion(text)
        intent = self._analyze_intent(text)
        entities = self._extract_entities(text)
        
        return ModalityResult(
            modality_id=self.modality_id,
            modality_name=self.modality_name,
            success=True,
            data={
                "emotion": emotion,
                "intent": intent,
                "entities": entities,
                "text_length": len(text)
            },
            confidence=self._calculate_confidence(text)
        )
    
    def _analyze_emotion(self, text: str) -> str:
        emotions = {
            "happy": ["开心", "高兴", "快乐", "幸福", "哈哈", "😊"],
            "sad": ["难过", "伤心", "悲伤", "哭", "😢"],
            "angry": ["生气", "愤怒", "烦", "讨厌", "😠"],
            "neutral": []
        }
        
        for emotion, keywords in emotions.items():
            if any(kw in text for kw in keywords):
                return emotion
        return "neutral"
    
    def _analyze_intent(self, text: str) -> str:
        intents = {
            "question": ["?", "吗", "什么", "怎么", "为什么"],
            "command": ["请", "帮我", "给我", "打开"],
            "statement": []
        }
        
        for intent, keywords in intents.items():
            if any(kw in text for kw in keywords):
                return intent
        return "statement"
    
    def _extract_entities(self, text: str) -> List[str]:
        return []
    
    def _calculate_confidence(self, text: str) -> float:
        return min(0.5 + len(text) / 100, 1.0)


class VoiceModalityPlugin(ModalityPlugin):
    """语音模态插件"""
    
    def __init__(self):
        self._librosa_available = self._check_librosa()
    
    def _check_librosa(self) -> bool:
        try:
            import librosa
            return True
        except ImportError:
            return False
    
    @property
    def modality_id(self) -> str:
        return "voice"
    
    @property
    def modality_name(self) -> str:
        return "语音分析"
    
    @property
    def description(self) -> str:
        return "分析语音的情感特征（音高、能量、语速）"
    
    @property
    def input_types(self) -> List[str]:
        return ["audio_path", "audio_data"]
    
    @property
    def default_weight(self) -> float:
        return 0.35
    
    async def initialize(self) -> bool:
        return True
    
    async def analyze(self, input_data: Dict[str, Any]) -> ModalityResult:
        audio_path = input_data.get("audio_path")
        audio_data = input_data.get("audio_data")
        
        if not audio_path and not audio_data:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=False,
                data={},
                error="No audio input"
            )
        
        if not self._librosa_available:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=True,
                data={"emotion": "neutral", "note": "librosa not available"},
                confidence=0.3
            )
        
        try:
            result = self._analyze_audio(audio_path, audio_data)
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=True,
                data=result,
                confidence=result.get("confidence", 0.7)
            )
        except Exception as e:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=False,
                data={},
                error=str(e)
            )
    
    def _analyze_audio(self, audio_path: str, audio_data: bytes) -> Dict:
        import librosa
        import numpy as np
        
        if audio_path:
            y, sr = librosa.load(audio_path, sr=16000)
        else:
            import io
            y, sr = librosa.load(io.BytesIO(audio_data), sr=16000)
        
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        pitch_values = pitches[magnitudes > np.median(magnitudes)]
        pitch_mean = np.mean(pitch_values) if len(pitch_values) > 0 else 200
        
        energy = librosa.feature.rms(y=y)[0]
        energy_mean = np.mean(energy)
        
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        
        if pitch_mean > 250 and energy_mean > 0.5:
            emotion = "happy"
        elif pitch_mean < 150 and energy_mean < 0.3:
            emotion = "sad"
        elif pitch_mean > 300 and energy_mean > 0.6:
            emotion = "angry"
        else:
            emotion = "neutral"
        
        return {
            "emotion": emotion,
            "pitch_mean": float(pitch_mean),
            "energy_mean": float(energy_mean),
            "tempo": float(tempo),
            "confidence": 0.7
        }


class FaceModalityPlugin(ModalityPlugin):
    """面部表情模态插件"""
    
    def __init__(self):
        self._deepface_available = self._check_deepface()
    
    def _check_deepface(self) -> bool:
        try:
            from deepface import DeepFace
            return True
        except ImportError:
            return False
    
    @property
    def modality_id(self) -> str:
        return "face"
    
    @property
    def modality_name(self) -> str:
        return "面部表情识别"
    
    @property
    def description(self) -> str:
        return "识别面部表情和情绪"
    
    @property
    def input_types(self) -> List[str]:
        return ["image_path", "image_data"]
    
    @property
    def default_weight(self) -> str:
        return 0.25
    
    async def initialize(self) -> bool:
        return True
    
    async def analyze(self, input_data: Dict[str, Any]) -> ModalityResult:
        image_path = input_data.get("image_path")
        image_data = input_data.get("image_data")
        
        if not image_path and not image_data:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=False,
                data={},
                error="No image input"
            )
        
        if not self._deepface_available:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=True,
                data={"emotion": "neutral", "note": "deepface not available"},
                confidence=0.3
            )
        
        try:
            result = self._analyze_face(image_path, image_data)
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=True,
                data=result,
                confidence=result.get("confidence", 0.8)
            )
        except Exception as e:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=False,
                data={},
                error=str(e)
            )
    
    def _analyze_face(self, image_path: str, image_data: bytes) -> Dict:
        from deepface import DeepFace
        
        if image_path:
            result = DeepFace.analyze(image_path, actions=['emotion'], enforce_detection=False)
        else:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                f.write(image_data)
                result = DeepFace.analyze(f.name, actions=['emotion'], enforce_detection=False)
        
        if isinstance(result, list):
            result = result[0]
        
        return {
            "emotion": result.get('dominant_emotion', 'neutral'),
            "confidence": result.get('emotion', {}).get(result.get('dominant_emotion', 'neutral'), 50) / 100,
            "all_emotions": result.get('emotion', {})
        }


class ImageModalityPlugin(ModalityPlugin):
    """图像场景分析插件"""
    
    def __init__(self):
        self._model = None
    
    @property
    def modality_id(self) -> str:
        return "image"
    
    @property
    def modality_name(self) -> str:
        return "图像场景分析"
    
    @property
    def description(self) -> str:
        return "分析图像中的场景、物体和活动"
    
    @property
    def input_types(self) -> List[str]:
        return ["image_path", "image_data"]
    
    @property
    def default_weight(self) -> float:
        return 0.2
    
    async def initialize(self) -> bool:
        return True
    
    async def analyze(self, input_data: Dict[str, Any]) -> ModalityResult:
        image_path = input_data.get("image_path")
        image_data = input_data.get("image_data")
        
        if not image_path and not image_data:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=False,
                data={},
                error="No image input"
            )
        
        return ModalityResult(
            modality_id=self.modality_id,
            modality_name=self.modality_name,
            success=True,
            data={
                "scene": "unknown",
                "objects": [],
                "activities": [],
                "note": "Image analysis requires vision model"
            },
            confidence=0.5
        )


class SensorModalityPlugin(ModalityPlugin):
    """
    传感器数据模态插件（示例）
    
    可用于：
    - 心率数据
    - 运动传感器
    - 环境传感器
    """
    
    @property
    def modality_id(self) -> str:
        return "sensor"
    
    @property
    def modality_name(self) -> str:
        return "传感器分析"
    
    @property
    def description(self) -> str:
        return "分析传感器数据（心率、运动等）"
    
    @property
    def input_types(self) -> List[str]:
        return ["sensor_data"]
    
    @property
    def default_weight(self) -> float:
        return 0.15
    
    async def analyze(self, input_data: Dict[str, Any]) -> ModalityResult:
        sensor_data = input_data.get("sensor_data", {})
        
        if not sensor_data:
            return ModalityResult(
                modality_id=self.modality_id,
                modality_name=self.modality_name,
                success=False,
                data={},
                error="No sensor data"
            )
        
        heart_rate = sensor_data.get("heart_rate")
        motion = sensor_data.get("motion")
        
        result_data = {}
        confidence = 0.5
        
        if heart_rate:
            if heart_rate > 100:
                result_data["physiological_state"] = "excited"
            elif heart_rate < 60:
                result_data["physiological_state"] = "calm"
            else:
                result_data["physiological_state"] = "normal"
            result_data["heart_rate"] = heart_rate
            confidence += 0.2
        
        if motion:
            result_data["motion"] = motion
            confidence += 0.1
        
        return ModalityResult(
            modality_id=self.modality_id,
            modality_name=self.modality_name,
            success=True,
            data=result_data,
            confidence=min(confidence, 1.0)
        )


def create_default_plugins():
    """创建默认插件集合"""
    return [
        TextModalityPlugin(),
        VoiceModalityPlugin(),
        FaceModalityPlugin(),
        ImageModalityPlugin(),
        SensorModalityPlugin()
    ]
