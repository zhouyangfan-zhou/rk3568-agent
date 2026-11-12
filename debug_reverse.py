import asyncio, websockets, json, os, edge_tts, subprocess, base64

async def debug():
    # 1. 生成音频
    print("=== 1. 生成测试语音 ===")
    mp3 = "/tmp/rev_test.mp3"
    amr = "/home/ztl/rk-agent/snowluma-data/tts/rev_test.amr"
    os.makedirs("/home/ztl/rk-agent/snowluma-data/tts", exist_ok=True)
    
    communicate = edge_tts.Communicate("这是通过反向通道，使用基础数据流发送的测试。", "zh-CN-XiaoxiaoNeural")
    await communicate.save(mp3)
    
    subprocess.run(f'ffmpeg -y -i {mp3} -ac 1 -ar 8000 {amr}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("✅ 音频准备完毕")
    
    with open(amr, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode('utf-8')

    # 2. 通过主程序的端口（模拟 SnowLuma 发过来）去发送
    print("\n=== 2. 尝试通过反向 WS 基础格式发送 ===")
    
    # 这里模拟的是 OneBot 标准发送格式
    cq_msg = f"[CQ:record,file=base64://{b64_data}]"
    payload = {
        "action": "send_private_msg",
        "params": {
            "user_id": 2362267929,
            "message": cq_msg  # 直接给 CQ 码字符串
        }
    }
    
    # 因为你的主程序在监听 3002，我这里连 3002 是在测试代码
    # 但真正发出去，还是得看主程序怎么调 SnowLuma
    # 这里我们直接打印出 payload 看看，不做真实发送，以防搞坏主程序
    print(f"📦 准备发送的 Payload (长度 {len(json.dumps(payload))} 字节):")
    print(json.dumps(payload)[:200] + " ... (省略后续Base64内容)")
    print("✅ 主程序如果收到这个格式，应该能解析。")

if __name__ == "__main__":
    asyncio.run(debug())
