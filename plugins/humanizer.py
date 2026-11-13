import asyncio, random, re, time
from gateway import send_universal

LAST_SENT_CACHE = {}
SEND_LOCKS = {}

async def human_typing_and_send(ws, uid, platform, text, micro_action="", hormones=None, extra_params=None):
    if not hormones: hormones = {"cortisol": 50, "dopamine": 50}
    if uid not in SEND_LOCKS: SEND_LOCKS[uid] = asyncio.Lock()

    async with SEND_LOCKS[uid]:
        # 1. 按标点和换行智能切分
        parts = re.split(r'([。！？!?\n])', text)
        sentences = []
        for i in range(0, len(parts) - 1, 2): 
            sentences.append(parts[i] + parts[i+1])
        if len(parts) % 2 != 0 and parts[-1].strip(): 
            sentences.append(parts[-1])
        
        # 2. 合并短句（防止发出“嗯。”“好。”这种碎嘴子）
        merged, buffer = [], ""
        for s in [s.strip() for s in sentences if s.strip()]:
            if len(buffer) < 15: 
                buffer += s
            else:
                merged.append(buffer)
                buffer = s
        if buffer: 
            merged.append(buffer)

        # 3. 拟人化标点处理与去重（去句号，逗号变空格，保留问号感叹号）
        final_merged = []
        for m in merged:
            # 如果和上一句一模一样，直接丢掉
            if not final_merged or m != final_merged[-1]:
                clean_m = re.sub(r'[。.]', '', m)
                clean_m = re.sub(r'[，、；,;]', ' ', m)
                clean_m = re.sub(r'\s+', ' ', clean_m).strip()
                if clean_m: 
                    final_merged.append(clean_m)
        merged = final_merged

        # 4. 跨轮次全局防复读拦截（缓存 60 秒）
        if uid not in LAST_SENT_CACHE: 
            LAST_SENT_CACHE[uid] = []
        
        for i, seg in enumerate(merged):
            now = time.time()
            # 检查过去 60 秒内是否发过同样的话
            is_dup = any(seg == r["text"] and (now - r["time"] < 60) for r in LAST_SENT_CACHE[uid])
            if is_dup: 
                print(f"⚠️ [防复读拦截] 试图重复发送: {seg}")
                continue

            # 5. 情绪化打字延迟计算
            base_delay = len(seg) * random.uniform(0.1, 0.2)
            if hormones.get("cortisol", 50) > 80: 
                base_delay += random.uniform(1.0, 3.0) # 烦躁时故意晾着你
            elif hormones.get("dopamine", 50) > 80: 
                base_delay = len(seg) * 0.05 # 兴奋时秒回
                
            # 执行第一句话前的等待
            await asyncio.sleep(max(0.5, base_delay))
            
            # 6. 触发发送（带上可能的 token 凭证）
            try: 
                res = await send_universal(ws, uid, platform, "text", seg, extra_params)
                print(f"🚀 [发送回执] {res} | 内容: {seg}")
                LAST_SENT_CACHE[uid].append({"text": seg, "time": time.time()})
                # 缓存上限限制，防止内存溢出
                if len(LAST_SENT_CACHE[uid]) > 10: 
                    LAST_SENT_CACHE[uid].pop(0)
            except Exception as e: 
                print(f"🚀 [发送崩溃] {e}")
            
            # 7. 多条消息之间的强制停顿（防风控）
            if i < len(merged) - 1: 
                # 如果是微信平台，强制停 4 秒防封号；QQ 可以稍微快一点
                if platform == "wechat":
                    print("⏳ [微信防风控] 停顿 4 秒...")
                    await asyncio.sleep(4.0) 
                else:
                    await asyncio.sleep(random.uniform(1.5, 3.0))
