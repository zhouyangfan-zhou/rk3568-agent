# -*- coding: utf-8 -*-
"""晚星定时任务调度器：持久化在 delayed_tasks.json，重启后可恢复"""
import asyncio, json, os, uuid, datetime

BASE_DIR = "/home/ztl/rk-agent"
TASK_FILE_CANDIDATES = [
    os.path.join(BASE_DIR, "delayed_tasks.json"),
    "/app/delayed_tasks.json",
]

def _task_file():
    for p in TASK_FILE_CANDIDATES:
        if os.path.exists(p):
            return p
    return TASK_FILE_CANDIDATES[-1]

def load_tasks():
    p = _task_file()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_tasks(tasks):
    p = _task_file()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[scheduler] 保存失败: {e}")
        return False

def add_task(run_time, content, uid):
    """run_time: 'YYYY-MM-DD HH:MM:SS' 或 datetime"""
    if isinstance(run_time, datetime.datetime):
        run_time = run_time.strftime("%Y-%m-%d %H:%M:%S")
    tid = str(uuid.uuid4())
    tasks = load_tasks()
    tasks[tid] = {"time": str(run_time), "content": str(content), "uid": str(uid)}
    save_tasks(tasks)
    return tid

def remove_task(tid):
    tasks = load_tasks()
    if tid in tasks:
        del tasks[tid]
        save_tasks(tasks)
        return True
    return False

def list_tasks(uid=None):
    tasks = load_tasks()
    if uid is None:
        return tasks
    return {k: v for k, v in tasks.items() if str(v.get("uid")) == str(uid)}

def _parse(t):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(t, fmt)
        except Exception:
            continue
    return None

async def run_scheduler(get_ws, send_func, catch_up=True, tick=15):
    """
    get_ws(uid) -> websocket 或 None
    send_func(ws, uid, text) -> 发消息协程
    catch_up: 重启后对已过期任务是否补发
    """
    print("[scheduler] 启动，任务文件:", _task_file())
    while True:
        try:
            tasks = load_tasks()
            now = datetime.datetime.now()
            changed = False
            for tid, task in list(tasks.items()):
                dt = _parse(task.get("time", ""))
                if dt is None:
                    print(f"[scheduler] 时间格式非法，跳过 {tid}: {task.get('time')}")
                    continue
                if dt > now:
                    continue
                uid = str(task.get("uid", ""))
                content = task.get("content", "")
                if dt < now and not catch_up:
                    del tasks[tid]; changed = True
                    print(f"[scheduler] 过期丢弃 {tid}")
                    continue
                ws = get_ws(uid)
                if ws is None:
                    continue  # 目标不在线，等下轮再试，不删任务
                try:
                    await send_func(ws, uid, content)
                    del tasks[tid]; changed = True
                    print(f"[scheduler] ✅ 已执行 {tid} -> {uid}: {content[:30]}")
                except Exception as e:
                    print(f"[scheduler] 发送失败 {tid}: {e}")
            if changed:
                save_tasks(tasks)
        except Exception as e:
            print(f"[scheduler] 轮询异常: {e}")
        await asyncio.sleep(tick)
