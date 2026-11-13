import asyncio, random, re, time
from gateway import send_universal

LAST_SENT_CACHE = {}
SEND_LOCKS = {}

async def human_typing_and_send(ws, uid, platform, text, micro_action="", hormones=None, extra_params=None):
    if not hormones: hormones = {"cortisol": 50, "dopamine": 50}
    if uid not in SEND_LOCKS: SEND_LOCKS[uid] = asyncio.Lock()

    async with SEND_LOCKS[uid]:
        # 1. 按标点断句
        parts = re.split(r'([。！？!?\n])', text)
        sentences = []
        for i in range(0, len(parts) - 1, 2): 
            sentences.append(parts[i] + parts[i+1])
        if len(parts) % 2 != 0 and parts[-1].strip(): 
            sentences.append(parts[-1])
        
        # 2. 合并短句
        merged, buffer = [], ""
        for s in [s.strip() for s in sentences if s.strip()]:
            if len(buffer) < 15: 
                buffer += s
            else:
                merged.append(buffer)
                buffer = s
        if buffer: 
            merged.append(buffer)

        # 3. 去标点拟人化
        final_merged = []
        for m in merged:
            if not final_merged or m != final_merged[-1]:
                clean_m = re.sub(r'[。.]', '', m)
                clean_m = re.sub(r'[，、；,;]', ' ', m)
                clean_m = re.sub(r'\s+', ' ', clean_m).strip()
                if clean_m and re.search(r'[\w\u4e00-\u9fa5]', clean_m):
                    final_merged.append(clean_m)
        merged = final_merged

        if uid not in LAST_SENT_CACHE: 
            LAST_SENT_CACHE[uid] = []
        
        for i, seg in enumerate(merged):
            now = time.time()
            # 过滤重复
            is_dup = any(seg == r["text"] and (now - r["time"] < 30) for r in LAST_SENT_CACHE[uid])
            if is_dup: 
                continue

            # 情绪化延迟
            base_delay = len(seg) * random.uniform(0.1, 0.2)
            if hormones.get("cortisol", 50) > 80: 
                base_delay += random.uniform(1.0, 2.0) # 烦躁时晾着你
            elif hormones.get("dopamine", 50) > 80: 
                base_delay = len(seg) * 0.05 # 兴奋时秒回
                
            await asyncio.sleep(max(0.5, base_delay))
            
            try: 
                res = await send_universal(ws, uid, platform, "text", seg, extra_params)
                print(f"🚀 [发送回执] {res} | 内容: {seg}")
                LAST_SENT_CACHE[uid].append({"text": seg, "time": time.time()})
                if len(LAST_SENT_CACHE[uid]) > 10: 
                    LAST_SENT_CACHE[uid].pop(0)
            except Exception as e: 
                print(f"🚀 [发送崩溃] {e}")
            
            # 防风控延迟
            if i < len(merged) - 1: 
                if platform == "wechat":
                    await asyncio.sleep(4.0) 
                else:
                    await asyncio.sleep(random.uniform(1.2, 2.5))
