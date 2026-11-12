#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
晚星记忆工具（轻量版）
存储：memory.json（追加式）
检索：哈希词向量 + TF 权重 + 余弦相似度（零第三方依赖，纯标准库）
支持中文按字/双字切分，实现模糊匹配。
"""
import json, os, re, math, hashlib, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEM_FILE = os.path.join(BASE_DIR, "memory.json")

# ---------- 文本切分 ----------
def tokenize(text):
    """中文按单字 + 双字(bigram)切分；英文/数字按词切。"""
    text = text.lower()
    tokens = []
    # 英文 / 数字
    for w in re.findall(r"[a-z0-9]+", text):
        tokens.append(w)
    # 中文：单字 + 相邻双字
    for seg in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(list(seg))                       # 单字
        tokens.extend(seg[i:i+2] for i in range(len(seg)-1))  # 双字，增强模糊
    return tokens

def to_vec(text):
    """哈希词袋 -> {hash_bucket: tf}，桶固定 1024 维。"""
    vec = {}
    for t in tokenize(text):
        h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16) % 1024
        vec[h] = vec.get(h, 0) + 1
    # 子线性 tf
    for k in vec:
        vec[k] = 1 + math.log(vec[k])
    return vec

def cosine(v1, v2):
    if not v1 or not v2:
        return 0.0
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in v1)
    n1 = math.sqrt(sum(x * x for x in v1.values()))
    n2 = math.sqrt(sum(x * x for x in v2.values()))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)

# ---------- 存储 ----------
def _load():
    if not os.path.exists(MEM_FILE):
        return []
    try:
        with open(MEM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _dump(data):
    tmp = MEM_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MEM_FILE)

def save(text, tag="general"):
    data = _load()
    rec = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tag": tag,
        "text": text,
    }
    data.append(rec)
    _dump(data)
    return rec

def search(query, top_k=5, threshold=0.15):
    """模糊检索：返回相似度最高的若干条记忆。"""
    data = _load()
    if not data:
        return []
    qv = to_vec(query)
    scored = []
    for rec in data:
        score = cosine(qv, to_vec(rec["text"]))
        if score >= threshold:
            scored.append((score, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(s, 3), **r} for s, r in scored[:top_k]]

def load_recent(n=20):
    """回灌用：取最近 n 条。"""
    return _load()[-n:]

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(json.dumps(load_recent(5), ensure_ascii=False, indent=2))
    elif sys.argv[1] == "add":
        print(json.dumps(save(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "general"), ensure_ascii=False))
    elif sys.argv[1] == "search":
        print(json.dumps(search(sys.argv[2]), ensure_ascii=False, indent=2))
