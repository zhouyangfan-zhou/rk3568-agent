import asyncio, edge_tts, subprocess, os, base64, httpx, websockets, json, uuid

async def debug_send():
    print("=== [1/4] 测试 Edge-TTS 语音生成 ===")
    test_id = str(uuid.uuid4())[:8]
    mp3_file = f"/tmp/debug_{test_id}.mp3"
    amr_file = f"/tmp/debug_{test_id}.amr"
    text = "这是终端独立测试语音，如果你能听到，说明底层发送成功。"
    
    try:
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(mp3_file)
        print(f"✅ MP3 生成成功: {mp3_file} ({os.path.getsize(mp3_file)} 字节)")
    except Exception as e:
        print(f"❌ MP3 生成失败: {e}")
        return

    print("\n=== [2/4] 测试 FFmpeg 转码 ===")
    cmd = f'ffmpeg -y -i {mp3_file} -ac 1 -ar 8000 {amr_file}'
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if os.path.exists(amr_file) and os.path.getsize(amr_file) > 0:
        print(f"✅ AMR 转码成功: {amr_file} ({os.path.getsize(amr_file)} 字节)")
    else:
        print(f"❌ AMR 转码失败:\n{proc.stderr[:300]}")
        return

    with open(amr_file, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode('utf-8')

    print("\n=== [3/4] 测试发送方式一：HTTP API 3000 端口 ===")
    url = "http://127.0.0.1:3000/send_private_msg"
    payload_http = {
        "user_id": 2362267929,
        "message": [{"type": "record", "data": {"file": f"base64://{b64_data}"}}]
    }
    
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.post(url, json=payload_http)
            print(f"HTTP 状态码: {resp.status_code}")
            print(f"HTTP 响应: {resp.text}")
    except Exception as e:
        print(f"❌ HTTP 发送失败: {e}")

    print("\n=== [4/4] 测试发送方式二：正向 WebSocket 3001 端口 ===")
    # 尝试不带 Token 和带 Token 两种连接
    token = "27b3fb5a28c2cdabea2" 
    uris = [
        "ws://127.0.0.1:3001/",
        f"ws://127.0.0.1:3001/?access_token={token}"
    ]
    
    for uri in uris:
        try:
            print(f"尝试连接: {uri}")
            async with websockets.connect(uri) as ws:
                payload_ws = {
                    "action": "send_private_msg",
                    "params": {
                        "user_id": 2362267929,
                        "message": [{"type": "record", "data": {"file": f"base64://{b64_data}"}}]
                    }
                }
                await ws.send(json.dumps(payload_ws))
                print(f"✅ WS 发送指令已执行，等待响应...")
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    print(f"⬅️ WS 响应: {resp}")
                except asyncio.TimeoutError:
                    print("⚠️ 发送后无响应（如果手机没收到，说明被底层直接静默吞了）")
        except Exception as e:
            print(f"❌ WS 连接/发送失败: {e}")

    os.remove(mp3_file)
    os.remove(amr_file)
    print("\n=== 调试结束，请检查手机 QQ 是否收到语音 ===")

if __name__ == "__main__":
    asyncio.run(debug_send())
