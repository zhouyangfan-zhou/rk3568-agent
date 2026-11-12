import asyncio, config
from config import docker_client, BASE_DIR

def docker_exec(cmd, is_python=False):
    if not docker_client: 
        return "Docker未就绪，请主人检查 daemon。"
    try:
        # 基础环境提示
        cmd_list = ["python", "-c", cmd] if is_python else ["sh", "-c", cmd]
        
        # 创建容器（40秒超时给冷启动留时间）
        container = docker_client.containers.run(
            "python:3.11-slim", cmd_list,
            volumes={BASE_DIR: {'bind': '/app', 'mode': 'rw'}},
            working_dir='/app', 
            detach=True, 
            stdout=True, 
            stderr=True
        )
        
        try:
            container.wait(timeout=40)
            logs = container.logs(stdout=True, stderr=False).decode('utf-8').strip()
            errs = container.logs(stdout=False, stderr=True).decode('utf-8').strip()
            container.remove(force=True)
            
            if errs:
                return f"【执行输出】:\n{logs}\n【报错】:\n{errs}"
            return logs[:2000] or "执行成功（无输出）"
            
        except Exception as e:
            container.remove(force=True)
            return "【沙盒熔断】：代码执行超时（40秒），已被强制终止！"
            
    except Exception as e: 
        return f"沙盒严重报错: {e}"

async def run_python(code): 
    env_hint = "# 注意：当前工作目录是 /app，已挂载宿主机。\n"
    return await asyncio.to_thread(docker_exec, env_hint + code, True)

async def run_shell(cmd): 
    if "rm -rf /" in cmd or "mkfs" in cmd:
        return "【系统拦截】：高危自毁指令被阻止！"
    
    # 如果有长任务，标记状态
    if "nohup" in cmd or "sleep" in cmd: 
        config.IS_TASK_RUNNING = True
        
    # 注入环境上下文
    final_cmd = f"echo '--- [Sandbox] 当前工作目录: /app ---' && {cmd}"
    return await asyncio.to_thread(docker_exec, final_cmd, False)
