import asyncio, edge_tts, subprocess, os, base64

async def test_main_logic():
    uid = "2362267929"
    text = "晚星最后的声音测试"
    speed = 1.0
    emotion = "neutral"
    
    try:
        tts_dir = "/home/ztl/rk-agent/snowluma-data/tts"
        os.makedirs(tts_dir, exist_ok=True)
        
        mp3_file = f"/tmp/edge_{uid}.mp3"
        amr_file = f"{tts_dir}/v_{uid}.amr"
        
        rate_str = "+0%"
        if speed > 1.0: rate_str = f"+{int((float(speed)-1.0)*100)}%"
        elif speed < 1.0: rate_str = f"-{int((1.0-float(speed))*100)}%"
        
        print("1. 正在测试 edge-tts 生成...")
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural", rate=rate_str)
        await communicate.save(mp3_file)
        if os.path.exists(mp3_file):
            print(f"✅ MP3 生成成功: {mp3_file} ({os.path.getsize(mp3_file)} bytes)")
        
        print("2. 正在测试 ffmpeg 转码...")
        cmd = f'ffmpeg -y -i {mp3_file} -ac 1 -ar 8000 {amr_file}'
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, stderr = await proc.communicate()
        
        if os.path.exists(amr_file) and os.path.getsize(amr_file) > 0:
            print(f"✅ AMR 转码成功: {amr_file} ({os.path.getsize(amr_file)} bytes)")
        else:
            print(f"❌ AMR 转码失败！报错:\n{stderr.decode('utf-8')}")
            return

        print("3. 正在测试 Base64 编码...")
        with open(amr_file, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode('utf-8')
        print(f"✅ Base64 编码成功，长度: {len(b64_data)}")
        
        print("🎉 全部逻辑通过！如果 QQ 收不到，说明 SnowLuma 吞了。")
        os.remove(mp3_file)
        os.remove(amr_file)
        
    except Exception as e:
        print(f"❌ 发生异常: {e}")

if __name__ == "__main__":
    asyncio.run(test_main_logic())
