"""
GPT-SoVITS TTS 封装
供 send_voice 工具调用，合成语音并返回音频字节
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class SoVITSTTS:
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:9881",
        ref_audio: str = "/home/qwq/zcx_ai_group_friend/ref_voice.wav",
        ref_text: str = "少爷 该起床了 少爷",
    ):
        self._api_url = api_url.rstrip("/")
        self._ref_audio = ref_audio
        self._ref_text = ref_text

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
            "text_lang": "zh",
            "ref_audio_path": self._ref_audio,
            "prompt_text": self._ref_text,
            "prompt_lang": "zh",
            "text_split_method": "cut0",
            "batch_size": 1,
            "speed_factor": 1.0,
            "streaming_mode": False,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{self._api_url}/tts", json=payload)
                resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.warning(f"TTS 合成失败: {e}")
            return None