from wcferry import Wcf, WxMsg
import asyncio
import json

# 连接到运行在 Docker 中的 WCF RPC 服务
# 如果适配器也跑在同一个 Docker 网络里，host 可能是 wcf 或 localhost
# 如果跑在宿主机，host 是 127.0.0.1，端口映射到 8001/8002
wcf = Wcf(host="127.0.0.1", port=8001)

def on_message(msg: WxMsg):
    """WCF 消息回调，转换为你的 Agent 格式"""
    if msg.from_self(): return # 忽略自己发的消息
    if msg.type != 0x01: return # 暂时只处理文本消息，图片/语音的 type 不同
    
    # 构造类似 OneBot 的 msg_data
    msg_data = {
        "post_type": "message",
        "message_type": "private", # 群聊 msg.roomid 不为空，可据此判断
        "user_id": msg.sender,
        "message": msg.content,
    }
    # 推入你的消息处理管道
    # 这里需要根据你的 main.py 中的消息入口进行调整
    # 例如：asyncio.run_coroutine_threadsafe(handle_msg(msg_data, ws_adapter, msg.sender), loop)
    print(f"收到消息: {msg.content}")

# 注册回调并启动
wcf.enable_receiving_msg()
wcf.register_msg_callback(on_message)

# 保持运行
import time
while True:
    time.sleep(1)
