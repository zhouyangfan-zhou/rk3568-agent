import os, json, httpx, psutil
from dotenv import load_dotenv

# 🚨 自动加载 .env 文件中的配置
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

try:
    import docker
    docker_client = docker.from_env()
except:
    docker_client = None

# 🚨 从环境变量读取 Key 和参数，带默认值兜底
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-default")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "sk-default")
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "sk-default")
DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "sk-default")

MASTER_QQ = os.getenv("MASTER_QQ", "2362267929")
MASTER_WXID = os.getenv("MASTER_WXID", "wxid_xxxxxxx")

# 🚨 系统路径（这些不需要经常改，保留在这里）
BASE_DIR = "/home/ztl/rk-agent"
MEM_DIR = f"{BASE_DIR}/memory_data"
os.makedirs(MEM_DIR, exist_ok=True)
DB_PATH = f"{MEM_DIR}/core.db"
WHITELIST_FILE = f"{BASE_DIR}/whitelist.json"
AUDIO_DIR = f"{BASE_DIR}/snowluma-data/audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

active_websockets = {}
IS_TASK_RUNNING = False
http_client = httpx.AsyncClient(timeout=60, trust_env=False, headers={"Connection": "close"})

def get_system_status():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f: temp = int(f.read()) / 1000.0
        return f"CPU温度: {temp}℃, 占用: {psutil.cpu_percent()}%, 内存: {psutil.virtual_memory().percent}%"
    except: return "系统状态未知"

def load_json(path):
    if not os.path.exists(path): return {}
    try:
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_files(uid):
    return f"{MEM_DIR}/user_{uid}_chat.json", f"{MEM_DIR}/user_{uid}_vector.json"
