import os, re, asyncio, base64, io
from PIL import Image
from config import ZHIPU_API_KEY, http_client

async def analyze_vision(url):
    clean_url = str(url).replace("&amp;", "&")
    b64_img = ""
    if clean_url.startswith("http"):
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://q.qq.com/"}
        try:
            r = await http_client.get(clean_url, headers=headers, timeout=15)
            if r.status_code == 200 and len(r.content) > 100:
                img = Image.open(io.BytesIO(r.content))
                if img.mode != 'RGB': img = img.convert('RGB')
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG")
                b64_img = base64.b64encode(buffered.getvalue()).decode('utf-8')
        except: pass
    if not b64_img: return "图片读取失败"
    payload = {"model": "glm-4v-flash", "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}, {"type": "text", "text": "详细描述这张图"}]}]}
    try:
        r = await http_client.post("https://open.bigmodel.cn/api/paas/v4/chat/completions", headers={"Authorization": f"Bearer {ZHIPU_API_KEY}"}, json=payload, timeout=20)
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e: return f"智谱异常: {e}"

async def parse_msg(raw_msg):
    txt, media_prompt, img_tasks = "", "", []
    if isinstance(raw_msg, list):
        for item in raw_msg:
            if item.get("type") == "text": txt += item.get("data", {}).get("text", "")
            elif item.get("type") == "image":
                src = item.get("data", {}).get("url") or item.get("data", {}).get("file")
                if src: img_tasks.append(analyze_vision(src))
    else: 
        raw_str = str(raw_msg)
        cq_matches = re.findall(r'\[CQ:image,[^\]]*\]', raw_str)
        if cq_matches:
            txt = re.sub(r'\[CQ:image,.*?\]', '[图片]', raw_str)
            for cq in cq_matches:
                url_m = re.search(r'url=([^,\]]+)', cq)
                if url_m: img_tasks.append(analyze_vision(url_m.group(1)))
        else: txt = raw_str
    if img_tasks:
        results = await asyncio.gather(*img_tasks)
        for i, desc in enumerate(results): media_prompt += f"\n[图片内容: {desc}]"
    return txt, media_prompt
