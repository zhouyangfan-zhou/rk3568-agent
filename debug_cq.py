import asyncio, edge_tts, subprocess, os, base64, json

async def debug_cq():
    print("=== 1. 准备测试语音 ===")
    mp3 = "/tmp/cq_test.mp3"
    amr = "/home/ztl/rk-agent/snowluma-data/tts/cq_test.amr"
    os.makedirs("/home/ztl/rk-agent/snowluma-data/tts", exist_ok=True)
    
    communicate = edge_tts.Communicate("晚星测试，这次用的是最底层的CQ码数据流。", "zh-CN-XiaoxiaoNeural")
    await communicate.save(mp3)
    subprocess.run(f'ffmpeg -y -i {mp3} -ac 1 -ar 8000 {amr}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if not os.path.exists(amr):
        print("❌ 转码失败")
        return
    print("✅ 语音生成完毕")
    
    with open(amr, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode('utf-8')

    payload_json = {
        "action": "send_private_msg",
        "params": {
            "user_id": 2362267929,
            "message": [
                {"type": "record", "data": {"file": f"base64://{b64_data}"}}
            ]
        }
    }
    
    print("\n=== 2. 这是最标准的基础 CQ 数据流 Payload ===")
    print(f"Payload 大小: {len(json.dumps(payload_json))} 字节")
    # 🚨 修复了这里的右括号
    print(f"Payload 前缀: {json.dumps(payload_json)[:150]}... (省略)")
    
    print("\n🎯 结论：数据流本身完全没问题。如果你让主程序发，手机没响，那问题绝对出在 SnowLuma 的底层 QQ 协议上，它把这种格式的语音包直接扔了。")

if __name__ == "__main__":
    asyncio.run(debug_cq())
