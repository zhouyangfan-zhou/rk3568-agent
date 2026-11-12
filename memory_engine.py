#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
晚星的长期记忆引擎
- 把对话沉淀进 memory_store.jsonl（只增不删）
- recall(query): 关键词 + 简单相似度检索相关旧记忆
- 支持 CLI: python memory_engine.py recall "关键词"
"""
import os, json, sys, time, re, math
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(BASE_DIR, "memory_store.jsonl")

def _tokenize(text):
    text = str(text).lower()
    # 中文按字 + 英文/数字按词，粗粒度但够用
    cn = re.findall(r'[\u4e00-\u9fff]', text)
    en = re.findall(r'[a-z0-9_]+', text)
    return cn + en

def _vec(tokens):
    return Counter(tokens)

def _cosine(a, b):
    if not a or not b: return 0.0
    common = set(a) & set(b)
    num = sum(a[t]*b[t] for t in common)
    da = math.sqrt(sum(v*v for v in a.values()))
    db = math.sqrt(sum(v*v for v in b.values()))
    return num/(da*db) if da and db else 0.0

def add_memory(role, content, uid="", ts=None):
    """追加一条记忆到持久库"""
    rec = {"ts": ts or time.time(), "uid": str(uid), "role": role, "content": str(content)}
    with open(STORE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

def load_all():
    if not os.path.exists(STORE): return []
    out = []
    with open(STORE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: out.append(json.loads(line))
            except: pass
    return out

def recall(query, top_k=5, min_score=0.06):
    """检索与 query 最相关的旧记忆"""
    qv = _vec(_tokenize(query))
    scored = []
    for rec in load_all():
        s = _cosine(qv, _vec(_tokenize(rec.get("content",""))))
        if s >= min_score: scored.append((s, rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]

def recall_text(query, top_k=5):
    """给主程序用的：返回一段可直接塞进 system 的记忆文本"""
    hits = recall(query, top_k=top_k)
    if not hits: return ""
    lines = ["【相关长期记忆】"]
    for r in hits:
        who = "主人" if r.get("role")=="user" else "我"
        lines.append(f"- {who}: {r.get('content','')[:120]}")
    return "\n".join(lines)

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "recall":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        hits = recall(q)
        if not hits:
            print("（没有相关记忆）")
        else:
            for r in hits:
                who = "主人" if r.get("role")=="user" else "我"
                print(f"[{who}] {r.get('content','')[:150]}")
    elif len(sys.argv) >= 2 and sys.argv[1] == "count":
        print(len(load_all()))
    else:
        print("用法: python memory_engine.py recall \"关键词\" | count")
