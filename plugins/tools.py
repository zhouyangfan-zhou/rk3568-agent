import json, base64, os, time, asyncio, subprocess
import httpx
from config import get_system_status, MASTER_QQ, WHITELIST_FILE, load_json, save_json, get_user_files, BASE_DIR
from plugins.sandbox import run_python, run_shell
from plugins.tts import generate_voice
from plugins.media import analyze_vision
from core.memory import write_important_memory, load_mind_state
from gateway import send_universal

TOOLS_SCHEMA = []
TOOL_FUNCTIONS = {}

def register_tool(name, desc, parameters):
    def decorator(func):
        TOOLS_SCHEMA.append({"type": "function", "function": {"name": name, "description": desc, "parameters": parameters}})
        TOOL_FUNCTIONS[name] = func
        return func
    return decorator

def _safe_user(target):
    if str(target).lower() in ["主人", "master"]: return str(MASTER_QQ)
    return str(target)

def _map_path(file_path):
    if str(file_path).startswith("/app/"): return str(file_path).replace("/app/", "/home/ztl/rk-agent/")
    return str(file_path)

MSG_PARAM = {"type": ["string", "array"], "description": "消息内容"}

# ==================== 1. 视觉与物理控制 ====================

@register_tool("take_screenshot", "截取开发板屏幕。", {"type": "object", "properties": {"send_to_user": {"type": "boolean"}}, "required": ["send_to_user"]})
async def tool_take_screenshot(ws, uid, platform, args, is_autonomous, extra_params=None):
    img_path = "/app/screenshot.png"
    host_path = _map_path(img_path)
    send_to_user = args.get("send_to_user", False)
    try:
        if os.path.exists(host_path): os.remove(host_path)
        res = subprocess.run(["scrot", host_path], capture_output=True, text=True, timeout=10)
        if res.returncode != 0: return f"❌ 【截屏失败】：{res.stderr}"
        vision_desc = await analyze_vision(f"file://{host_path}")
        
        if send_to_user:
            with open(host_path, "rb") as f: b64_data = base64.b64encode(f.read()).decode('utf-8')
            await send_universal(ws, uid, platform, "image", f"base64://{b64_data}", extra_params)
            return f"✅ 【截屏并发送给主人】：{vision_desc}"
        return f"✅ 【截屏（仅自己可见）】：{vision_desc}"
    except Exception as e: return f"❌ 截屏崩溃: {e}"

@register_tool("open_application", "启动应用", {"type": "object", "properties": {"app_cmd": {"type": "string"}}, "required": ["app_cmd"]})
async def tool_open_application(ws, uid, platform, args, is_autonomous, extra_params=None):
    subprocess.Popen(f"nohup {args.get('app_cmd', '')} >/dev/null 2>&1 &", shell=True, executable="/bin/bash")
    return "✅ 【物理操作】：已尝试启动应用。"

@register_tool("browse_web", "读取网页内容", {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]})
async def tool_browse_web(ws, uid, platform, args, is_autonomous, extra_params=None):
    url = args.get("url", "")
    if not url.startswith("http"): url = "https://" + url
    try:
        from bs4 import BeautifulSoup
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            text = BeautifulSoup(r.text, 'lxml').get_text(separator=' ', strip=True)
            return f"【网页内容】:\n{text[:2000]}"
    except Exception as e: return f"【网页失败】: {e}"

@register_tool("look_at_image", "查看图片", {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]})
async def tool_look_at_image(ws, uid, platform, args, is_autonomous, extra_params=None):
    path = args.get("file_path", "")
    if not path.startswith("http"): path = f"file://{_map_path(path)}"
    return f"✅ 【识图结果】:\n{await analyze_vision(path)}"

@register_tool("click_screen", "鼠标点击", {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]})
async def tool_click_screen(ws, uid, platform, args, is_autonomous, extra_params=None):
    try:
        subprocess.run(["xdotool", "mousemove", str(args.get("x")), str(args.get("y")), "click", "1"], check=True, timeout=5)
        return f"✅ 已点击 ({args.get('x')}, {args.get('y')})。"
    except Exception as e: return f"❌ 点击失败: {e}"

@register_tool("scroll_screen", "鼠标滑动屏幕", {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}, "amount": {"type": "integer"}}, "required": ["direction"]})
async def tool_scroll_screen(ws, uid, platform, args, is_autonomous, extra_params=None):
    btn = "4" if args.get("direction", "down") == "up" else "5"
    for _ in range(args.get("amount", 3)):
        subprocess.run(["xdotool", "click", btn], check=True, timeout=2)
    return f"✅ 已滑动。"

# ==================== 2. 消息与媒体发送 ====================

@register_tool("send_private_msg", "发送私聊消息", {"type": "object", "properties": {"user_id": {"type": "string"}, "message": MSG_PARAM}, "required": ["user_id", "message"]})
async def tool_send_private(ws, uid, platform, args, is_autonomous, extra_params=None):
    return await send_universal(ws, _safe_user(args.get("user_id")), platform, "text", args.get("message"), extra_params)

@register_tool("send_group_msg", "发送群聊消息", {"type": "object", "properties": {"group_id": {"type": "string"}, "message": MSG_PARAM}, "required": ["group_id", "message"]})
async def tool_send_group(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "send_group_msg", "params": {"group_id": int(args.get("group_id", 0)), "message": args.get("message", "")}}))
    return "✅ 【回执】：群聊已发送。"

@register_tool("send_msg", "通用发送（自动识别群或私）", {"type": "object", "properties": {"message_type": {"type": "string", "enum": ["private", "group"]}, "target_id": {"type": "string"}, "message": MSG_PARAM}, "required": ["message_type", "target_id", "message"]})
async def tool_send_msg(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信请使用 send_private_msg"
    mtype, target = args.get("message_type"), _safe_user(args.get("target_id"))
    payload = {"action": "send_msg", "params": {"message_type": mtype, "message": args.get("message", "")}}
    if mtype == "private": payload["params"]["user_id"] = int(target)
    else: payload["params"]["group_id"] = int(target)
    await ws.send(json.dumps(payload))
    return "✅ 【回执】：通用消息已发送。"

@register_tool("send_image", "发送图片", {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]})
async def tool_send_image(ws, uid, platform, args, is_autonomous, extra_params=None):
    file_path = args.get("file_path", "")
    if not file_path.startswith("http"):
        file_path = _map_path(file_path)
        if not os.path.exists(file_path): return f"❌ 【发送失败】：找不到文件 {file_path}。"
        with open(file_path, "rb") as f: file_path = f"base64://{base64.b64encode(f.read()).decode('utf-8')}"
    return await send_universal(ws, uid, platform, "image", file_path, extra_params)

@register_tool("send_voice", "发送语音", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]})
async def tool_send_voice(ws, uid, platform, args, is_autonomous, extra_params=None):
    audio_path = await generate_voice(args.get("text", ""), load_mind_state().get("hormones", {}))
    if audio_path and os.path.exists(audio_path):
        with open(audio_path, "rb") as f: b64 = base64.b64encode(f.read()).decode('utf-8')
        res = await send_universal(ws, uid, platform, "record", f"base64://{b64}", extra_params)
        await asyncio.sleep(1.0); os.remove(audio_path)
        return res
    return "❌ TTS 生成失败。"

@register_tool("delete_msg", "撤回消息", {"type": "object", "properties": {"message_id": {"type": "string"}}, "required": ["message_id"]})
async def tool_delete_msg(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "delete_msg", "params": {"message_id": int(args.get("message_id", 0))}}))
    return "✅ 【回执】：撤回指令已发送。"

@register_tool("upload_group_file", "上传文件到群聊", {"type": "object", "properties": {"group_id": {"type": "string"}, "file_path": {"type": "string"}, "name": {"type": "string"}}, "required": ["group_id", "file_path", "name"]})
async def tool_upload_group_file(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    file_path = _map_path(args.get("file_path", ""))
    await ws.send(json.dumps({"action": "upload_group_file", "params": {"group_id": int(args.get("group_id", 0)), "file": file_path, "name": args.get("name", "")}}))
    return "✅ 【回执】：群文件上传指令已发送。"

@register_tool("send_qzone_msg", "发布QQ空间说说（文字+图）", {"type": "object", "properties": {"content": {"type": "string"}, "image_path": {"type": "string"}}, "required": ["content"]})
async def tool_send_qzone(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持 Qzone"
    msg = []
    if args.get("content"): msg.append({"type": "text", "data": {"text": args.get("content")}})
    if args.get("image_path"): msg.append({"type": "image", "data": {"file": f"file://{_map_path(args.get('image_path'))}"}})
    await ws.send(json.dumps({"action": "send_qzone_msg", "params": {"message": msg}}))
    return "✅ 【回执】：说说已发布。"

@register_tool("send_like", "给好友点赞", {"type": "object", "properties": {"user_id": {"type": "string"}, "times": {"type": "integer"}}, "required": ["user_id"]})
async def tool_send_like(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "send_like", "params": {"user_id": int(_safe_user(args.get("user_id"))), "times": args.get("times", 1)}}))
    return "✅ 【回执】：赞已点。"

@register_tool("friend_poke", "戳一戳好友", {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]})
async def tool_friend_poke(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "friend_poke", "params": {"user_id": int(_safe_user(args.get("user_id")))}}))
    return "✅ 【回执】：已戳一戳。"

# ==================== 3. 群管与查询 ====================

@register_tool("group_poke", "群内戳一戳", {"type": "object", "properties": {"group_id": {"type": "string"}, "user_id": {"type": "string"}}, "required": ["group_id", "user_id"]})
async def tool_group_poke(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "group_poke", "params": {"group_id": int(args.get("group_id", 0)), "user_id": int(args.get("user_id", 0))}}))
    return "✅ 【回执】：群戳一戳已发送。"

@register_tool("set_msg_emoji_like", "给消息贴表情回应", {"type": "object", "properties": {"message_id": {"type": "string"}, "emoji_id": {"type": "string"}}, "required": ["message_id", "emoji_id"]})
async def tool_set_emoji_like(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "set_msg_emoji_like", "params": {"message_id": int(args.get("message_id", 0)), "emoji_id": args.get("emoji_id", "")}}))
    return "✅ 【回执】：表情回应已发送。"

@register_tool("mark_msg_as_read", "设置消息已读", {"type": "object", "properties": {"message_id": {"type": "string"}}, "required": ["message_id"]})
async def tool_mark_msg_as_read(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "mark_msg_as_read", "params": {"message_id": int(args.get("message_id", 0))}}))
    return "✅ 【回执】：已标记已读。"

@register_tool("get_login_info", "获取登录信息", {"type": "object", "properties": {}})
async def tool_get_login_info(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "get_login_info", "params": {}}))
    return "✅ 【回执】：查询指令已发送。"

@register_tool("get_friend_list", "获取好友列表", {"type": "object", "properties": {}})
async def tool_get_friend_list(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if uid != str(MASTER_QQ): return "【拦截】：仅主人可查。"
    await ws.send(json.dumps({"action": "get_friend_list", "params": {}}))
    return "✅ 【回执】：查询指令已发送。"

@register_tool("get_group_list", "获取群列表", {"type": "object", "properties": {}})
async def tool_get_group_list(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if uid != str(MASTER_QQ): return "【拦截】：仅主人可查。"
    await ws.send(json.dumps({"action": "get_group_list", "params": {}}))
    return "✅ 【回执】：查询指令已发送。"

@register_tool("get_group_member_list", "获取群成员列表", {"type": "object", "properties": {"group_id": {"type": "string"}}, "required": ["group_id"]})
async def tool_get_group_member_list(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "get_group_member_list", "params": {"group_id": int(args.get("group_id", 0))}}))
    return "✅ 【回执】：群成员查询指令已发送。"

@register_tool("get_group_member_info", "获取群成员信息", {"type": "object", "properties": {"group_id": {"type": "string"}, "user_id": {"type": "string"}}, "required": ["group_id", "user_id"]})
async def tool_get_group_member_info(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "get_group_member_info", "params": {"group_id": int(args.get("group_id", 0)), "user_id": int(args.get("user_id", 0))}}))
    return "✅ 【回执】：群成员信息查询已发送。"

@register_tool("get_msg", "获取单条消息详情", {"type": "object", "properties": {"message_id": {"type": "string"}}, "required": ["message_id"]})
async def tool_get_msg(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "get_msg", "params": {"message_id": int(args.get("message_id", 0))}}))
    return "✅ 【回执】：消息详情查询已发送。"

@register_tool("get_forward_msg", "获取合并转发内容", {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]})
async def tool_get_forward_msg(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "get_forward_msg", "params": {"id": args.get("id", "")}}))
    return "✅ 【回执】：合并转发查询已发送。"

# ==================== 4. 高危管理操作 ====================

@register_tool("set_group_ban", "群禁言", {"type": "object", "properties": {"group_id": {"type": "string"}, "user_id": {"type": "string"}, "duration": {"type": "integer"}}, "required": ["group_id", "user_id", "duration"]})
async def tool_set_group_ban(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_group_ban", "params": {"group_id": int(args.get("group_id", 0)), "user_id": int(args.get("user_id", 0)), "duration": args.get("duration", 0)}}))
    return "✅ 【回执】：禁言操作已执行。"

@register_tool("set_group_whole_ban", "全员禁言开关", {"type": "object", "properties": {"group_id": {"type": "string"}, "enable": {"type": "boolean"}}, "required": ["group_id", "enable"]})
async def tool_set_group_whole_ban(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_group_whole_ban", "params": {"group_id": int(args.get("group_id", 0)), "enable": args.get("enable", False)}}))
    return "✅ 【回执】：全员禁言状态已更新。"

@register_tool("set_group_kick", "踢出群成员", {"type": "object", "properties": {"group_id": {"type": "string"}, "user_id": {"type": "string"}}, "required": ["group_id", "user_id"]})
async def tool_set_group_kick(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_group_kick", "params": {"group_id": int(args.get("group_id", 0)), "user_id": int(args.get("user_id", 0))}}))
    return "✅ 【回执】：踢人操作已执行。"

@register_tool("set_group_card", "修改群名片", {"type": "object", "properties": {"group_id": {"type": "string"}, "user_id": {"type": "string"}, "card": {"type": "string"}}, "required": ["group_id", "user_id", "card"]})
async def tool_set_group_card(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "set_group_card", "params": {"group_id": int(args.get("group_id", 0)), "user_id": int(args.get("user_id", 0)), "card": args.get("card", "")}}))
    return "✅ 【回执】：群名片已修改。"

@register_tool("set_group_name", "修改群名称", {"type": "object", "properties": {"group_id": {"type": "string"}, "group_name": {"type": "string"}}, "required": ["group_id", "group_name"]})
async def tool_set_group_name(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_group_name", "params": {"group_id": int(args.get("group_id", 0)), "group_name": args.get("group_name", "")}}))
    return "✅ 【回执】：群名称已修改。"

@register_tool("set_group_admin", "设置群管理员", {"type": "object", "properties": {"group_id": {"type": "string"}, "user_id": {"type": "string"}, "enable": {"type": "boolean"}}, "required": ["group_id", "user_id", "enable"]})
async def tool_set_group_admin(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_group_admin", "params": {"group_id": int(args.get("group_id", 0)), "user_id": int(args.get("user_id", 0)), "enable": args.get("enable", False)}}))
    return "✅ 【回执】：管理员设置已更新。"

@register_tool("leave_group", "退出群聊", {"type": "object", "properties": {"group_id": {"type": "string"}}, "required": ["group_id"]})
async def tool_leave_group(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_group_leave", "params": {"group_id": int(args.get("group_id", 0))}}))
    return "✅ 【回执】：退群指令已执行。"

# ==================== 5. 系统底座 ====================

@register_tool("run_python", "沙盒执行代码", {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]})
async def tool_run_python(ws, uid, platform, args, is_autonomous, extra_params=None): return await run_python(args.get("code", ""))

@register_tool("execute_shell", "沙盒执行Shell", {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]})
async def tool_execute_shell(ws, uid, platform, args, is_autonomous, extra_params=None): return await run_shell(args.get("cmd", ""))

@register_tool("get_system_info", "查询硬件状态", {"type": "object", "properties": {}})
async def tool_get_system_info(ws, uid, platform, args, is_autonomous, extra_params=None): return get_system_status()

@register_tool("list_local_files", "查看文件", {"type": "object", "properties": {"dir_path": {"type": "string"}}, "required": ["dir_path"]})
async def tool_list_local_files(ws, uid, platform, args, is_autonomous, extra_params=None):
    path = _map_path(args.get("dir_path", "/app"))
    try:
        if not os.path.exists(path): return f"目录 {path} 不存在。"
        return f"目录 {path} 下的文件列表：\n" + "\n".join(os.listdir(path)[:20])
    except Exception as e: return f"读取目录失败: {e}"

@register_tool("remember_important", "核心记忆", {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]})
async def tool_remember(ws, uid, platform, args, is_autonomous, extra_params=None):
    write_important_memory(args.get("content", ""))
    return "✅ 【回执】：已刻入核心记忆。"

# ==================== 统一执行入口 ====================
async def execute_tool(ws, uid, platform, name, args, is_autonomous=False, extra_params=None):
    if name not in TOOL_FUNCTIONS: return f"【报错】：未知工具 {name}"
    try: return await TOOL_FUNCTIONS[name](ws, uid, platform, args, is_autonomous, extra_params)
    except Exception as e: return f"工具执行异常: {e}"
