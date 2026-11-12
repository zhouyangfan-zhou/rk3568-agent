import asyncio, websockets, json, os, base64, subprocess, edge_tts

async def handle_conn(ws):
    print("🎯 SnowLuma 已连接！准备发送测试语音包...")
    
    # 1. 现场生成一段语音
    audio_dir = "/home/ztl/rk-agent/snowluma-data/audio"
    os.makedirs(audio_dir, exist_ok=True)
    mp3_file = f"{audio_dir}/raw_test.mp3"
    amr_file = f"{audio_dir}/raw_test.amr"
    
    print("🎙️ 正在生成测试语音...")
    communicate = edge_tts.Communicate("这是底层数据流测试，如果你能听到，说明通道没问题。", "zh-CN-XiaoxiaoNeural")
    await communicate.save(mp3_file)
    subprocess.run(f'ffmpeg -y -i {mp3_file} -ac 1 -ar 8000 {amr_file}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    with open(amr_file, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode('utf-8')

    # 2. 依次尝试各种格式（每次间隔3秒，让你看清楚手机有没有反应）
    test_cases = [
        # 格式1：最纯正的 CQ 码 Base64 (没有多余参数)
        {"name": "1. 纯 CQ 码 base64", "message": f"[CQ:record,file=base64://{b64_data}]"},
        
        # 格式2：数组形式的 base64
        {"name": "2. 数组 base64", "message": [{"type": "record", "data": {"file": f"base64://{b64_data}"}}]},
        
        # 格式3：本地路径 record
        {"name": "3. 本地绝对路径 record", "message": [{"type": "record", "data": {"file": "file:///app/data/audio/raw_test.amr"}}]},
        
        # 格式4：本地路径 voice (有些框架专吃这个词)
        {"name": "4. 本地绝对路径 voice", "message": [{"type": "voice", "data": {"file": "file:///app/data/audio/raw_test.amr"}}]}
    ]

    for case in test_cases:
        print(f"\n======================================")
        print(f"📡 正在测试格式: {case['name']}")
        payload = {
            "action": "send_private_msg",
            "params": {
                "user_id": 2362267929,
                "message": case['message']
            }
        }
        try:
            await ws.send(json.dumps(payload))
            print(f"✅ 发送指令成功。请盯着手机 QQ 看有没有弹出语音条！")
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            
        await asyncio.sleep(4) # 停顿4秒，方便你检查手机

    print("\n🏁 所有格式测试完毕！")
    print("如果一条都没收到，说明 SnowLuma 底层把语音全拦截了。")
    print("如果收到了某一条，请记住对应的数字！")
    # 清理文件
    os.remove(mp3_file)
    os.remove(amr_file)
    print("服务已关闭，你可以去重启主程序了。")

async def main():
    # 监听 3002 端口，截胡 SnowLuma 的连接
    async with websockets.serve(handle_conn, "0.0.0.0", 3002):
        print("🚀 截胡服务已启动，等待 SnowLuma 重连 (请等大概5-10秒)...")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
