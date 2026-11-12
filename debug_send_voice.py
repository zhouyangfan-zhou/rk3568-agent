import asyncio, edge_tts, subprocess, os, base64, httpx, websockets, json, uuid

async def run_debug():
    print("=== 1. 独立生成测试语音 ===")
    mp3_file = f"/tmp/dbg_{uuid.uuid4().hex[:6]}.mp3"
    amr_file = f"/tmp/dbg_{uuid.uuid4().hex[:6]}.amr"
    text = "晚星底层调试，如果你听到这句，说明发送链路终于通了。"
    
    try:
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(mp3_file)
        subprocess.run(f'ffmpeg -y -i {mp3_file} -ac 1 -ar 8000 {amr_file}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if not os.path.exists(amr_file):
            print("❌ 转码失败")
            return
        print(f"✅ 语音文件准备完毕: {amr_file}")
        
        with open(amr_file, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"❌ 生成语音报错: {e}")
        return

    print("\n=== 2. 尝试 HTTP API (3000端口) ===")
    url = "http://127.0.0.1:3000/send_private_msg"
    payload = {"user_id": 2362267929, "message": [{"type": "record", "data": {"file": f"base64://{b64_data}"}}]}
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            resp = await c.post(url, json=payload)
            print(f"HTTP 状态码: {resp.status_code}")
            print(f"HTTP 响应: {resp.text}")
            if resp.status_code == 200:
                print("🎉 HTTP 发送成功！手机应该收到语音了。")
    except Exception as e:
        print(f"❌ HTTP 连不上 (说明3000端口根本没开或者没映射): {e}")

    print("\n=== 3. 尝试 正向 WS (3001端口) ===")
    # 测试带不同鉴权的 WS 连接
    uris = [
        ("无Token", "ws://127.0.0.1:3001/"),
        ("URL带Token", "ws://127.0.0.1:3001/?access_token=27b3fb5a28c2cdabea2"),
        ("Bearer Token", "ws://127.0.0.1:3001/", {"Authorization": "Bearer 27b3fb5a28c2cdabea2"}),
        ("纯Token Header", "ws://127.0.0.1:3001/", {"Authorization": "27b3fb5a28c2cdabea2"})
    ]

    for item in uris:
        name = item[0]
        uri = item[1]
        headers = item[2] if len(item) > 2 else {}
        
        print(f"--- 测试方式: {name} ---")
        try:
            async with websockets.connect(uri, additional_headers=headers) as ws:
                print("✅ WS 连接成功！")
                ws_payload = {"action": "send_private_msg", "params": {"user_id": 2267929, "message": [{"type": "record", "data": {"file": f"base64://{b64_data}"}}]}}
                # 注意上面故意写错个 user_id 看看服务器理不理
                ws_payload["params"]["user_id"] = 2362267929 # 改回来
                await ws.send(json.dumps(ws_payload))
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=2)
                    print(f"⬅️ 响应: {resp}")
                except:
                    print("✅ 发送指令成功，无响应（说明被吞了或发过去了）")
        except Exception as e:
            print(f"❌ 连接失败: {e}")

    os.remove(mp3_file)
    os.remove(amr_file)
    print("\n=== 调试结束，如果手机没响，说明除了 3002 反向通道，其他全废了 ===")

if __name__ == "__main__":
    asyncio.run(run_debug())
