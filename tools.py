import json, base64, subprocess, os, time, re, asyncio
from config import http_client, get_system_status, AUDIO_DIR, MASTER_QQ, WHITELIST_FILE, load_json, save_json, get_user_files, MIND_STATE_FILE
from sandbox import run_python, run_shell
from tts import text_to_speech
from memory import auto_summarize_and_store, write_important_memory

TOOLS_SCHEMA = []
TOOL_FUNCTIONS = {}

def register_tool(name, desc, parameters):
    def decorator(func):
        TOOLS_SCHEMA.append({
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": parameters}
        })
        TOOL_FUNCTIONS[name] = func
        return func
    return decorator

@register_tool("run_python", "执行Python代码", {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]})
async def tool_run_python(ws, uid, args, is_autonomous):
    return await run_python(args.get("code", ""))

@register_tool("execute_shell", "执行Shell命令/查文件/ps aux", {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]})
async def tool_execute_shell(ws, uid, args, is_autonomous):
    return await run_shell(args.get("cmd", ""))

@register_tool("search_web", "联网搜索", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})
async def tool_search_web(ws, uid, args, is_autonomous):
    try:
        from bs4 import BeautifulSoup
        r = await http_client.get(f"https://html.duckduckgo.com/html/?q={args.get('query', '')}", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        soup = BeautifulSoup(r.text, 'lxml')
        results = [f"【{a.find('h2').text}】{a.find('a').text}" for a in soup.find_all('a', class_='result__snippet') if a.find('h2') and a.find('a')][:5]
        return "【搜索结果】\n" + "\n".join(results) if results else "没搜到"
    except: return "搜索失败"

@register_tool("send_voice", "发语音", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]})
async def tool_send_voice(ws, uid, args, is_autonomous):
    mind_db = load_json(MIND_STATE_FILE)
    hormones = mind_db.get("hormones", {})
    
    # 1. 调用豆包生成 WAV
    audio_path = await text_to_speech(args.get("text", ""), hormones)
    if not audio_path or not os.path.exists(audio_path):
        return "语音生成失败，请检查 TTS 日志。"
        
    try:
        # 2. 直接读取 WAV 转为 Base64
        with open(audio_path, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode('utf-8')
        
        # 3. 发送给协议端
        await ws.send(json.dumps({
            "action": "send_private_msg",
            "params": {
                "user_id": int(uid),
                "message": [{"type": "record", "data": {"file": f"base64://{b64_audio}"}}]
            }
        }))
        # 留点时间给底层发完
        await asyncio.sleep(1.5) 
        return "语音已成功发送。"
    except Exception as e:
        return f"发送异常: {e}"
    finally:
        # 4. 发完立刻清理垃圾文件，保护板子存储
        if os.path.exists(audio_path): 
            os.remove(audio_path)


@register_tool("get_system_info", "查板子状态", {"type": "object", "properties": {}})
async def tool_get_system_info(ws, uid, args, is_autonomous):
    return get_system_status()

@register_tool("send_voice", "发语音", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]})

@register_tool("remember_important", "刻入最高级重要记忆", {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]})
async def tool_remember(ws, uid, args, is_autonomous):
    write_important_memory(args.get("content", ""))
    return "【系统回执】：已刻入最高级重要记忆！"

@register_tool("evaluate_add_whitelist", "将某人拉入白名单", {"type": "object", "properties": {"user_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["user_id", "reason"]})
async def tool_add_whitelist(ws, uid, args, is_autonomous):
    target = str(args.get("user_id", ""))
    reason = args.get("reason", "")
    wl_db = load_json(WHITELIST_FILE)
    allowed = wl_db.get("users", [])
    if target not in allowed:
        allowed.append(target)
        save_json(WHITELIST_FILE, {"users": allowed})
        return f"【评估通过】已基于理由“{reason}”将 {target} 加入白名单。"
    return "已经在白名单内。"

@register_tool("write_note", "写笔记/读后感到本地", {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]})
async def tool_write_note(ws, uid, args, is_autonomous):
    with open(f"/home/ztl/rk-agent/agent_notes.txt", "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M')}] {args.get('content', '')}\n")
    return "【系统回执】：感想/笔记已写入本地。"

@register_tool("read_friend_chat", "调阅指定好友档案", {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]})
async def tool_read_friend_chat(ws, uid, args, is_autonomous):
    if uid != MASTER_QQ: return "【系统拦截】只有主人有权查阅所有人档案！"
    target = str(args.get("user_id", ""))
    chat_file, _ = get_user_files(target)
    chats = load_json(chat_file).get("history", [])[-10:]
    if not chats: return f"该用户目前没有任何聊天记录。"
    return f"【{target} 的档案】\n" + "\n".join([f"对方:{c['user']}\n晚星:{c['ai']}" for c in chats])

@register_tool("send_private_msg", "发私聊", {"type": "object", "properties": {"user_id": {"type": "string"}, "message": {"type": "string"}}, "required": ["user_id", "message"]})
async def tool_send_private(ws, uid, args, is_autonomous):
    target = str(args.get("user_id", ""))
    if target == "主人" or target.lower() == "master": target = MASTER_QQ
    await ws.send(json.dumps({"action": "send_private_msg", "params": {"user_id": int(target), "message": args.get("message", "")}}))
    return "【工具回执】：私聊已发送。"

@register_tool("send_group_msg", "发群聊", {"type": "object", "properties": {"group_id": {"type": "string"}, "message": {"type": "string"}}, "required": ["group_id", "message"]})
async def tool_send_group_msg(ws, uid, args, is_autonomous):
    await ws.send(json.dumps({"action": "send_group_msg", "params": {"group_id": int(args.get("group_id", 0)), "message": args.get("message", "")}}))
    return "【工具回执】：群消息已发送。"

@register_tool("friend_poke", "戳一戳好友", {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]})
async def tool_friend_poke(ws, uid, args, is_autonomous):
    target = str(args.get("user_id", ""))
    if target == "主人" or target.lower() == "master": target = MASTER_QQ
    await ws.send(json.dumps({"action": "friend_poke", "params": {"user_id": int(target)}}))
    return "【工具回执】：已发送戳一戳动作。"

@register_tool("send_like", "给好友点赞", {"type": "object", "properties": {"user_id": {"type": "string"}, "times": {"type": "integer"}}, "required": ["user_id"]})
async def tool_send_like(ws, uid, args, is_autonomous):
    target = str(args.get("user_id", ""))
    if target == "主人" or target.lower() == "master": target = MASTER_QQ
    await ws.send(json.dumps({"action": "send_like", "params": {"user_id": int(target), "times": args.get("times", 1)}}))
    return "【工具回执】：已点赞。"

@register_tool("delete_msg", "撤回消息", {"type": "object", "properties": {"message_id": {"type": "string"}}, "required": ["message_id"]})
async def tool_delete_msg(ws, uid, args, is_autonomous):
    await ws.send(json.dumps({"action": "delete_msg", "params": {"message_id": int(args.get("message_id", 0))}}))
    return "【工具回执】：撤回指令已发送。"

@register_tool("delete_friend", "【高危】删除好友", {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]})
async def tool_delete_friend(ws, uid, args, is_autonomous):
    if is_autonomous: return "【漫游模式拒绝高危操作】"
    await ws.send(json.dumps({"action": "delete_friend", "params": {"user_id": int(args.get("user_id", 0))}}))
    return "【工具回执】：执行删除。"

async def execute_tool(ws, uid, name, args, is_autonomous=False):
    if name not in TOOL_FUNCTIONS:
        return f"【报错】：未知工具 {name}"
    try:
        return await TOOL_FUNCTIONS[name](ws, uid, args, is_autonomous)
    except Exception as e:
        return f"工具执行异常: {e}"
@register_tool("open_application", "通过命令行启动图形界面应用（如浏览器、终端等）", {"type": "object", "properties": {"app_cmd": {"type": "string", "description": "启动命令，例如 chromium-browser 或 firefox"}}, "required": ["app_cmd"]})
async def tool_open_application(ws, uid, args, is_autonomous):
    cmd = args.get("app_cmd", "")
    try:
        # 使用 nohup 让它后台常驻，不阻塞主进程
        subprocess.Popen(f"nohup {cmd} >/dev/null 2>&1 &", shell=True, executable="/bin/bash")
        return f"✅ 【物理操作】：已尝试在屏幕上启动 {cmd}，你可以截屏确认。"
    except Exception as e:
        return f"❌ 启动应用失败: {e}"
