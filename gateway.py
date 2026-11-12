CURRENT_TOKEN = None
import sys
try: import sqlite3
except ImportError:
    import pysqlite3
    sys.modules['sqlite3'] = pysqlite3

import json, asyncio, os, base64
from weilink import WeiLink
from config import MASTER_QQ

wl = WeiLink(message_store=True)

def init_weilink():
    print("🔄 [WeChat] 正在初始化 Weilink 并抢占长连接...")
    try:
        wl.login()
        print("✅ [WeChat] 登录状态就绪！")
        wl.run_background() 
        print("👂 [WeChat] Weilink 后台长连接已成功启动！")
    except Exception as e: print(f"❌ [WeChat] 初始化失败: {e}")

async def send_universal(ws, uid, platform, msg_type, content, extra_params=None):
    if platform == "wechat":
        try:
            target = str(uid)
            if msg_type == "text":
                ok = await asyncio.to_thread(wl.send, target, content)
                if not ok: return "❌ 微信发送失败: 可能缺少 context_token 或超时"
            elif msg_type == "image":
                if content.startswith("base64://"):
                    b64_data = content.replace("base64://", "")
                    temp_img = "/app/temp_wechat_img.jpg"
                    with open(temp_img, "wb") as f: f.write(base64.b64decode(b64_data))
                    content = temp_img
                await asyncio.to_thread(wl.send, target, "", image=content)
                if os.path.exists(content) and "temp_wechat" in content: os.remove(content)
            elif msg_type == "record":
                if content.startswith("base64://"):
                    b64_data = content.replace("base64://", "")
                    temp_audio = "/app/temp_wechat_voice.mp3"
                    with open(temp_audio, "wb") as f: f.write(base64.b64decode(b64_data))
                    content = temp_audio
                await asyncio.to_thread(wl.send, target, "", file=content)
                if os.path.exists(content) and "temp_wechat" in content: os.remove(content)
            return "✅ 微信发送成功"
        except Exception as e: return f"❌ 微信发送失败: {e}"
    else:
        if ws is None: return "❌ QQ 通道未连接"
        action = extra_params.get("action", "send_private_msg") if extra_params else "send_private_msg"
        params = {"user_id": int(uid) if uid.isdigit() else uid}
        if msg_type == "text": params["message"] = content
        elif msg_type == "image": params["message"] = [{"type": "image", "data": {"file": content}}]
        elif msg_type == "record": params["message"] = [{"type": "record", "data": {"file": content}}]
        await ws.send(json.dumps({"action": action, "params": params}))
        return "✅ QQ 发送成功"
