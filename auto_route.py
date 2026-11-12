import subprocess
import time
import re
import asyncio
import json

TARGET_IP = "223.5.5.5" 

async def ping_task(interface):
    """测试指定网卡的延迟"""
    try:
        # 发 2 个包，超时 1 秒
        cmd = ["ping", "-I", interface, "-c", "2", "-W", "1", TARGET_IP]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _ = await proc.communicate()
        
        if proc.returncode != 0: return 9999
        output = stdout.decode()
        match = re.search(r'rtt min/avg/max/mdev = [\d\.]+/([\d\.]+)/', output)
        return float(match.group(1)) if match else 9999
    except: return 9999

def get_active_networks():
    """🚨 核心黑科技：自动侦察系统中所有插着网线且配置了网关的网卡"""
    active_nets = []
    try:
        # 1. 获取所有网卡的状态 (JSON 格式)
        link_info = subprocess.check_output(["ip", "-j", "link"]).decode('utf-8')
        links = json.loads(link_info)
        
        for link in links:
            iface = link.get("ifname")
            # 过滤掉本地回环(lo)和虚拟网卡(docker0, veth等)
            if iface == "lo" or iface.startswith(("docker", "br-", "veth", "tailscale")): 
                continue
            # 只处理处于 UP 状态的网卡
            if link.get("operstate") != "UP": 
                continue
                
            # 2. 查找这个网卡对应的网关
            try:
                route_info = subprocess.check_output(["ip", "route", "show", "dev", iface]).decode('utf-8')
                # 提取类似 "default via 192.168.1.1" 中的网关 IP
                match = re.search(r'default via ([\d\.]+)', route_info)
                if match:
                    gateway = match.group(1)
                    active_nets.append({"name": iface, "gateway": gateway})
            except: pass
    except Exception as e:
        print(f"侦察网络失败: {e}")
    return active_nets

def switch_route(interface, gateway):
    """切换默认路由"""
    try:
        subprocess.run(["sudo", "ip", "route", "del", "default"], capture_output=True)
        subprocess.run(["sudo", "ip", "route", "add", "default", "via", gateway, "dev", interface], check=True)
        return True
    except: return False

async def main_loop():
    print("🚀 全自动智能寻优引擎启动！无需配置，自动侦察并发测速...")
    current_best = None
    
    while True:
        start_time = time.time()
        
        # 1. 动态获取当前有网的网卡和网关
        networks = get_active_networks()
        
        if not networks:
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ 未检测到任何可用的物理网卡或网关（是不是没插网线？）")
            await asyncio.sleep(10)
            continue
            
        # 2. 并发测速
        tasks = [ping_task(net["name"]) for net in networks]
        latencies_ms = await asyncio.gather(*tasks)
        
        # 3. 组合结果并排序
        results = []
        for i, latency in enumerate(latencies_ms):
            net = networks[i]
            results.append((latency, net))
            print(f"[{time.strftime('%H:%M:%S')}] 网卡 {net['name']} (网关:{net['gateway']}) 延迟: {latency} ms")
            
        results.sort(key=lambda x: x[0])
        best_latency, best_net = results[0]
        
        # 4. 判断与切换
        if best_latency >= 9999:
            print("❌ 警告：所有网卡均无法连接外网！")
        else:
            if current_best != best_net["name"]:
                print(f"⚡ 发现最优网络：{best_net['name']} ({best_latency}ms)，正在动态切换路由...")
                if switch_route(best_net["name"], best_net["gateway"]):
                    current_best = best_net["name"]
                    print(f"✅ 切换成功！当前首选出口：{current_best}")
            else:
                pass # 当前已经是最优，保持安静，不刷屏
                
        # 5. 精确控制 10 秒周期
        elapsed = time.time() - start_time
        sleep_time = max(0, 10 - elapsed)
        await asyncio.sleep(sleep_time)

if __name__ == "__main__":
    asyncio.run(main_loop())
