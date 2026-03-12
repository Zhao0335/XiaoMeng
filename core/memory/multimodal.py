"""
多模态情感融合系统
完全按照完整实现指南实现

支持：
1. 文本情感分析
2. 语音情感分析
3. 表情识别
4. 多模态融合

参考：完整实现指南/高级阶段/阶段06_多模态情感系统.md
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from enum import Enum
from pathlib import Path
import json
import math


class ModalityType(Enum):
    """模态类型"""
    TEXT = "text"
    VOICE = "voice"
    VIDEO = "video"
    IMAGE = "image"


class EmotionType(Enum):
    """情感类型"""
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    NEUTRAL = "neutral"
    MIXED = "mixed"


@dataclass
class ModalityResult:
    """单模态分析结果"""
    modality: ModalityType
    emotion: EmotionType
    confidence: float
    intensity: float
    features: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "modality": self.modality.value,
            "emotion": self.emotion.value,
            "confidence": self.confidence,
            "intensity": self.intensity,
            "features": self.features,
            "description": self.description
        }


@dataclass
class FusedEmotionResult:
    """融合后的情感结果"""
    primary: EmotionType
    secondary: Optional[EmotionType]
    confidence: float
    intensity: float
    modality_contributions: Dict[str, float] = field(default_factory=dict)
    description: str = ""
    is_sarcastic: bool = False
    sarcasm_confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "primary": self.primary.value,
            "secondary": self.secondary.value if self.secondary else None,
            "confidence": self.confidence,
            "intensity": self.intensity,
            "modality_contributions": self.modality_contributions,
            "description": self.description,
            "is_sarcastic": self.is_sarcastic,
            "sarcasm_confidence": self.sarcasm_confidence
        }


class TextEmotionAnalyzer:
    """文本情感分析器"""
    
    EMOTION_KEYWORDS = {
        EmotionType.HAPPY: ["开心", "高兴", "快乐", "幸福", "棒", "好", "喜欢", "爱", "哈哈", "😊"],
        EmotionType.SAD: ["难过", "伤心", "悲伤", "哭", "泪", "郁闷", "不开心", "😢"],
        EmotionType.ANGRY: ["生气", "愤怒", "烦", "讨厌", "气死", "火大", "😠"],
        EmotionType.FEAR: ["害怕", "担心", "恐惧", "紧张", "焦虑", "不安"],
        EmotionType.SURPRISE: ["惊讶", "意外", "没想到", "居然", "竟然", "哇"],
        EmotionType.DISGUST: ["恶心", "讨厌", "反感", "厌恶"],
    }
    
    SARCASM_INDICATORS = [
        ("你真棒啊", "angry"),
        ("好极了", "sad"),
        ("真行", "angry"),
        ("厉害了", "neutral"),
    ]
    
    def analyze(self, text: str) -> ModalityResult:
        """分析文本情感"""
        scores = {}
        
        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            scores[emotion] = score
        
        intensity_modifiers = sum(1 for m in ["很", "非常", "特别", "超级"] if m in text)
        intensity = min(0.5 + intensity_modifiers * 0.15, 1.0)
        
        if max(scores.values()) == 0:
            return ModalityResult(
                modality=ModalityType.TEXT,
                emotion=EmotionType.NEUTRAL,
                confidence=0.5,
                intensity=intensity,
                description="中性情感"
            )
        
        best_emotion = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = scores[best_emotion] / total
        
        return ModalityResult(
            modality=ModalityType.TEXT,
            emotion=best_emotion,
            confidence=min(confidence, 1.0),
            intensity=intensity,
            description=f"文本情感：{best_emotion.value}"
        )
    
    def detect_sarcasm(self, text: str, emotion_result: ModalityResult) -> Tuple[bool, float]:
        """检测讽刺"""
        for phrase, actual_emotion in self.SARCASM_INDICATORS:
            if phrase in text and emotion_result.emotion != EmotionType[actual_emotion.upper()]:
                return True, 0.7
        
        positive_words = ["好", "棒", "厉害", "行"]
        negative_context = ["但是", "可是", "就是", "可惜"]
        
        has_positive = any(w in text for w in positive_words)
        has_negative_context = any(w in text for w in negative_context)
        
        if has_positive and has_negative_context:
            return True, 0.6
        
        return False, 0.0


class VoiceEmotionAnalyzer:
    """
    语音情感分析器
    
    基于音频特征分析情感：
    - 音高
    - 能量
    - 语速
    - 频谱特征
    """
    
    EMOTION_THRESHOLDS = {
        EmotionType.HAPPY: {"pitch_mean": (200, 400), "energy_mean": (0.3, 0.8), "tempo": (120, 180)},
        EmotionType.SAD: {"pitch_mean": (100, 200), "energy_mean": (0.1, 0.3), "tempo": (60, 100)},
        EmotionType.ANGRY: {"pitch_mean": (250, 500), "energy_mean": (0.5, 1.0), "tempo": (140, 200)},
        EmotionType.FEAR: {"pitch_mean": (200, 350), "energy_mean": (0.2, 0.5), "tempo": (100, 150)},
        EmotionType.NEUTRAL: {"pitch_mean": (150, 250), "energy_mean": (0.2, 0.5), "tempo": (90, 130)},
    }
    
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._librosa_available = self._check_librosa()
    
    def _check_librosa(self) -> bool:
        """检查 librosa 是否可用"""
        try:
            import librosa
            return True
        except ImportError:
            return False
    
    def analyze(self, audio_path: str = None, audio_data: bytes = None) -> ModalityResult:
        """分析语音情感"""
        if not self._librosa_available or (not audio_path and not audio_data):
            return ModalityResult(
                modality=ModalityType.VOICE,
                emotion=EmotionType.NEUTRAL,
                confidence=0.3,
                intensity=0.5,
                description="语音分析不可用"
            )
        
        try:
            import librosa
            import numpy as np
            
            if audio_path:
                y, sr = librosa.load(audio_path, sr=self.sample_rate)
            else:
                import io
                y, sr = librosa.load(io.BytesIO(audio_data), sr=self.sample_rate)
            
            pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
            pitch_values = pitches[magnitudes > np.median(magnitudes)]
            pitch_mean = np.mean(pitch_values) if len(pitch_values) > 0 else 200
            
            energy = librosa.feature.rms(y=y)[0]
            energy_mean = np.mean(energy)
            
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            
            features = {
                "pitch_mean": float(pitch_mean),
                "energy_mean": float(energy_mean),
                "tempo": float(tempo)
            }
            
            scores = {}
            for emotion, thresholds in self.EMOTION_THRESHOLDS.items():
                score = 0
                for feature, (low, high) in thresholds.items():
                    value = features.get(feature, 0)
                    if low <= value <= high:
                        score += 1
                scores[emotion] = score
            
            best_emotion = max(scores, key=scores.get)
            confidence = scores[best_emotion] / len(self.EMOTION_THRESHOLDS[best_emotion])
            
            intensity = min(energy_mean * 2, 1.0)
            
            return ModalityResult(
                modality=ModalityType.VOICE,
                emotion=best_emotion,
                confidence=confidence,
                intensity=intensity,
                features=features,
                description=f"语音情感：{best_emotion.value}"
            )
        
        except Exception as e:
            return ModalityResult(
                modality=ModalityType.VOICE,
                emotion=EmotionType.NEUTRAL,
                confidence=0.3,
                intensity=0.5,
                description=f"语音分析失败: {str(e)}"
            )


class FaceEmotionAnalyzer:
    """
    面部表情识别器
    
    基于视觉特征识别情感：
    - 使用 DeepFace 或类似模型
    - 支持图片和视频帧
    """
    
    def __init__(self):
        self._deepface_available = self._check_deepface()
    
    def _check_deepface(self) -> bool:
        """检查 DeepFace 是否可用"""
        try:
            from deepface import DeepFace
            return True
        except ImportError:
            return False
    
    def analyze(self, image_path: str = None, image_data: bytes = None) -> ModalityResult:
        """分析面部表情"""
        if not self._deepface_available or (not image_path and not image_data):
            return ModalityResult(
                modality=ModalityType.VIDEO,
                emotion=EmotionType.NEUTRAL,
                confidence=0.3,
                intensity=0.5,
                description="表情分析不可用"
            )
        
        try:
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
            
            emotion_map = {
                'happy': EmotionType.HAPPY,
                'sad': EmotionType.SAD,
                'angry': EmotionType.ANGRY,
                'fear': EmotionType.FEAR,
                'surprise': EmotionType.SURPRISE,
                'disgust': EmotionType.DISGUST,
                'neutral': EmotionType.NEUTRAL,
            }
            
            dominant_emotion = result.get('dominant_emotion', 'neutral')
            emotion = emotion_map.get(dominant_emotion, EmotionType.NEUTRAL)
            
            emotion_scores = result.get('emotion', {})
            confidence = emotion_scores.get(dominant_emotion, 50) / 100
            intensity = min(confidence * 1.2, 1.0)
            
            return ModalityResult(
                modality=ModalityType.VIDEO,
                emotion=emotion,
                confidence=confidence,
                intensity=intensity,
                features=emotion_scores,
                description=f"表情情感：{emotion.value}"
            )
        
        except Exception as e:
            return ModalityResult(
                modality=ModalityType.VIDEO,
                emotion=EmotionType.NEUTRAL,
                confidence=0.3,
                intensity=0.5,
                description=f"表情分析失败: {str(e)}"
            )


class MultimodalEmotionFusion:
    """
    多模态情感融合
    
    使用注意力机制融合不同模态的情感分析结果
    """
    
    DEFAULT_WEIGHTS = {
        ModalityType.TEXT: 0.4,
        ModalityType.VOICE: 0.35,
        ModalityType.VIDEO: 0.25,
    }
    
    def __init__(
        self,
        weights: Dict[ModalityType, float] = None,
        use_attention: bool = True
    ):
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.use_attention = use_attention
        
        self.text_analyzer = TextEmotionAnalyzer()
        self.voice_analyzer = VoiceEmotionAnalyzer()
        self.face_analyzer = FaceEmotionAnalyzer()
    
    def analyze(
        self,
        text: str = None,
        audio_path: str = None,
        audio_data: bytes = None,
        image_path: str = None,
        image_data: bytes = None
    ) -> FusedEmotionResult:
        """
        多模态情感分析
        
        Args:
            text: 文本内容
            audio_path: 音频文件路径
            audio_data: 音频二进制数据
            image_path: 图片文件路径
            image_data: 图片二进制数据
        
        Returns:
            融合后的情感结果
        """
        results = []
        
        if text:
            text_result = self.text_analyzer.analyze(text)
            results.append(text_result)
        
        if audio_path or audio_data:
            voice_result = self.voice_analyzer.analyze(audio_path, audio_data)
            results.append(voice_result)
        
        if image_path or image_data:
            face_result = self.face_analyzer.analyze(image_path, image_data)
            results.append(face_result)
        
        if not results:
            return FusedEmotionResult(
                primary=EmotionType.NEUTRAL,
                secondary=None,
                confidence=0.5,
                intensity=0.5,
                description="无输入数据"
            )
        
        return self._fuse_results(results, text)
    
    def _fuse_results(
        self, 
        results: List[ModalityResult],
        text: str = None
    ) -> FusedEmotionResult:
        """融合多模态结果"""
        if self.use_attention:
            weights = self._compute_attention_weights(results)
        else:
            weights = self.weights
        
        emotion_scores = {}
        total_weight = 0
        
        for result in results:
            modality_weight = weights.get(result.modality, 0.33)
            effective_weight = modality_weight * result.confidence
            
            if result.emotion not in emotion_scores:
                emotion_scores[result.emotion] = 0
            emotion_scores[result.emotion] += effective_weight
            total_weight += effective_weight
        
        if total_weight > 0:
            for emotion in emotion_scores:
                emotion_scores[emotion] /= total_weight
        
        sorted_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
        
        primary = sorted_emotions[0][0] if sorted_emotions else EmotionType.NEUTRAL
        secondary = sorted_emotions[1][0] if len(sorted_emotions) > 1 else None
        
        confidence = emotion_scores.get(primary, 0.5)
        
        intensity = sum(r.intensity * weights.get(r.modality, 0.33) for r in results)
        intensity /= len(results) if results else 1
        
        contributions = {
            r.modality.value: weights.get(r.modality, 0.33) * r.confidence
            for r in results
        }
        
        is_sarcastic = False
        sarcasm_confidence = 0.0
        if text:
            text_result = next((r for r in results if r.modality == ModalityType.TEXT), None)
            if text_result:
                is_sarcastic, sarcasm_confidence = self.text_analyzer.detect_sarcasm(text, text_result)
        
        description = self._generate_description(primary, secondary, is_sarcastic, results)
        
        return FusedEmotionResult(
            primary=primary,
            secondary=secondary,
            confidence=confidence,
            intensity=intensity,
            modality_contributions=contributions,
            description=description,
            is_sarcastic=is_sarcastic,
            sarcasm_confidence=sarcasm_confidence
        )
    
    def _compute_attention_weights(self, results: List[ModalityResult]) -> Dict[ModalityType, float]:
        """计算注意力权重"""
        confidences = {r.modality: r.confidence for r in results}
        
        total = sum(confidences.values()) or 1
        
        attention_weights = {}
        for modality, conf in confidences.items():
            base_weight = self.weights.get(modality, 0.33)
            attention_weights[modality] = base_weight * (conf / total) * len(results)
        
        weight_sum = sum(attention_weights.values()) or 1
        for modality in attention_weights:
            attention_weights[modality] /= weight_sum
        
        return attention_weights
    
    def _generate_description(
        self,
        primary: EmotionType,
        secondary: Optional[EmotionType],
        is_sarcastic: bool,
        results: List[ModalityResult]
    ) -> str:
        """生成描述"""
        emotion_names = {
            EmotionType.HAPPY: "开心",
            EmotionType.SAD: "难过",
            EmotionType.ANGRY: "生气",
            EmotionType.FEAR: "害怕",
            EmotionType.SURPRISE: "惊讶",
            EmotionType.DISGUST: "厌恶",
            EmotionType.NEUTRAL: "中性",
        }
        
        parts = [f"主要情感：{emotion_names.get(primary, '未知')}"]
        
        if secondary:
            parts.append(f"次要情感：{emotion_names.get(secondary, '未知')}")
        
        if is_sarcastic:
            parts.append("检测到讽刺/反话")
        
        modalities = [r.modality.value for r in results]
        parts.append(f"分析模态：{', '.join(modalities)}")
        
        return " | ".join(parts)


def create_emotion_fusion(
    text_weight: float = 0.4,
    voice_weight: float = 0.35,
    video_weight: float = 0.25,
    use_attention: bool = True
) -> MultimodalEmotionFusion:
    """创建多模态情感融合实例"""
    weights = {
        ModalityType.TEXT: text_weight,
        ModalityType.VOICE: voice_weight,
        ModalityType.VIDEO: video_weight,
    }
    return MultimodalEmotionFusion(weights=weights, use_attention=use_attention)
