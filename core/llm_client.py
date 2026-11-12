import asyncio, httpx, json
from config import DEEPSEEK_API_KEY

async def call_deepseek(msgs, tools=None, retries=2):
    for attempt in range(retries):
        try:
            payload = {"model": "deepseek-reasoner", "messages": msgs, "temperature": 0.3}
            if tools: payload["tools"] = tools
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                r = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                    json=payload
                )
                if r.status_code != 200: continue
                return r.json()["choices"][0]["message"]
        except Exception as e:
            await asyncio.sleep(1)
    return None
