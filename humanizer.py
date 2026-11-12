import asyncio, random, re, json

async def human_typing_and_send(ws, uid, text, micro_action="", hormones=None):
    """赛博晚星物理拟人发送引擎"""
    if not hormones: hormones = {"cortisol": 50, "dopamine": 50}
    
    if micro_action:
        await asyncio.sleep(random.uniform(0.5, 1.5))
        try:
            await ws.send(json.dumps({"action": "send_private_msg", "params": {"user_id": int(uid), "message": micro_action}}, ensure_ascii=False))
        except: pass

    parts = re.split(r'([。！？!?\n])', text)
    sentences = [parts[i] + parts[i+1] for i in range(0, len(parts) - 1, 2)]
    if len(parts) % 2 != 0 and parts[-1].strip(): sentences.append(parts[-1])
    sentences = [s.strip() for s in sentences if s.strip()]
    
    merged = []
    buffer = ""
    for s in sentences:
        if len(buffer) < 15: buffer += s
        else:
            merged.append(buffer)
            buffer = s
    if buffer: merged.append(buffer)

    for i, seg in enumerate(merged):
        base_delay = len(seg) * random.uniform(0.1, 0.2)
        # 皮质醇高（烦躁）或 多巴胺低（抑郁）时，故意晾着你
        if hormones.get("cortisol", 50) > 80:
            base_delay += random.uniform(1.0, 3.0) 
        elif hormones.get("dopamine", 50) > 80:
            base_delay = len(seg) * 0.05 # 极度兴奋，秒回连发
            
        await asyncio.sleep(max(0.5, base_delay))
        try:
            await ws.send(json.dumps({"action": "send_private_msg", "params": {"user_id": int(uid), "message": seg}}, ensure_ascii=False))
        except: pass
        
        if i < len(merged) - 1:
            await asyncio.sleep(random.uniform(0.8, 2.0))
