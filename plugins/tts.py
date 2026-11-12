import asyncio, httpx, os, time, uuid, json, base64
from config import DOUBAO_API_KEY, AUDIO_DIR

async def generate_voice(text: str, hormones: dict = None) -> str | None:
    if not text.strip(): return None
    speech_rate = 0
    if hormones:
        if hormones.get("cortisol", 50) > 80: speech_rate = 30
        elif hormones.get("dopamine", 50) > 80: speech_rate = 50
        elif hormones.get("dopamine", 50) < 30: speech_rate = -20

    url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    headers = {"X-Api-Key": DOUBAO_API_KEY, "X-Api-Resource-Id": "seed-tts-2.0", "X-Api-Request-Id": str(uuid.uuid4()), "Content-Type": "application/json"}
    payload = {"req_params": {"text": text, "speaker": "zh_female_vv_uranus_bigtts", "audio_params": {"format": "mp3", "sample_rate": 24000, "speech_rate": speech_rate}}}
    
    mp3_path = f"{AUDIO_DIR}/tts_{int(time.time()*1000)}.mp3"
    audio_bytes = bytearray()

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200: return None
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            data_json = json.loads(line)
                            if "data" in data_json and data_json["data"]:
                                audio_bytes.extend(base64.b64decode(data_json["data"]))
                        except: continue
            if len(audio_bytes) > 1000:
                with open(mp3_path, "wb") as f: f.write(audio_bytes)
                return mp3_path
        except: pass
    return None
