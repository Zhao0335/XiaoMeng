"""
XiaoMengCore 实时信息获取系统
支持天气查询、新闻获取、汇率查询等功能
"""

import asyncio
import aiohttp
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import re


class InfoType(Enum):
    WEATHER = "weather"
    NEWS = "news"
    EXCHANGE_RATE = "exchange_rate"
    STOCK = "stock"
    HOLIDAY = "holiday"
    AIR_QUALITY = "air_quality"


@dataclass
class WeatherInfo:
    city: str
    temperature: float
    feels_like: float
    humidity: int
    wind_speed: float
    wind_direction: str
    weather: str
    weather_code: str
    visibility: float
    pressure: float
    uv_index: Optional[float] = None
    air_quality: Optional[str] = None
    sunrise: Optional[str] = None
    sunset: Optional[str] = None
    forecast: List[Dict] = field(default_factory=list)
    tips: List[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "city": self.city,
            "temperature": self.temperature,
            "feels_like": self.feels_like,
            "humidity": self.humidity,
            "wind_speed": self.wind_speed,
            "wind_direction": self.wind_direction,
            "weather": self.weather,
            "weather_code": self.weather_code,
            "visibility": self.visibility,
            "pressure": self.pressure,
            "uv_index": self.uv_index,
            "air_quality": self.air_quality,
            "sunrise": self.sunrise,
            "sunset": self.sunset,
            "forecast": self.forecast,
            "tips": self.tips,
            "updated_at": self.updated_at.isoformat()
        }
    
    def get_brief(self) -> str:
        return f"{self.city}：{self.weather}，{self.temperature}°C，湿度{self.humidity}%"


@dataclass
class NewsItem:
    title: str
    summary: str
    source: str
    url: str
    published_at: datetime
    category: str = "general"
    image_url: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "category": self.category,
            "image_url": self.image_url
        }


@dataclass
class ExchangeRate:
    from_currency: str
    to_currency: str
    rate: float
    updated_at: datetime
    
    def to_dict(self) -> Dict:
        return {
            "from_currency": self.from_currency,
            "to_currency": self.to_currency,
            "rate": self.rate,
            "updated_at": self.updated_at.isoformat()
        }


class RealtimeInfoService:
    """
    实时信息服务
    
    功能：
    1. 天气查询
    2. 新闻获取
    3. 汇率查询
    4. 节假日查询
    5. 空气质量查询
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self._config = config or {}
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = {
            "weather": 30 * 60,
            "news": 60 * 60,
            "exchange": 60 * 60,
        }
        self._weather_api_key = self._config.get("weather_api_key", "")
        self._news_api_key = self._config.get("news_api_key", "")
        self._default_city = self._config.get("default_city", "北京")
    
    async def _fetch(self, url: str, params: Dict = None, headers: Dict = None) -> Optional[Dict]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            print(f"Fetch error: {e}")
        return None
    
    def _is_cache_valid(self, cache_key: str, info_type: str) -> bool:
        if cache_key not in self._cache:
            return False
        
        cached = self._cache[cache_key]
        ttl = self._cache_ttl.get(info_type, 3600)
        
        return (datetime.now() - cached["timestamp"]).total_seconds() < ttl
    
    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        if cache_key in self._cache:
            return self._cache[cache_key]["data"]
        return None
    
    def _set_cache(self, cache_key: str, data: Any):
        self._cache[cache_key] = {
            "data": data,
            "timestamp": datetime.now()
        }
    
    async def get_weather(self, city: Optional[str] = None) -> Optional[WeatherInfo]:
        target_city = city or self._default_city
        cache_key = f"weather_{target_city}"
        
        if self._is_cache_valid(cache_key, "weather"):
            return self._get_from_cache(cache_key)
        
        if self._weather_api_key:
            weather = await self._fetch_weather_api(target_city)
        else:
            weather = await self._fetch_weather_free(target_city)
        
        if weather:
            self._set_cache(cache_key, weather)
        
        return weather
    
    async def _fetch_weather_api(self, city: str) -> Optional[WeatherInfo]:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": self._weather_api_key,
            "units": "metric",
            "lang": "zh_cn"
        }
        
        data = await self._fetch(url, params)
        if not data:
            return None
        
        weather_code = data["weather"][0]["id"]
        weather_desc = data["weather"][0]["description"]
        
        tips = self._generate_weather_tips(
            data["main"]["temp"],
            data["main"]["humidity"],
            weather_code
        )
        
        return WeatherInfo(
            city=city,
            temperature=data["main"]["temp"],
            feels_like=data["main"]["feels_like"],
            humidity=data["main"]["humidity"],
            wind_speed=data["wind"]["speed"],
            wind_direction=self._deg_to_direction(data["wind"].get("deg", 0)),
            weather=weather_desc,
            weather_code=str(weather_code),
            visibility=data.get("visibility", 10000) / 1000,
            pressure=data["main"]["pressure"],
            tips=tips
        )
    
    async def _fetch_weather_free(self, city: str) -> Optional[WeatherInfo]:
        url = "https://wttr.in"
        params = {
            "format": "j1",
            "lang": "zh"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                url_with_city = f"{url}/{city}"
                async with session.get(url_with_city, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        current = data.get("current_condition", [{}])[0]
                        
                        return WeatherInfo(
                            city=city,
                            temperature=float(current.get("temp_C", 0)),
                            feels_like=float(current.get("FeelsLikeC", 0)),
                            humidity=int(current.get("humidity", 0)),
                            wind_speed=float(current.get("windspeedKmph", 0)),
                            wind_direction=current.get("winddir16Point", ""),
                            weather=current.get("lang_zh", [{}])[0].get("value", current.get("weatherDesc", [{}])[0].get("value", "未知")),
                            weather_code=current.get("weatherCode", "0"),
                            visibility=float(current.get("visibility", 0)),
                            pressure=float(current.get("pressure", 0)),
                            tips=self._generate_weather_tips(
                                float(current.get("temp_C", 20)),
                                int(current.get("humidity", 50)),
                                int(current.get("weatherCode", 0))
                            )
                        )
        except Exception as e:
            print(f"Free weather fetch error: {e}")
        
        return None
    
    def _deg_to_direction(self, deg: int) -> str:
        directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
        index = int((deg + 22.5) / 45) % 8
        return directions[index]
    
    def _generate_weather_tips(self, temp: float, humidity: int, weather_code: int) -> List[str]:
        tips = []
        
        if temp < 0:
            tips.append("天气寒冷，注意保暖")
        elif temp < 10:
            tips.append("天气较冷，建议穿厚外套")
        elif temp > 35:
            tips.append("高温天气，注意防暑")
        elif temp > 30:
            tips.append("天气炎热，注意防晒")
        
        if humidity > 80:
            tips.append("湿度较高，注意防潮")
        elif humidity < 30:
            tips.append("空气干燥，多喝水")
        
        if weather_code in [200, 201, 202, 230, 231, 232]:
            tips.append("可能有雷暴，注意安全")
        elif weather_code in [300, 301, 302, 310, 311, 312, 500, 501, 502, 503, 504]:
            tips.append("可能下雨，记得带伞")
        elif weather_code in [600, 601, 602, 611, 612, 615, 616, 620, 621, 622]:
            tips.append("可能下雪，注意路滑")
        elif weather_code in [701, 711, 721, 731, 741, 751, 761, 762, 771, 781]:
            tips.append("能见度较低，注意出行安全")
        
        if not tips:
            tips.append("天气不错，适合出行")
        
        return tips
    
    async def get_news(self, category: str = "general", count: int = 5) -> List[NewsItem]:
        cache_key = f"news_{category}"
        
        if self._is_cache_valid(cache_key, "news"):
            return self._get_from_cache(cache_key)
        
        news = await self._fetch_news(category, count)
        
        if news:
            self._set_cache(cache_key, news)
        
        return news
    
    async def _fetch_news(self, category: str, count: int) -> List[NewsItem]:
        if self._news_api_key:
            return await self._fetch_news_api(category, count)
        else:
            return await self._fetch_news_free(category, count)
    
    async def _fetch_news_api(self, category: str, count: int) -> List[NewsItem]:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "country": "cn",
            "category": category,
            "pageSize": count,
            "apiKey": self._news_api_key
        }
        
        data = await self._fetch(url, params)
        if not data or data.get("status") != "ok":
            return []
        
        news_items = []
        for article in data.get("articles", [])[:count]:
            news_items.append(NewsItem(
                title=article.get("title", ""),
                summary=article.get("description", "") or "",
                source=article.get("source", {}).get("name", ""),
                url=article.get("url", ""),
                published_at=datetime.fromisoformat(article.get("publishedAt", "").replace("Z", "+00:00")) if article.get("publishedAt") else datetime.now(),
                category=category,
                image_url=article.get("urlToImage")
            ))
        
        return news_items
    
    async def _fetch_news_free(self, category: str, count: int) -> List[NewsItem]:
        return [
            NewsItem(
                title="示例新闻标题",
                summary="这是一条示例新闻摘要，实际使用时请配置新闻API密钥。",
                source="示例来源",
                url="https://example.com",
                published_at=datetime.now(),
                category=category
            )
        ]
    
    async def get_exchange_rate(self, from_currency: str = "USD", to_currency: str = "CNY") -> Optional[ExchangeRate]:
        cache_key = f"exchange_{from_currency}_{to_currency}"
        
        if self._is_cache_valid(cache_key, "exchange"):
            return self._get_from_cache(cache_key)
        
        rate = await self._fetch_exchange_rate(from_currency, to_currency)
        
        if rate:
            self._set_cache(cache_key, rate)
        
        return rate
    
    async def _fetch_exchange_rate(self, from_currency: str, to_currency: str) -> Optional[ExchangeRate]:
        try:
            url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
            data = await self._fetch(url)
            
            if data and "rates" in data:
                rate = data["rates"].get(to_currency)
                if rate:
                    return ExchangeRate(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        rate=rate,
                        updated_at=datetime.now()
                    )
        except Exception as e:
            print(f"Exchange rate fetch error: {e}")
        
        return None
    
    async def get_holiday_info(self, target_date: Optional[date] = None) -> Dict:
        target = target_date or date.today()
        
        holidays_2024 = {
            "2024-01-01": "元旦",
            "2024-02-10": "春节",
            "2024-04-04": "清明节",
            "2024-05-01": "劳动节",
            "2024-06-10": "端午节",
            "2024-09-17": "中秋节",
            "2024-10-01": "国庆节",
        }
        
        date_str = target.strftime("%Y-%m-%d")
        
        return {
            "date": date_str,
            "is_holiday": date_str in holidays_2024,
            "holiday_name": holidays_2024.get(date_str),
            "weekday": target.strftime("%A"),
            "weekday_cn": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][target.weekday()]
        }
    
    def format_weather_response(self, weather: WeatherInfo) -> str:
        response = f"📍 {weather.city}天气\n\n"
        response += f"🌡️ 温度：{weather.temperature}°C（体感{weather.feels_like}°C）\n"
        response += f"🌤️ 天气：{weather.weather}\n"
        response += f"💧 湿度：{weather.humidity}%\n"
        response += f"💨 风力：{weather.wind_direction}风 {weather.wind_speed}km/h\n"
        
        if weather.tips:
            response += f"\n💡 小贴士：{weather.tips[0]}"
        
        return response
    
    def format_news_response(self, news_list: List[NewsItem]) -> str:
        if not news_list:
            return "暂无新闻信息"
        
        response = "📰 今日新闻\n\n"
        
        for i, news in enumerate(news_list[:5], 1):
            response += f"{i}. {news.title}\n"
            response += f"   来源：{news.source}\n\n"
        
        return response
    
    def clear_cache(self, info_type: Optional[str] = None):
        if info_type:
            keys_to_remove = [k for k in self._cache if k.startswith(info_type)]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            self._cache.clear()
