import asyncio
import httpx
import os
import time
import uuid
import json
import base64
from config import AUDIO_DIR

DOUBAO_API_KEY = "f0299af6-6560-47f4-b0c9-0f4c77ef181f"
RESOURCE_ID = "seed-tts-2.0"
DEFAULT_VOICE = "zh_female_vv_uranus_bigtts"

async def text_to_speech(text: str, hormones: dict = None) -> str | None:
    if not text.strip():
        return None

    speech_rate = 0
    if hormones:
        if hormones.get("cortisol", 50) > 80: speech_rate = 30
        elif hormones.get("dopamine", 50) > 80: speech_rate = 50
        elif hormones.get("dopamine", 50) < 30: speech_rate = -20

    url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    headers = {
        "X-Api-Key": DOUBAO_API_KEY,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    payload = {
        "req_params": {
            "text": text,
            "speaker": DEFAULT_VOICE,
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
                "speech_rate": speech_rate,
            }
        }
    }

    mp3_path = f"{AUDIO_DIR}/tts_{int(time.time()*1000)}.mp3"
    audio_bytes = bytearray()

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            # 🚨 核心修复：逐行读取，提取 JSON 中的 data 字段
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    return None

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("{"):
                        continue
                    try:
                        data_json = json.loads(line)
                        if "data" in data_json and data_json["data"]:
                            # 解码 Base64 音频片段并追加
                            audio_bytes.extend(base64.b64decode(data_json["data"]))
                    except Exception:
                        continue

            if len(audio_bytes) > 1000:
                with open(mp3_path, "wb") as f:
                    f.write(audio_bytes)
                return mp3_path
            else:
                print(f"🔇 TTS 提取音频失败，大小仅为: {len(audio_bytes)} 字节")
                return None

        except Exception as e:
            print(f"🔇 TTS 请求异常: {e}")
            return None
