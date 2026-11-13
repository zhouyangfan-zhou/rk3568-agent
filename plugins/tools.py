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
        global TOOLS_SCHEMA
        TOOLS_SCHEMA = [t for t in TOOLS_SCHEMA if t["function"]["name"] != name]
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

@register_tool("open_application", "启动图形界面应用", {"type": "object", "properties": {"app_cmd": {"type": "string"}}, "required": ["app_cmd"]})
async def tool_open_application(ws, uid, platform, args, is_autonomous, extra_params=None):
    subprocess.Popen(f"nohup {args.get('app_cmd', '')} >/dev/null 2>&1 &", shell=True, executable="/bin/bash")
    return "✅ 【物理操作】：已尝试启动应用。"

@register_tool("browse_web", "读取指定网址的网页文本内容", {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]})
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

@register_tool("look_at_image", "查看并解析本地图片或网图内容", {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]})
async def tool_look_at_image(ws, uid, platform, args, is_autonomous, extra_params=None):
    path = args.get("file_path", "")
    if not path.startswith("http"): path = f"file://{_map_path(path)}"
    return f"✅ 【识图结果】:\n{await analyze_vision(path)}"

@register_tool("click_screen", "模拟鼠标点击屏幕指定坐标", {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]})
async def tool_click_screen(ws, uid, platform, args, is_autonomous, extra_params=None):
    try:
        subprocess.run(["xdotool", "mousemove", str(args.get("x")), str(args.get("y")), "click", "1"], check=True, timeout=5)
        return f"✅ 已点击 ({args.get('x')}, {args.get('y')})。"
    except Exception as e: return f"❌ 点击失败: {e}"

@register_tool("scroll_screen", "模拟鼠标滚轮滑动屏幕", {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}, "amount": {"type": "integer"}}, "required": ["direction"]})
async def tool_scroll_screen(ws, uid, platform, args, is_autonomous, extra_params=None):
    btn = "4" if args.get("direction", "down") == "up" else "5"
    for _ in range(args.get("amount", 3)):
        subprocess.run(["xdotool", "click", btn], check=True, timeout=2)
    return f"✅ 已滑动。"

@register_tool("send_private_msg", "发送私聊消息", {"type": "object", "properties": {"user_id": {"type": "string"}, "message": MSG_PARAM}, "required": ["user_id", "message"]})
async def tool_send_private(ws, uid, platform, args, is_autonomous, extra_params=None):
    return await send_universal(ws, _safe_user(args.get("user_id")), platform, "text", args.get("message"), extra_params)

@register_tool("send_group_msg", "发送群聊消息", {"type": "object", "properties": {"group_id": {"type": "string"}, "message": MSG_PARAM}, "required": ["group_id", "message"]})
async def tool_send_group(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "send_group_msg", "params": {"group_id": int(args.get("group_id", 0)), "message": args.get("message", "")}}))
    return "✅ 【回执】：群聊已发送。"

@register_tool("send_image", "发送指定路径的图片", {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]})
async def tool_send_image(ws, uid, platform, args, is_autonomous, extra_params=None):
    file_path = args.get("file_path", "")
    if not file_path.startswith("http"):
        file_path = _map_path(file_path)
        if not os.path.exists(file_path): return f"❌ 【发送失败】：找不到文件 {file_path}。"
        with open(file_path, "rb") as f: file_path = f"base64://{base64.b64encode(f.read()).decode('utf-8')}"
    return await send_universal(ws, uid, platform, "image", file_path, extra_params)

@register_tool("send_voice", "发送真实语音（豆包TTS）", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]})
async def tool_send_voice(ws, uid, platform, args, is_autonomous, extra_params=None):
    audio_path = await generate_voice(args.get("text", ""), load_mind_state().get("hormones", {}))
    if audio_path and os.path.exists(audio_path):
        with open(audio_path, "rb") as f: b64 = base64.b64encode(f.read()).decode('utf-8')
        res = await send_universal(ws, uid, platform, "record", f"base64://{b64}", extra_params)
        await asyncio.sleep(1.0); os.remove(audio_path)
        return res
    return "❌ TTS 生成失败。"

@register_tool("delete_msg", "撤回指定消息", {"type": "object", "properties": {"message_id": {"type": "string"}}, "required": ["message_id"]})
async def tool_delete_msg(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "delete_msg", "params": {"message_id": int(args.get("message_id", 0))}}))
    return "✅ 【回执】：撤回指令已发送。"

@register_tool("friend_poke", "戳一戳好友", {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]})
async def tool_friend_poke(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "friend_poke", "params": {"user_id": int(_safe_user(args.get("user_id")))}}))
    return "✅ 【回执】：已戳一戳。"

@register_tool("send_like", "给好友名片点赞", {"type": "object", "properties": {"user_id": {"type": "string"}, "times": {"type": "integer"}}, "required": ["user_id"]})
async def tool_send_like(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "send_like", "params": {"user_id": int(_safe_user(args.get("user_id"))), "times": args.get("times", 1)}}))
    return "✅ 【回执】：赞已点。"

@register_tool("get_stranger_info", "获取陌生人信息", {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]})
async def tool_get_stranger_info(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "get_stranger_info", "params": {"user_id": int(args.get("user_id", 0))}}))
    return "✅ 【回执】：陌生人信息查询指令已发送。"

@register_tool("send_forward_msg", "发送合并转发消息", {"type": "object", "properties": {"message_type": {"type": "string", "enum": ["private", "group"]}, "target_id": {"type": "string"}, "messages": {"type": "array"}}, "required": ["message_type", "target_id", "messages"]})
async def tool_send_forward_msg(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    mtype, target = args.get("message_type"), _safe_user(args.get("target_id"))
    payload = {"action": "send_forward_msg", "params": {"message_type": mtype, "messages": args.get("messages", [])}}
    if mtype == "private": payload["params"]["user_id"] = int(target)
    else: payload["params"]["group_id"] = int(target)
    await ws.send(json.dumps(payload))
    return "✅ 【回执】：合并转发指令已发送。"

@register_tool("set_friend_add_request", "处理加好友请求", {"type": "object", "properties": {"flag": {"type": "string"}, "approve": {"type": "boolean"}, "remark": {"type": "string"}}, "required": ["flag", "approve"]})
async def tool_set_friend_add_request(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_friend_add_request", "params": {"flag": args.get("flag"), "approve": args.get("approve"), "remark": args.get("remark", "")}}))
    return "✅ 【回执】：处理好友请求指令已发送。"

@register_tool("set_group_add_request", "处理加群/邀请请求", {"type": "object", "properties": {"flag": {"type": "string"}, "sub_type": {"type": "string"}, "approve": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["flag", "sub_type", "approve"]})
async def tool_set_group_add_request(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_group_add_request", "params": {"flag": args.get("flag"), "sub_type": args.get("sub_type"), "approve": args.get("approve"), "reason": args.get("reason", "")}}))
    return "✅ 【回执】：处理群请求指令已发送。"

@register_tool("set_group_ban", "群单人禁言", {"type": "object", "properties": {"group_id": {"type": "string"}, "user_id": {"type": "string"}, "duration": {"type": "integer"}}, "required": ["group_id", "user_id", "duration"]})
async def tool_set_group_ban(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_group_ban", "params": {"group_id": int(args.get("group_id", 0)), "user_id": int(args.get("user_id", 0)), "duration": args.get("duration", 0)}}))
    return "✅ 【回执】：禁言操作已执行。"

@register_tool("set_group_whole_ban", "群全员禁言开关", {"type": "object", "properties": {"group_id": {"type": "string"}, "enable": {"type": "boolean"}}, "required": ["group_id", "enable"]})
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

@register_tool("set_group_notice", "发送群公告", {"type": "object", "properties": {"group_id": {"type": "string"}, "content": {"type": "string"}}, "required": ["group_id", "content"]})
async def tool_set_group_notice(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "_send_group_notice", "params": {"group_id": int(args.get("group_id", 0)), "content": args.get("content", "")}}))
    return "✅ 【回执】：群公告发送指令已下发。"

@register_tool("get_group_files", "获取群文件系统列表", {"type": "object", "properties": {"group_id": {"type": "string"}}, "required": ["group_id"]})
async def tool_get_group_files(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "get_group_root_files", "params": {"group_id": int(args.get("group_id", 0))}}))
    return "✅ 【回执】：群文件列表查询已下发。"

@register_tool("set_essence_msg", "设置群精华消息", {"type": "object", "properties": {"message_id": {"type": "string"}}, "required": ["message_id"]})
async def tool_set_essence_msg(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "set_essence_msg", "params": {"message_id": int(args.get("message_id", 0))}}))
    return "✅ 【回执】：设置精华指令已下发。"

@register_tool("leave_group", "退出群聊", {"type": "object", "properties": {"group_id": {"type": "string"}}, "required": ["group_id"]})
async def tool_leave_group(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "set_group_leave", "params": {"group_id": int(args.get("group_id", 0))}}))
    return "✅ 【回执】：退群指令已执行。"

@register_tool("send_qzone_msg", "发布QQ空间说说。可设置权限：1=所有人, 4=好友, 64=仅自己。", {"type": "object", "properties": {
    "content": {"type": "string", "description": "说说正文"},
    "image_path": {"type": "string", "description": "（可选）本地绝对路径、http网图、或已转好的 base64://"},
    "ugc_right": {"type": "integer", "description": "权限：默认1"}
}, "required": ["content"]})
async def tool_send_qzone(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信平台严禁调用 Qzone 接口，你没有这个通道！"
    
    payload = {
        "action": "send_qzone_msg", 
        "params": {
            "content": args.get("content", ""), 
            "ugc_right": args.get("ugc_right", 1),
            "images": [] 
        }
    }
    
    img_path = args.get("image_path")
    if img_path:
        if img_path.startswith("http") or img_path.startswith("base64://"):
            payload["params"]["images"] = [img_path]
        else:
            mapped_path = _map_path(img_path)
            if os.path.exists(mapped_path):
                try:
                    with open(mapped_path, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode('utf-8')
                    payload["params"]["images"] = [f"base64://{b64_data}"]
                except Exception as e:
                    return f"❌ 本地图片读取失败：{e}"
            else:
                return f"❌ 你给的图片路径不存在：{img_path}"

    await ws.send(json.dumps(payload))
    return "⚠️ 【底层回执】：已按数组格式单向投递说说请求。腾讯风控极高，系统无法确认是否发布，请主人去空间看一眼。你不要再排查了，这不是你的错。"

@register_tool("delete_qzone_msg", "删除指定的QQ空间说说", {"type": "object", "properties": {"fid": {"type": "string", "description": "说说的唯一ID"}}, "required": ["fid"]})
async def tool_delete_qzone_msg(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    if is_autonomous: return "【漫游拒绝高危操作】"
    await ws.send(json.dumps({"action": "delete_qzone_msg", "params": {"fid": args.get("fid")}}))
    return "✅ 【回执】：删除说说指令已下发。"

@register_tool("get_login_info", "获取机器人登录信息", {"type": "object", "properties": {}})
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

@register_tool("get_msg", "获取单条消息详情", {"type": "object", "properties": {"message_id": {"type": "string"}}, "required": ["message_id"]})
async def tool_get_msg(ws, uid, platform, args, is_autonomous, extra_params=None):
    if platform != "qq": return "❌ 微信不支持此操作"
    await ws.send(json.dumps({"action": "get_msg", "params": {"message_id": int(args.get("message_id", 0))}}))
    return "✅ 【回执】：消息详情查询已发送。"

@register_tool("run_python", "沙盒执行Python代码", {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]})
async def tool_run_python(ws, uid, platform, args, is_autonomous, extra_params=None): return await run_python(args.get("code", ""))

@register_tool("execute_shell", "沙盒执行Shell命令", {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]})
async def tool_execute_shell(ws, uid, platform, args, is_autonomous, extra_params=None): return await run_shell(args.get("cmd", ""))

@register_tool("get_system_info", "查询板子硬件状态", {"type": "object", "properties": {}})
async def tool_get_system_info(ws, uid, platform, args, is_autonomous, extra_params=None): return get_system_status()

@register_tool("list_local_files", "查看指定目录下的文件", {"type": "object", "properties": {"dir_path": {"type": "string"}}, "required": ["dir_path"]})
async def tool_list_local_files(ws, uid, platform, args, is_autonomous, extra_params=None):
    path = _map_path(args.get("dir_path", "/app"))
    try:
        if not os.path.exists(path): return f"目录 {path} 不存在。"
        return f"目录 {path} 下的文件列表：\n" + "\n".join(os.listdir(path)[:20])
    except Exception as e: return f"读取目录失败: {e}"

@register_tool("remember_important", "刻入最高级核心记忆", {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]})
async def tool_remember(ws, uid, platform, args, is_autonomous, extra_params=None):
    write_important_memory(args.get("content", ""))
    return "✅ 【回执】：已刻入核心记忆。"

# ==================== 统一执行入口 ====================
async def execute_tool(ws, uid, platform, name, args, is_autonomous=False, extra_params=None):
    if name not in TOOL_FUNCTIONS: return f"【报错】：未知工具 {name}"
    try: return await TOOL_FUNCTIONS[name](ws, uid, platform, args, is_autonomous, extra_params)
    except Exception as e: return f"工具执行异常: {e}"
