"""
Transformer 语义识别模块
完全按照完整实现指南实现

包含：
1. 意图识别器
2. 情感分析器
3. 实体提取器
4. 重要性评估器

参考：完整实现指南/进阶阶段/阶段02_高级记忆系统.md
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from enum import Enum
import re
import json


class IntentType(Enum):
    """意图类型"""
    REMEMBER = "remember"
    RECALL = "recall"
    QUESTION = "question"
    CHAT = "chat"
    COMMAND = "command"
    EMOTION_SHARE = "emotion_share"
    COMPLAINT = "complaint"
    GRATITUDE = "gratitude"
    GREETING = "greeting"
    FAREWELL = "farewell"


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
    EXCITED = "excited"
    WORRIED = "worried"
    PROUD = "proud"
    GRATEFUL = "grateful"
    LONELY = "lonely"


@dataclass
class IntentResult:
    """意图识别结果"""
    intent: IntentType
    confidence: float
    all_probs: Dict[str, float] = field(default_factory=dict)


@dataclass
class EmotionResult:
    """情感分析结果"""
    primary: EmotionType
    confidence: float
    intensity: float
    secondary: Optional[EmotionType] = None
    description: str = ""
    probabilities: Dict[str, float] = field(default_factory=dict)


@dataclass
class Entity:
    """实体"""
    text: str
    type: str
    start: int
    end: int
    
    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "type": self.type,
            "start": self.start,
            "end": self.end
        }


@dataclass
class SemanticAnalysis:
    """语义分析结果"""
    intent: IntentResult
    emotion: EmotionResult
    entities: List[Entity]
    importance: float
    relations: List[Dict]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "intent": {
                "type": self.intent.intent.value,
                "confidence": self.intent.confidence
            },
            "emotion": {
                "primary": self.emotion.primary.value,
                "intensity": self.emotion.intensity,
                "description": self.emotion.description
            },
            "entities": [e.to_dict() for e in self.entities],
            "importance": self.importance,
            "relations": self.relations,
            "timestamp": self.timestamp.isoformat()
        }


class IntentRecognizer:
    """
    意图识别器
    
    支持两种模式：
    1. 基于规则的快速识别（默认）
    2. 基于 Transformer 模型的深度识别（可选）
    """
    
    INTENT_PATTERNS = {
        IntentType.REMEMBER: [
            r"记住|记得|别忘|不要忘|帮我记",
            r"重要|关键|必须",
            r"提醒我",
        ],
        IntentType.RECALL: [
            r"记得吗|还记得吗|想起来",
            r"上次|之前|以前",
            r"我们说过|我们聊过",
        ],
        IntentType.QUESTION: [
            r"什么|怎么|为什么|如何|哪里|谁",
            r"吗\?|吗？$",
            r"能不能|可以不可以",
        ],
        IntentType.COMMAND: [
            r"帮我|给我|帮我做|执行",
            r"打开|关闭|启动|停止",
            r"设置|修改|删除",
        ],
        IntentType.EMOTION_SHARE: [
            r"我好|我很|我觉得",
            r"开心|难过|生气|担心",
            r"分享|告诉",
        ],
        IntentType.COMPLAINT: [
            r"烦死了|讨厌|气死",
            r"受不了|崩溃",
            r"怎么这么|为什么总是",
        ],
        IntentType.GRATITUDE: [
            r"谢谢|感谢|多谢",
            r"太棒了|太好了",
            r"你真好",
        ],
        IntentType.GREETING: [
            r"你好|嗨|哈喽|早上好|晚上好",
            r"在吗|在不在",
        ],
        IntentType.FAREWELL: [
            r"再见|拜拜|晚安",
            r"我先走了|下次聊",
        ],
    }
    
    def __init__(self, use_transformer: bool = False, model_name: str = None):
        self.use_transformer = use_transformer
        self.model = None
        self.tokenizer = None
        
        if use_transformer and model_name:
            self._init_transformer(model_name)
    
    def _init_transformer(self, model_name: str):
        """初始化 Transformer 模型"""
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                model_name,
                num_labels=len(IntentType)
            )
            self.model.to(self.device)
            self.model.eval()
        except ImportError:
            self.use_transformer = False
    
    def recognize(self, text: str) -> IntentResult:
        """识别意图"""
        if self.use_transformer and self.model:
            return self._recognize_with_transformer(text)
        return self._recognize_with_rules(text)
    
    def _recognize_with_rules(self, text: str) -> IntentResult:
        """基于规则的意图识别"""
        scores = {}
        
        for intent_type, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, text)
                score += len(matches)
            scores[intent_type.value] = score
        
        total = sum(scores.values()) or 1
        probs = {k: v / total for k, v in scores.items()}
        
        if max(scores.values()) == 0:
            return IntentResult(
                intent=IntentType.CHAT,
                confidence=0.5,
                all_probs={"chat": 0.5}
            )
        
        best_intent = max(scores, key=scores.get)
        confidence = scores[best_intent] / total
        
        return IntentResult(
            intent=IntentType(best_intent),
            confidence=min(confidence, 1.0),
            all_probs=probs
        )
    
    def _recognize_with_transformer(self, text: str) -> IntentResult:
        """基于 Transformer 的意图识别"""
        import torch
        
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=128
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
        
        pred_idx = torch.argmax(probs, dim=-1).item()
        confidence = probs[0][pred_idx].item()
        
        intent_labels = [t.value for t in IntentType]
        
        return IntentResult(
            intent=IntentType(intent_labels[pred_idx]),
            confidence=confidence,
            all_probs={
                intent_labels[i]: probs[0][i].item()
                for i in range(len(intent_labels))
            }
        )


class EmotionAnalyzer:
    """
    情感分析器
    
    支持两种模式：
    1. 基于关键词和规则的快速分析（默认）
    2. 基于 Transformer 模型的深度分析（可选）
    """
    
    EMOTION_KEYWORDS = {
        EmotionType.HAPPY: ["开心", "高兴", "快乐", "幸福", "棒", "好", "喜欢", "爱", "哈哈", "嘻嘻", "😊", "😄"],
        EmotionType.SAD: ["难过", "伤心", "悲伤", "哭", "泪", "郁闷", "不开心", "😢", "😭"],
        EmotionType.ANGRY: ["生气", "愤怒", "烦", "讨厌", "气死", "火大", "恼火", "😠", "😡"],
        EmotionType.FEAR: ["害怕", "担心", "恐惧", "紧张", "焦虑", "不安", "😨", "😰"],
        EmotionType.SURPRISE: ["惊讶", "意外", "没想到", "居然", "竟然", "哇", "😲", "🤯"],
        EmotionType.EXCITED: ["兴奋", "激动", "期待", "迫不及待", "太棒了", "🎉", "🥳"],
        EmotionType.WORRIED: ["担心", "忧虑", "发愁", "纠结", "迷茫", "😟", "🤔"],
        EmotionType.GRATEFUL: ["感谢", "谢谢", "感激", "感恩", "多谢", "🙏", "❤️"],
        EmotionType.LONELY: ["孤独", "寂寞", "孤单", "没人", "一个人", "😢"],
    }
    
    INTENSITY_BOOSTERS = ["很", "非常", "特别", "超级", "极其", "太", "真的"]
    INTENSITY_REDUCERS = ["有点", "稍微", "一点", "还算"]
    
    def __init__(self, use_transformer: bool = False, model_name: str = None):
        self.use_transformer = use_transformer
        self.model = None
        self.tokenizer = None
        
        if use_transformer and model_name:
            self._init_transformer(model_name)
    
    def _init_transformer(self, model_name: str):
        """初始化 Transformer 模型"""
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
        except ImportError:
            self.use_transformer = False
    
    def analyze(self, text: str) -> EmotionResult:
        """分析情感"""
        if self.use_transformer and self.model:
            return self._analyze_with_transformer(text)
        return self._analyze_with_rules(text)
    
    def _analyze_with_rules(self, text: str) -> EmotionResult:
        """基于规则的情感分析"""
        scores = {}
        
        for emotion_type, keywords in self.EMOTION_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in text:
                    score += 1
            scores[emotion_type] = score
        
        intensity = 0.5
        for booster in self.INTENSITY_BOOSTERS:
            if booster in text:
                intensity = min(intensity + 0.15, 1.0)
        for reducer in self.INTENSITY_REDUCERS:
            if reducer in text:
                intensity = max(intensity - 0.15, 0.1)
        
        if max(scores.values()) == 0:
            return EmotionResult(
                primary=EmotionType.NEUTRAL,
                confidence=0.5,
                intensity=intensity,
                description="中性情感"
            )
        
        sorted_emotions = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_emotions[0][0]
        secondary = sorted_emotions[1][0] if len(sorted_emotions) > 1 and sorted_emotions[1][1] > 0 else None
        
        total = sum(scores.values())
        confidence = scores[primary] / total
        
        description = self._generate_description(primary, intensity)
        
        return EmotionResult(
            primary=primary,
            confidence=min(confidence, 1.0),
            intensity=intensity,
            secondary=secondary,
            description=description,
            probabilities={e.value: s / total for e, s in scores.items()}
        )
    
    def _analyze_with_transformer(self, text: str) -> EmotionResult:
        """基于 Transformer 的情感分析"""
        import torch
        import numpy as np
        
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
        
        pred_class = torch.argmax(probs, dim=-1).item()
        confidence = probs[0][pred_class].item()
        
        entropy = -torch.sum(probs * torch.log(probs + 1e-10)).item()
        intensity = 1 - (entropy / np.log(probs.shape[1]))
        
        emotion_labels = {i: e.value for i, e in enumerate(EmotionType)}
        primary = EmotionType(emotion_labels.get(pred_class, "neutral"))
        
        return EmotionResult(
            primary=primary,
            confidence=confidence,
            intensity=intensity,
            description=self._generate_description(primary, intensity)
        )
    
    def _generate_description(self, emotion: EmotionType, intensity: float) -> str:
        """生成情感描述"""
        intensity_desc = "轻微" if intensity < 0.3 else "中等" if intensity < 0.7 else "强烈"
        emotion_names = {
            EmotionType.HAPPY: "开心",
            EmotionType.SAD: "难过",
            EmotionType.ANGRY: "生气",
            EmotionType.FEAR: "害怕",
            EmotionType.SURPRISE: "惊讶",
            EmotionType.NEUTRAL: "中性",
            EmotionType.EXCITED: "兴奋",
            EmotionType.WORRIED: "担心",
            EmotionType.GRATEFUL: "感激",
            EmotionType.LONELY: "孤独",
        }
        return f"{intensity_desc}的{emotion_names.get(emotion, '未知')}情绪"


class EntityExtractor:
    """
    实体提取器
    
    提取文本中的：
    - 人物
    - 时间
    - 地点
    - 事件
    """
    
    ENTITY_PATTERNS = {
        "person": [
            r"我|你|他|她|它|我们|你们|他们",
            r"[\u4e00-\u9fa5]{2,4}(?=说|做|去|来|是|有)",
            r"主人|小萌|爸爸|妈妈|哥哥|姐姐|弟弟|妹妹|老师|同学|朋友",
        ],
        "time": [
            r"\d{4}年\d{1,2}月\d{1,2}日?",
            r"\d{1,2}月\d{1,2}日?",
            r"今天|明天|后天|昨天|前天|大后天",
            r"上午|下午|晚上|早上|中午|傍晚|深夜",
            r"\d{1,2}点\d{0,2}分?",
            r"周末|工作日|节假日",
        ],
        "location": [
            r"[在到去从][\u4e00-\u9fa5]{2,10}",
            r"家|学校|公司|图书馆|食堂|宿舍|医院|超市|公园",
        ],
        "event": [
            r"(论文|考试|面试|会议|约会|聚餐|旅行|活动)",
            r"(吃饭|睡觉|学习|工作|运动|游戏|看电影|逛街)",
            r"(生日|纪念日|节日|假期)",
        ],
    }
    
    def extract(self, text: str) -> List[Entity]:
        """提取实体"""
        entities = []
        
        for entity_type, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text):
                    entities.append(Entity(
                        text=match.group(),
                        type=entity_type,
                        start=match.start(),
                        end=match.end()
                    ))
        
        entities = self._remove_duplicates(entities)
        
        return entities
    
    def _remove_duplicates(self, entities: List[Entity]) -> List[Entity]:
        """去除重叠的实体"""
        if not entities:
            return []
        
        entities.sort(key=lambda e: (e.start, -len(e.text)))
        
        result = []
        last_end = -1
        
        for entity in entities:
            if entity.start >= last_end:
                result.append(entity)
                last_end = entity.end
        
        return result
    
    def extract_relations(self, text: str, entities: List[Entity]) -> List[Dict]:
        """提取实体间关系"""
        relations = []
        
        persons = [e for e in entities if e.type == "person"]
        events = [e for e in entities if e.type == "event"]
        times = [e for e in entities if e.type == "time"]
        locations = [e for e in entities if e.type == "location"]
        
        for person in persons:
            for event in events:
                relations.append({
                    "subject": person.text,
                    "relation": "参与",
                    "object": event.text,
                    "type": "person_event"
                })
            
            for location in locations:
                relations.append({
                    "subject": person.text,
                    "relation": "位于",
                    "object": location.text,
                    "type": "person_location"
                })
        
        for event in events:
            for time in times:
                relations.append({
                    "subject": event.text,
                    "relation": "发生时间",
                    "object": time.text,
                    "type": "event_time"
                })
        
        return relations


class ImportanceScorer:
    """
    重要性评估器
    
    评估消息的重要性，决定是否需要长期存储
    """
    
    IMPORTANCE_KEYWORDS = [
        "重要", "记住", "别忘", "关键", "必须",
        "论文", "考试", "面试", "生日", "纪念日",
        "开心", "难过", "生气", "感谢", "对不起",
        "决定", "选择", "计划", "目标",
    ]
    
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
    
    def score(
        self, 
        text: str, 
        emotion: EmotionResult = None,
        intent: IntentResult = None
    ) -> float:
        """
        计算重要性分数
        
        综合考虑：
        1. 关键词匹配
        2. 情感强度
        3. 意图类型
        """
        keyword_score = self._keyword_score(text)
        
        emotion_score = 0.5
        if emotion:
            emotion_score = emotion.intensity
            if emotion.primary in [EmotionType.HAPPY, EmotionType.SAD, EmotionType.ANGRY]:
                emotion_score *= 1.2
        
        intent_score = 0.5
        if intent:
            if intent.intent in [IntentType.REMEMBER, IntentType.EMOTION_SHARE]:
                intent_score = 0.9
            elif intent.intent in [IntentType.COMMAND, IntentType.QUESTION]:
                intent_score = 0.7
            elif intent.intent in [IntentType.GREETING, IntentType.FAREWELL]:
                intent_score = 0.3
        
        importance = (
            0.4 * keyword_score +
            0.3 * emotion_score +
            0.3 * intent_score
        )
        
        return min(importance, 1.0)
    
    def _keyword_score(self, text: str) -> float:
        """基于关键词的重要性评分"""
        matches = sum(1 for kw in self.IMPORTANCE_KEYWORDS if kw in text)
        return min(matches / 5, 1.0)


class SemanticAnalyzer:
    """
    语义分析器
    
    整合意图识别、情感分析、实体提取和重要性评估
    """
    
    def __init__(
        self,
        use_transformer: bool = False,
        intent_model: str = None,
        emotion_model: str = None,
        llm_client=None
    ):
        self.intent_recognizer = IntentRecognizer(
            use_transformer=use_transformer,
            model_name=intent_model
        )
        self.emotion_analyzer = EmotionAnalyzer(
            use_transformer=use_transformer,
            model_name=emotion_model
        )
        self.entity_extractor = EntityExtractor()
        self.importance_scorer = ImportanceScorer(llm_client)
    
    def analyze(self, text: str) -> SemanticAnalysis:
        """完整语义分析"""
        intent = self.intent_recognizer.recognize(text)
        emotion = self.emotion_analyzer.analyze(text)
        entities = self.entity_extractor.extract(text)
        relations = self.entity_extractor.extract_relations(text, entities)
        importance = self.importance_scorer.score(text, emotion, intent)
        
        return SemanticAnalysis(
            intent=intent,
            emotion=emotion,
            entities=entities,
            importance=importance,
            relations=relations
        )
    
    def quick_analyze(self, text: str) -> Dict:
        """快速分析（仅返回关键信息）"""
        intent = self.intent_recognizer.recognize(text)
        emotion = self.emotion_analyzer.analyze(text)
        importance = self.importance_scorer.score(text, emotion, intent)
        
        return {
            "intent": intent.intent.value,
            "emotion": emotion.primary.value,
            "intensity": emotion.intensity,
            "importance": importance
        }
