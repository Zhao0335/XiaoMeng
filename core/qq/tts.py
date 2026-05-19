"""
GPT-SoVITS TTS 封装
供 send_voice 工具调用，合成语音并返回音频字节
所有参数从 qq_config.json 的 tts 节传入，不再自行读取配置文件
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class SoVITSTTS:
    def __init__(
        self,
        api_url: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        ref_lang: str = "zh",
        text_lang: str = "zh",
        text_split_method: str = "cut0",
        request_timeout: float = 60,
    ):
        self._api_url = (api_url or "http://127.0.0.1:9882").rstrip("/")
        self._ref_audio = ref_audio or ""
        self._ref_text = ref_text or ""
        self._ref_lang = ref_lang
        self._text_lang = text_lang
        self._text_split_method = text_split_method
        self._request_timeout = request_timeout

        logger.info(
            f"SoVITSTTS 初始化: api_url={self._api_url}, "
            f"ref_audio={self._ref_audio}"
        )

    @staticmethod
    def _clean(text: str) -> str:
        """只保留中文、日文、英文、数字和常用标点，去掉颜文字/emoji"""
        text = re.sub(r'[^一-鿿぀-ヿ -~，。！？、；：「」『』…—～\n]', '', text)
        # 清掉清理后留下的空括号/空括号对
        text = re.sub(r'[(（\[【][)\）\]】]', '', text)
        text = re.sub(r' +', ' ', text).strip()
        return text

    async def synthesize(self, text: str) -> Optional[bytes]:
        """合成语音，返回音频字节；失败返回 None"""
        import httpx
        text = self._clean(text)
        if not text:
            return None
        payload = {
            "text": text,
            "text_lang": self._text_lang,
            "ref_audio_path": self._ref_audio,
            "prompt_text": self._ref_text,
            "prompt_lang": self._ref_lang,
            "text_split_method": self._text_split_method,
            "batch_size": 1,
            "speed_factor": 1.0,
            "streaming_mode": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout) as client:
                resp = await client.post(f"{self._api_url}/tts", json=payload)
                resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.warning(f"TTS 合成失败: {e}")
            return None
