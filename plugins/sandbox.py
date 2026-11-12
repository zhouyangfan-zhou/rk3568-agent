import asyncio
import config
from config import docker_client, BASE_DIR

CONTAINER_NAME = "wanxing_sandbox"

def ensure_container():
    if not docker_client: return None
    try:
        container = docker_client.containers.get(CONTAINER_NAME)
        if container.status != "running": container.start()
        return container
    except Exception:
        try:
            return docker_client.containers.run(
                "python:3.11-slim", command="sleep infinity", name=CONTAINER_NAME,
                volumes={BASE_DIR: {'bind': '/app', 'mode': 'rw'}}, working_dir='/app', detach=True
            )
        except: return None

def docker_exec_sync(cmd_list):
    container = ensure_container()
    if not container: return "Docker未就绪"
    try:
        exec_result = container.exec_run(cmd_list, workdir="/app")
        output = exec_result.output.decode('utf-8').strip()
        if exec_result.exit_code != 0: return f"【执行失败 {exec_result.exit_code}】:\n{output[:2000]}"
        return output[:2000] or "执行成功（无输出）"
    except Exception as e: return f"沙盒报错: {e}"

async def run_python(code: str):
    if any(bad in code for bad in ["shutil.rmtree", "os.remove('/')", "rm -rf /"]):
        return "【安全拦截】：高危自毁指令被阻止！"
    return await asyncio.to_thread(docker_exec_sync, ["timeout", "15s", "python3", "-c", code])

async def run_shell(cmd: str):
    if any(bad in cmd for bad in ["rm -rf /", "mkfs", "dd if="]):
        return "【安全拦截】：高危自毁指令被阻止！"
    return await asyncio.to_thread(docker_exec_sync, ["timeout", "15s", "sh", "-c", cmd])
