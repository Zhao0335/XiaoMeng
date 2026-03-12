"""
XiaoMengCore 个性化适应系统
学习用户偏好、沟通风格、兴趣爱好等
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import re
from collections import Counter
import math


class PreferenceCategory(Enum):
    COMMUNICATION_STYLE = "communication_style"
    INTERESTS = "interests"
    SCHEDULE = "schedule"
    VOCABULARY = "vocabulary"
    EMOTIONAL_PATTERNS = "emotional_patterns"
    TOPIC_PREFERENCES = "topic_preferences"
    RESPONSE_LENGTH = "response_length"
    FORMALITY = "formality"


@dataclass
class UserPreferenceItem:
    category: PreferenceCategory
    key: str
    value: Any
    confidence: float = 0.5
    source: str = "learned"
    last_updated: datetime = field(default_factory=datetime.now)
    update_count: int = 1


@dataclass
class UserProfile:
    user_id: str
    nickname: str = "主人"
    preferred_name: Optional[str] = None
    
    communication_style: str = "warm"
    formality_level: float = 0.3
    response_length_preference: str = "medium"
    
    interests: List[str] = field(default_factory=list)
    dislikes: List[str] = field(default_factory=list)
    
    preferred_greeting: str = "默认"
    preferred_ending: str = "默认"
    
    active_hours: Dict[str, List[int]] = field(default_factory=lambda: {
        "weekday": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22],
        "weekend": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
    })
    
    emotional_baseline: Dict[str, float] = field(default_factory=lambda: {
        "happy": 0.3,
        "neutral": 0.5,
        "sad": 0.1,
        "angry": 0.05,
        "excited": 0.05
    })
    
    frequently_used_words: Dict[str, int] = field(default_factory=dict)
    topic_engagement: Dict[str, float] = field(default_factory=dict)
    
    learned_preferences: Dict[str, UserPreferenceItem] = field(default_factory=dict)


class PersonalizationEngine:
    """
    个性化适应引擎
    
    功能：
    1. 学习用户沟通风格
    2. 记录用户兴趣爱好
    3. 分析用户活跃时间
    4. 学习用户情感模式
    5. 适应回复长度和正式程度
    """
    
    def __init__(self, user_id: str = "default"):
        self._profile = UserProfile(user_id=user_id)
        self._interaction_history: List[Dict] = []
        self._max_history = 1000
        self._learning_rate = 0.1
        
        self._style_keywords = {
            "formal": ["请", "谢谢", "麻烦", "劳驾", "请问", "您好"],
            "casual": ["哈", "呀", "呢", "吧", "嘛", "啦", "哦"],
            "cute": ["~", "（", "）", "｡", "･", "ω", "･", "｡"],
            "direct": ["直接", "简单", "快点", "别废话"]
        }
        
        self._interest_keywords = {
            "technology": ["代码", "编程", "AI", "机器学习", "程序", "开发", "技术"],
            "academic": ["论文", "研究", "学术", "期刊", "实验", "数据"],
            "entertainment": ["游戏", "电影", "音乐", "动漫", "小说", "追剧"],
            "sports": ["运动", "健身", "跑步", "篮球", "足球", "游泳"],
            "food": ["美食", "做饭", "餐厅", "菜谱", "好吃"],
            "travel": ["旅游", "旅行", "景点", "出门", "度假"],
            "work": ["工作", "项目", "会议", "报告", "任务"],
            "life": ["生活", "日常", "家里", "朋友", "家人"]
        }
    
    def get_profile(self) -> UserProfile:
        return self._profile
    
    def record_interaction(self, user_message: str, response: str, 
                           emotion: Optional[str] = None,
                           topic: Optional[str] = None):
        interaction = {
            "timestamp": datetime.now(),
            "user_message": user_message,
            "response": response,
            "emotion": emotion,
            "topic": topic,
            "hour": datetime.now().hour,
            "is_weekend": datetime.now().weekday() >= 5
        }
        
        self._interaction_history.append(interaction)
        
        if len(self._interaction_history) > self._max_history:
            self._interaction_history = self._interaction_history[-self._max_history:]
        
        self._learn_from_interaction(interaction)
    
    def _learn_from_interaction(self, interaction: Dict):
        user_message = interaction.get("user_message", "")
        
        self._learn_communication_style(user_message)
        self._learn_interests(user_message)
        self._learn_active_hours(interaction)
        self._learn_vocabulary(user_message)
        
        if interaction.get("emotion"):
            self._learn_emotional_pattern(interaction["emotion"])
        
        if interaction.get("topic"):
            self._learn_topic_engagement(interaction["topic"])
    
    def _learn_communication_style(self, message: str):
        style_scores = {}
        
        for style, keywords in self._style_keywords.items():
            score = sum(1 for kw in keywords if kw in message) / len(keywords)
            style_scores[style] = score
        
        if style_scores.get("formal", 0) > 0.1:
            self._update_preference(
                PreferenceCategory.COMMUNICATION_STYLE,
                "formality",
                min(1.0, self._profile.formality_level + self._learning_rate)
            )
        
        if style_scores.get("casual", 0) > 0.1:
            self._update_preference(
                PreferenceCategory.COMMUNICATION_STYLE,
                "formality",
                max(0.0, self._profile.formality_level - self._learning_rate)
            )
        
        if style_scores.get("cute", 0) > 0.1:
            self._profile.communication_style = "cute"
        
        if style_scores.get("direct", 0) > 0.1:
            self._profile.communication_style = "direct"
            self._update_preference(
                PreferenceCategory.RESPONSE_LENGTH,
                "preference",
                "short"
            )
    
    def _learn_interests(self, message: str):
        for interest, keywords in self._interest_keywords.items():
            if any(kw in message for kw in keywords):
                if interest not in self._profile.interests:
                    self._profile.interests.append(interest)
                    self._update_preference(
                        PreferenceCategory.INTERESTS,
                        interest,
                        True
                    )
    
    def _learn_active_hours(self, interaction: Dict):
        hour = interaction.get("hour")
        is_weekend = interaction.get("is_weekend", False)
        
        key = "weekend" if is_weekend else "weekday"
        if hour not in self._profile.active_hours[key]:
            self._profile.active_hours[key].append(hour)
            self._profile.active_hours[key].sort()
    
    def _learn_vocabulary(self, message: str):
        words = re.findall(r'[\u4e00-\u9fa5]+', message)
        for word in words:
            if len(word) >= 2:
                self._profile.frequently_used_words[word] = \
                    self._profile.frequently_used_words.get(word, 0) + 1
    
    def _learn_emotional_pattern(self, emotion: str):
        if emotion in self._profile.emotional_baseline:
            current = self._profile.emotional_baseline[emotion]
            self._profile.emotional_baseline[emotion] = \
                current + self._learning_rate * (1 - current)
            
            for other_emotion in self._profile.emotional_baseline:
                if other_emotion != emotion:
                    self._profile.emotional_baseline[other_emotion] *= (1 - self._learning_rate * 0.5)
    
    def _learn_topic_engagement(self, topic: str):
        if topic not in self._profile.topic_engagement:
            self._profile.topic_engagement[topic] = 0.5
        
        self._profile.topic_engagement[topic] = min(
            1.0, 
            self._profile.topic_engagement[topic] + self._learning_rate
        )
    
    def _update_preference(self, category: PreferenceCategory, key: str, value: Any):
        pref_key = f"{category.value}:{key}"
        
        if pref_key in self._profile.learned_preferences:
            pref = self._profile.learned_preferences[pref_key]
            pref.value = value
            pref.confidence = min(1.0, pref.confidence + 0.1)
            pref.last_updated = datetime.now()
            pref.update_count += 1
        else:
            self._profile.learned_preferences[pref_key] = UserPreferenceItem(
                category=category,
                key=key,
                value=value,
                confidence=0.5
            )
    
    def adapt_response(self, response: str, context: Optional[Dict] = None) -> str:
        if not response:
            return response
        
        style = self._profile.communication_style
        formality = self._profile.formality_level
        
        if style == "cute" or formality < 0.3:
            if not response.endswith("~") and not response.endswith("！"):
                if response.endswith("。"):
                    response = response[:-1] + "~"
                elif response.endswith("。"):
                    response = response[:-1] + "~"
                else:
                    response = response + "~"
        
        if style == "direct":
            sentences = response.split("。")
            if len(sentences) > 3:
                response = "。".join(sentences[:2]) + "。"
        
        nickname = self._profile.preferred_name or self._profile.nickname
        if "主人" in response and nickname != "主人":
            response = response.replace("主人", nickname)
        
        return response
    
    def get_personalized_greeting(self) -> str:
        hour = datetime.now().hour
        style = self._profile.communication_style
        
        if 5 <= hour < 12:
            base = "早上好"
        elif 12 <= hour < 18:
            base = "下午好"
        else:
            base = "晚上好"
        
        nickname = self._profile.preferred_name or self._profile.nickname
        
        if style == "cute":
            return f"{nickname}~ {base}呀(｡･ω･｡)"
        elif style == "formal":
            return f"{nickname}，{base}。"
        else:
            return f"{nickname}~ {base}~"
    
    def suggest_topics(self) -> List[str]:
        interests = self._profile.interests[:5]
        
        sorted_topics = sorted(
            self._profile.topic_engagement.items(),
            key=lambda x: x[1],
            reverse=True
        )
        high_engagement = [t[0] for t in sorted_topics[:3]]
        
        return list(set(interests + high_engagement))[:5]
    
    def get_user_summary(self) -> Dict:
        return {
            "nickname": self._profile.nickname,
            "preferred_name": self._profile.preferred_name,
            "communication_style": self._profile.communication_style,
            "formality_level": round(self._profile.formality_level, 2),
            "top_interests": self._profile.interests[:5],
            "active_hours": self._profile.active_hours,
            "emotional_baseline": self._profile.emotional_baseline,
            "top_words": dict(Counter(self._profile.frequently_used_words).most_common(10)),
            "learned_preferences_count": len(self._profile.learned_preferences)
        }
    
    def set_preference(self, key: str, value: Any):
        if key == "nickname":
            self._profile.nickname = value
        elif key == "preferred_name":
            self._profile.preferred_name = value
        elif key == "communication_style":
            self._profile.communication_style = value
        elif key == "formality_level":
            self._profile.formality_level = float(value)
        elif key == "response_length":
            self._profile.response_length_preference = value
    
    def load_profile(self, data: Dict):
        if "nickname" in data:
            self._profile.nickname = data["nickname"]
        if "preferred_name" in data:
            self._profile.preferred_name = data["preferred_name"]
        if "communication_style" in data:
            self._profile.communication_style = data["communication_style"]
        if "formality_level" in data:
            self._profile.formality_level = data["formality_level"]
        if "interests" in data:
            self._profile.interests = data["interests"]
        if "active_hours" in data:
            self._profile.active_hours = data["active_hours"]
        if "emotional_baseline" in data:
            self._profile.emotional_baseline = data["emotional_baseline"]
        if "frequently_used_words" in data:
            self._profile.frequently_used_words = data["frequently_used_words"]
        if "topic_engagement" in data:
            self._profile.topic_engagement = data["topic_engagement"]
    
    def export_profile(self) -> Dict:
        return {
            "user_id": self._profile.user_id,
            "nickname": self._profile.nickname,
            "preferred_name": self._profile.preferred_name,
            "communication_style": self._profile.communication_style,
            "formality_level": self._profile.formality_level,
            "response_length_preference": self._profile.response_length_preference,
            "interests": self._profile.interests,
            "dislikes": self._profile.dislikes,
            "active_hours": self._profile.active_hours,
            "emotional_baseline": self._profile.emotional_baseline,
            "frequently_used_words": dict(
                Counter(self._profile.frequently_used_words).most_common(100)
            ),
            "topic_engagement": self._profile.topic_engagement
        }
