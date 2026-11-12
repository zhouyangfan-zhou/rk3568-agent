import numpy as np, time
from config import SILICONFLOW_API_KEY, DEEPSEEK_API_KEY, IMPORTANT_FILE, http_client, load_json, save_json, get_user_files, get_group_file

async def get_embedding(text):
    try:
        r = await http_client.post("https://api.siliconflow.cn/v1/embeddings", headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}"}, json={"model": "BAAI/bge-m3", "input": text}, timeout=15)
        return r.json()["data"][0]["embedding"]
    except: return None

def read_important_memory():
    db = load_json(IMPORTANT_FILE)
    return "\n【💎 核心重要记忆】：\n" + "\n".join(db.get("memories", []))

def write_important_memory(content):
    db = load_json(IMPORTANT_FILE)
    if "memories" not in db: db["memories"] = []
    db["memories"].append(content)
    save_json(IMPORTANT_FILE, db)

def read_recent_chat(uid, limit=10):
    chat_file, _ = get_user_files(uid)
    db = load_json(chat_file)
    history = []
    for c in db.get("history", [])[-limit:]:
        history.append({"role": "user", "content": c["user"]})
        history.append({"role": "assistant", "content": c["ai"]})
    return history

async def auto_summarize_and_store(uid, dialog_text):
    chat_file, vector_file = get_user_files(uid)
    try:
        r = await http_client.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, json={"model": "deepseek-chat", "messages": [{"role": "system", "content": "提取对话重点，精简总结。没有则输出'无'。"}, {"role": "user", "content": dialog_text}], "temperature": 0.3}, timeout=30)
        summary = r.json()["choices"][0]["message"]["content"].strip()
        if summary == "无" or len(summary) < 2: return
        vector = await get_embedding(summary)
        if not vector: return
        mem_db = load_json(vector_file)
        if "list" not in mem_db: mem_db["list"] = []
        mem_db["list"].append({"text": summary, "vector": vector, "time": time.time()})
        if len(mem_db["list"]) > 300: mem_db["list"] = mem_db["list"][-300:] 
        save_json(vector_file, mem_db)
    except: pass

async def search_memory(uid, query, top_k=3):
    query_vec = await get_embedding(query)
    if not query_vec: return ""
    chat_file, vector_file = get_user_files(uid)
    mem_db = load_json(vector_file)
    if "list" not in mem_db: return ""
    scored = []
    for item in mem_db["list"]:
        if not isinstance(item, dict) or "vector" not in item: continue
        a, b = np.array(query_vec), np.array(item["vector"])
        score = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        if score > 0.4: scored.append((score, item["text"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    return "\n【🧠 长期对话记忆】：\n" + "\n".join([t for s, t in scored[:top_k]]) if scored else ""

def save_full_chat(uid, user_text, ai_reply):
    chat_file, _ = get_user_files(uid)
    db = load_json(chat_file)
    if "history" not in db: db["history"] = []
    db["history"].append({"user": user_text, "ai": ai_reply})
    save_json(chat_file, db)

def save_group_chat(gid, user_text, ai_reply=""):
    g_file = get_group_file(gid)
    db = load_json(g_file)
    if "history" not in db: db["history"] = []
    db["history"].append({"time": time.strftime("%H:%M"), "user": user_text, "ai": ai_reply})
    if len(db["history"]) > 100: db["history"] = db["history"][-100:]
    save_json(g_file, db)
