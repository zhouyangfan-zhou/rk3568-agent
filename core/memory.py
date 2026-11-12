import sys
try: import sqlite3
except ImportError:
    import pysqlite3
    sys.modules['sqlite3'] = pysqlite3
import sqlite3, json, time, os
import numpy as np
from config import DB_PATH, MEM_DIR, SILICONFLOW_API_KEY, http_client

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS important_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, time REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mind_state (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()
init_db()

def write_important_memory(content):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO important_memory (content, time) VALUES (?, ?)", (content, time.time()))
    conn.commit()
    conn.close()

def read_important_memory():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT content FROM important_memory ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return "\n【💎 核心重要记忆】：\n" + "\n".join([r[0] for r in rows]) if rows else ""

def save_mind_state(state_dict):
    conn = sqlite3.connect(DB_PATH)
    for k, v in state_dict.items():
        conn.execute("INSERT OR REPLACE INTO mind_state (key, value) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))
    conn.commit()
    conn.close()

def load_mind_state():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT key, value FROM mind_state").fetchall()
    conn.close()
    return {k: json.loads(v) for k, v in rows}

def read_recent_chat(uid, limit=15):
    chat_file, _ = get_user_files(uid)
    db = json_load(chat_file)
    history = []
    for c in db.get("history", [])[-limit:]:
        history.append({"role": "user", "content": c["user"]})
        history.append({"role": "assistant", "content": c["ai"]})
    return history

def save_full_chat(uid, user_text, ai_reply):
    chat_file, _ = get_user_files(uid)
    db = json_load(chat_file)
    if "history" not in db: db["history"] = []
    db["history"].append({"user": user_text, "ai": ai_reply})
    if len(db["history"]) > 50: db["history"] = db["history"][-50:]
    json_save(chat_file, db)

async def get_embedding(text):
    try:
        r = await http_client.post("https://api.siliconflow.cn/v1/embeddings", headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}"}, json={"model": "BAAI/bge-m3", "input": text}, timeout=15)
        return r.json()["data"][0]["embedding"]
    except: return None

async def search_memory(uid, query, top_k=3):
    query_vec = await get_embedding(query)
    if not query_vec: return ""
    _, vector_file = get_user_files(uid)
    mem_db = json_load(vector_file)
    if "list" not in mem_db: return ""
    scored = []
    for item in mem_db["list"]:
        if not isinstance(item, dict) or "vector" not in item: continue
        a, b = np.array(query_vec), np.array(item["vector"])
        score = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        if score > 0.4: scored.append((score, item["text"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    return "\n【🧠 潜意识回忆】：\n" + "\n".join([t for s, t in scored[:top_k]]) if scored else ""

async def auto_summarize_and_store(uid, dialog_text):
    from config import DEEPSEEK_API_KEY
    _, vector_file = get_user_files(uid)
    try:
        r = await http_client.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, json={"model": "deepseek-chat", "messages": [{"role": "system", "content": "提取重点，精简总结。没有则输出'无'。"}, {"role": "user", "content": dialog_text}], "temperature": 0.3}, timeout=30)
        summary = r.json()["choices"][0]["message"]["content"].strip()
        if summary == "无" or len(summary) < 2: return
        vector = await get_embedding(summary)
        if not vector: return
        mem_db = json_load(vector_file)
        if "list" not in mem_db: mem_db["list"] = []
        mem_db["list"].append({"text": summary, "vector": vector, "time": time.time()})
        if len(mem_db["list"]) > 300: mem_db["list"] = mem_db["list"][-300:] 
        json_save(vector_file, mem_db)
    except: pass

def save_group_chat(gid, user_text):
    g_file = f"{MEM_DIR}/group_{gid}_chat.json"
    db = json_load(g_file)
    if "history" not in db: db["history"] = []
    db["history"].append({"time": time.strftime("%H:%M"), "user": user_text})
    if len(db["history"]) > 100: db["history"] = db["history"][-100:]
    json_save(g_file, db)

def json_load(path):
    if not os.path.exists(path): return {}
    try:
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def json_save(path, data):
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_files(uid):
    return f"{MEM_DIR}/user_{uid}_chat.json", f"{MEM_DIR}/user_{uid}_vector.json"
