import asyncio, json, websockets, time, re
from config import load_json, get_system_status, active_websockets, CHAT_FILE, MASTER_QQ
from memory import search_memory, save_full_chat, auto_summarize_and_store
from tools import parse_message
from brain import agent_react_loop, post_chat_think

def split_sentences(text):
    parts = re.split(r'([。！？!?\n])', text)
    sentences = [parts[i] + parts[i+1] for i in range(0, len(parts) - 1, 2)]
    if len(parts) % 2 != 0 and parts[-1].strip(): sentences.append(parts[-1])
    return [s.strip() for s in sentences if s.strip()]

async def send_msg(ws, uid, text):
    for i, seg in enumerate(split_sentences(text)):
        if i > 0: await asyncio.sleep(min(len(seg) * 0.05, 1.5)) 
        try: await ws.send(json.dumps({"action": "send_private_msg", "params": {"user_id": int(uid), "message": seg}}, ensure_ascii=False))
        except: pass

async def handle_conn(ws):
    print("🔔 客户端已连入")
    async for msg in ws:
        d = json.loads(msg)
        # 🔎 调试：任何进入的消息先打一行类型
        print(f"[RX] post_type={d.get('post_type')} message_type={d.get('message_type')} sender={d.get('sender')}", flush=True)
        if d.get("post_type") != "message" or d.get("message_type") != "private": continue
        uid = str(d["sender"]["user_id"])
        print(f"[RX] 私聊消息 来自 uid={uid} 内容={d.get('message')!r}", flush=True)
        active_websockets[uid] = ws
        
        txt, media_prompt = await parse_message(d.get("message", ""))
        if not txt.strip() and not media_prompt: continue
        
        long_term = await search_memory(uid, txt)
        db = load_json(CHAT_FILE)
        history = []
        for c in db.get(uid, [])[-20:]:
            history.append({"role": "user", "content": c["user"]})
            history.append({"role": "assistant", "content": c["ai"]})
            
        sp = f"你是晚星。状态：{get_system_status()}。你可以调用Docker沙盒和系统工具。\n{long_term}"
        msgs = [{"role": "system", "content": sp}] + history + [{"role": "user", "content": txt + media_prompt}]
        
        rep = await agent_react_loop(msgs, ws, uid, user_text=txt)
        await send_msg(ws, uid, rep)
        
        asyncio.create_task(asyncio.to_thread(save_full_chat, uid, txt + media_prompt, rep))
        asyncio.create_task(auto_summarize_and_store(uid, f"用户: {txt}\n晚星: {rep}"))
        asyncio.create_task(post_chat_think(ws, uid, history + [{"role": "user", "content": txt}, {"role": "assistant", "content": rep}], rep))

async def bg_think():
    while True:
        now = time.localtime()
        if 1 <= now.tm_hour < 7:
            await asyncio.sleep(3600); continue
        await asyncio.sleep(1800) 
        if MASTER_QQ in active_websockets:
            ws = active_websockets[MASTER_QQ]
            sp = f"你是晚星，现在是{now.tm_hour}:{now.tm_min}。你可以自由支配时间。不想动就输出 <SILENT>。"
            rep = await agent_react_loop([{"role": "system", "content": sp}, {"role": "user", "content": "自由活动"}], ws, MASTER_QQ, "自由活动")
            if "<SILENT>" not in rep and len(rep) > 2: await send_msg(ws, MASTER_QQ, rep)

async def main():
    asyncio.create_task(bg_think())
    print("🚀 晚星·终极融合体 (Docker沙盒+多轨记忆) 启动，监听 3002...")
    async with websockets.serve(handle_conn, "0.0.0.0", 3002): 
        await asyncio.Future()

if __name__ == "__main__": 
    asyncio.run(main())

# ================= 🚨 主程序消息路由补丁 =================
import re
import os
from tools import parse_message # 确保调用识图函数

async def handle_conn(ws):
    print("🔔 客户端已连入")
    async for msg in ws:
        d = json.loads(msg)
        # 只处理私聊消息
        if d.get("post_type") != "message" or d.get("message_type") != "private": continue
        
        uid = str(d["sender"]["user_id"])
        active_websockets[uid] = ws
        
        # 🚨 核心：调用 parse_message 提取文字并识别图片
        txt, media_prompt = await parse_message(d.get("message", ""))
        
        if not txt.strip() and not media_prompt: continue
        
        # 记忆检索
        long_term = await search_memory(uid, txt)
        db = load_json(CHAT_FILE)
        history = []
        for c in db.get(uid, [])[-20:]:
            history.append({"role": "user", "content": c["user"]})
            history.append({"role": "assistant", "content": c["ai"]})
            
        sp = f"你是晚星。状态：{get_system_status()}。\n{long_term}"
        
        # 将识别到的图片描述（media_prompt）拼接到用户文本后面，一起发给大模型
        msgs = [{"role": "system", "content": sp}] + history + [{"role": "user", "content": txt + media_prompt}]
        
        # 大脑思考并生成回复
        rep = await agent_react_loop(msgs, ws, uid, user_text=txt)
        await send_msg(ws, uid, rep)
        
        # 存档与后置思考
        asyncio.create_task(asyncio.to_thread(save_full_chat, uid, txt + media_prompt, rep))
        asyncio.create_task(auto_summarize_and_store(uid, f"用户: {txt}\n晚星: {rep}"))
        asyncio.create_task(post_chat_think(ws, uid, history + [{"role": "user", "content": txt}, {"role": "assistant", "content": rep}], rep))
