import sys
try: import sqlite3
except ImportError:
    import pysqlite3
    sys.modules['sqlite3'] = pysqlite3

import json, asyncio, os, base64
from weilink import WeiLink

wl = WeiLink(message_store=True)
CURRENT_TOKEN = None

def init_weilink():
    print("🔄 [WeChat] 正在初始化 Weilink...")
    try:
        wl.login()
        print("✅ [WeChat] 登录状态就绪！")
        wl.run_background() 
        print("👂 [WeChat] 后台长连接启动！")
    except Exception as e: print(f"❌ [WeChat] 初始化失败: {e}")

async def send_universal(ws, uid, platform, msg_type, content, extra_params=None):
    if platform == "wechat":
        try:
            # 🚨 终极补丁：先发送“正在输入”状态！很多官方 AI 必须走这个前置流程
            await asyncio.to_thread(wl.send_typing, uid)
            await asyncio.sleep(0.8) # 假装打一下字
            
            if msg_type == "text":
                # 直接调 send，让它自己去拿 token
                res = await asyncio.to_thread(wl.send, uid, content)
                
                # 彻底扒开 SendResult 的真面目！
                # 如果这个打印出来显示 remaining=0，那就是被腾讯限额了
                return f"✅ 微信发送返回: {res}"

            elif msg_type == "image":
                await asyncio.to_thread(wl.send, uid, "", image=content)
            elif msg_type == "record":
                if content.startswith("base64://"):
                    b64_data = content.replace("base64://", "")
                    temp_audio = "/app/temp_wechat_voice.mp3"
                    with open(temp_audio, "wb") as f: f.write(base64.b64decode(b64_data))
                    content = temp_audio
                await asyncio.to_thread(wl.send, uid, "", file=content)
                if os.path.exists(content) and "temp_wechat" in content: os.remove(content)
            return "✅ 微信发送成功"
        except Exception as e: 
            return f"❌ 微信发送异常: {e}"
    else:
        # QQ 发送逻辑不变
        if ws is None: return "❌ QQ 通道未连接"
        action = extra_params.get("action", "send_private_msg") if extra_params else "send_private_msg"
        params = {"user_id": int(uid) if uid.isdigit() else uid}
        if msg_type == "text": params["message"] = content
        elif msg_type == "image": params["message"] = [{"type": "image", "data": {"file": content}}]
        elif msg_type == "record": params["message"] = [{"type": "record", "data": {"file": content}}]
        await ws.send(json.dumps({"action": action, "params": params}))
        return "✅ QQ 发送成功"
