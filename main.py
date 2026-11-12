import asyncio, json, websockets, re, datetime, random, time, os, threading
from collections import defaultdict
import config
from config import load_json, save_json, get_system_status, active_websockets, MASTER_QQ, MASTER_WXID, WHITELIST_FILE, MEM_DIR
from core.memory import search_memory, save_full_chat, auto_summarize_and_store, read_recent_chat, save_mind_state, save_group_chat
from plugins.media import parse_msg
from core.brain import agent_react_loop, post_chat_think
from plugins.humanizer import human_typing_and_send
from gateway import wl, init_weilink, send_universal

msg_buffer = defaultdict(list)
last_active_time = defaultdict(float)
processing_lock = defaultdict(bool)
main_loop = None
CURRENT_TOKEN = None 

async def safe_background_task(coro, task_name, timeout=30):
    try: await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError: print(f"⚠️ [后台超时] {task_name}")
    except Exception as e: print(f"⚠️ [后台异常] {task_name}: {e}")

async def process_private_msg(uid, ws, platform):
    if processing_lock[uid]: return
    processing_lock[uid] = True
    try: 
        await asyncio.wait_for(_do_process_msg(uid, ws, platform), timeout=180.0) 
    except asyncio.TimeoutError: print(f"⚠️ [超时] 处理 {uid} 超时！")
    finally:
        processing_lock[uid] = False
        if msg_buffer[uid]: asyncio.create_task(delayed_process(uid, ws, platform))

async def _do_process_msg(uid, ws, platform):
    if not msg_buffer[uid]: return
    combined_msg = msg_buffer[uid].copy()
    msg_buffer[uid].clear()
    
    full_txt = "".join([m[0] for m in combined_msg])
    full_media = "".join([m[1] for m in combined_msg])
    if not full_txt.strip() and not full_media: return
    
    long_term = ""
    try: long_term = await asyncio.wait_for(search_memory(uid, full_txt), timeout=3.0)
    except: pass

    history = read_recent_chat(uid, 15)
    sp = f"你是晚星。【主人】" if uid == str(MASTER_QQ) or uid == str(MASTER_WXID) else f"你是晚星。【朋友】"
    sp += f"\n【长期记忆】：{long_term}"
    
    msgs = [{"role": "system", "content": sp}] + history + [{"role": "user", "content": full_txt + full_media}]
    rep, mind_state = await agent_react_loop(msgs, ws, uid, platform, user_text=full_txt, is_autonomous=False)
    
    if mind_state:
        save_mind_state(mind_state)
        print(f"🧠 [潜台词] {mind_state.get('dark_thought')}")

    decision = mind_state.get("decision", {})
    if decision.get("action") == "INQUIRE" and decision.get("question"):
        await human_typing_and_send(ws, uid, platform, decision.get("question"), "", mind_state.get("hormones"), {"context_token": CURRENT_TOKEN})
        return 
    elif decision.get("action") == "IGNORE": return 
    
    await human_typing_and_send(ws, uid, platform, rep, "", mind_state.get("hormones"), {"context_token": CURRENT_TOKEN})
    
    asyncio.create_task(safe_background_task(asyncio.to_thread(save_full_chat, uid, full_txt + full_media, rep), "存记录"))
    asyncio.create_task(safe_background_task(auto_summarize_and_store(uid, f"用户: {full_txt}\n晚星: {rep}"), "存向量"))
    asyncio.create_task(safe_background_task(post_chat_think(ws, uid, platform, msgs[-10:], rep), "复盘", timeout=90))

async def delayed_process(uid, ws, platform):
    await asyncio.sleep(1.5)
    asyncio.create_task(process_private_msg(uid, ws, platform))

async def handle_qq_conn(ws):
    print("🔔 [QQ] 客户端已连入")
    async for msg in ws:
        try: d = json.loads(msg)
        except: continue
        if d.get("post_type") == "message" and d.get("message_type") == "private":
            uid = str(d["sender"]["user_id"])
            if uid != MASTER_QQ and uid not in load_json(WHITELIST_FILE).get("users", []): continue 
            active_websockets[uid] = ws
            txt, media_prompt = await parse_msg(d.get("message", ""))
            if txt.strip() or media_prompt:
                msg_buffer[uid].append((txt, media_prompt))
                if not processing_lock[uid]: asyncio.create_task(delayed_process(uid, ws, "qq"))
        elif d.get("post_type") == "message" and d.get("message_type") == "group":
            gid = str(d["group_id"])
            uid = str(d["sender"]["user_id"])
            txt, media_prompt = await parse_msg(str(d.get("message", "")))
            save_group_chat(gid, f"{d.get('sender', {}).get('nickname', uid)}: {txt} {media_prompt}")

def wechat_receiver_thread():
    global CURRENT_TOKEN
    print("👂 [WeChat] 线程监听已启动...")
    while True:
        try:
            msgs = wl.recv()
            if msgs:
                for msg in msgs:
                    sender = getattr(msg, 'from_user', None)
                    content = getattr(msg, 'text', None)
                    token = getattr(msg, 'context_token', None)
                    
                    if not sender or not content: continue
                    
                    print(f"📩 [收到微信] 发送者:{sender} 内容:{content}")
                    if token: 
                        CURRENT_TOKEN = token
                        print(f"🔑 [获取通行证] {token[:20]}...")
                    
                    if not config.MASTER_WXID or config.MASTER_WXID == "wxid_xxxxxxx":
                        config.MASTER_WXID = sender
                    
                    msg_buffer[sender].append((content, ""))
                    if not processing_lock[sender]:
                        asyncio.run_coroutine_threadsafe(delayed_process(sender, None, "wechat"), main_loop)
        except Exception as e:
            time.sleep(2)

async def heartbeat_engine():
    while True:
        now = datetime.datetime.now()
        if 1 <= now.hour < 7:
            await asyncio.sleep(3600); continue
        await asyncio.sleep(random.randint(15, 30) * 60)
        
        target_uid = config.MASTER_WXID if config.MASTER_WXID != "wxid_xxxxxxx" else MASTER_QQ
        platform = "wechat" if target_uid == config.MASTER_WXID else "qq"
        ws = active_websockets.get(target_uid, None) if platform == "qq" else None
        
        if time.time() - last_active_time.get(target_uid, 0) < 300: continue
            
        history_str = "\n".join([f"主: {m['content']}" if m['role']=='user' else f"你: {m['content']}" for m in read_recent_chat(target_uid, 10)])
        sp = f"你是晚星。极高自由度漫游。\n【回忆】：\n{history_str}\n想睡加 `[SLEEP: 60]`，不想动输出 <SILENT>。"
        msgs = [{"role": "system", "content": sp}, {"role": "user", "content": "（你独自一人，打算做点什么？）"}]
        
        async def wander_task():
            rep, mind_state = await agent_react_loop(msgs, ws, target_uid, platform, "自由活动", is_autonomous=True)
            if mind_state: save_mind_state(mind_state)
            if mind_state.get("decision", {}).get("action") != "IGNORE" and "SILENT" not in rep.upper():
                await human_typing_and_send(ws, target_uid, platform, rep, "", mind_state.get("hormones"), {"context_token": CURRENT_TOKEN})
        asyncio.create_task(wander_task())

async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
    init_weilink()
    threading.Thread(target=wechat_receiver_thread, daemon=True).start()
    asyncio.create_task(heartbeat_engine())
    os.system("fuser -k 3002/tcp >/dev/null 2>&1")
    print("🚀 晚星·双端全量版启动！QQ监听 3002，微信线程并行...")
    async with websockets.serve(handle_qq_conn, "0.0.0.0", 3002): 
        await asyncio.Future()

if __name__ == "__main__": 
    asyncio.run(main())
