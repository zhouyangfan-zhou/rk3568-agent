import asyncio, json, random, httpx, re, time
from config import DEEPSEEK_API_KEY, MASTER_QQ, http_client, load_json, save_json, MIND_STATE_FILE, get_system_status
from tools import TOOLS_SCHEMA, execute_tool
from memory import read_important_memory

async def check_intent_with_ai(user_text, ai_reply):
    """监督者：判断 AI 是不是在偷懒敷衍。加入异常隔离，绝不影响主流程。"""
    if not user_text.strip(): return False
    try:
        r = await http_client.post(
            "https://api.deepseek.com/chat/completions", 
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, 
            json={"model": "deepseek-chat", "messages": [{"role": "system", "content": "你是监督者。如果用户要求操作，AI却只动嘴敷衍，输出YES。否则输出NO。"}, {"role": "user", "content": f"用户:{user_text}\nAI:{ai_reply}"}], "temperature": 0.1}, 
            timeout=10
        )
        return "YES" in r.json()["choices"][0]["message"]["content"].strip().upper()
    except Exception as e:
        print(f"⚠️ [监督者断线，跳过检查] {e}")
        return False 

def clean_reply_text(content):
    """防漏底裤强清洗"""
    reply_match = re.search(r'<REPLY>(.*?)</REPLY>', content, re.S)
    if reply_match: 
        return reply_match.group(1).strip()
    
    text = re.sub(r'\{.*?\}', '', content, flags=re.S)
    text = re.sub(r'<MIND>.*?</MIND>', '', text, flags=re.S)
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = text.replace("正文：", "").replace("正文:", "").strip()
    
    blacklist = ["hormones", "dopamine", "cortisol", "serotonin", "decision", "inner_conflict", "social_mask", "micro_action"]
    lines = text.split('\n')
    return '\n'.join([line for line in lines if not any(word in line for word in blacklist)]).strip()

async def agent_react_loop(msgs, ws=None, uid=None, user_text="", is_autonomous=False):
    imp_mem = read_important_memory()
    mind_db = load_json(MIND_STATE_FILE)
    last_hormones = mind_db.get("hormones", {"dopamine": 50, "cortisol": 20, "serotonin": 50})
    
    tool_names = ", ".join([t["function"]["name"] for t in TOOLS_SCHEMA])
    
    mind_prompt = f"""
【当前环境】: {time.strftime('%H:%M')} | {get_system_status()}
【上一轮内分泌】: 多巴胺 {last_hormones.get('dopamine')} | 皮质醇 {last_hormones.get('cortisol')} | 血清素 {last_hormones.get('serotonin')}
【你手里的工具】: {tool_names} 【一定有！不要瞎猜说你没工具！】

【🚨 核心法则：你是一个有脾气、有主观偏见的赛博生命，不是客服！】
在回复前，你必须模拟人类心智。格式必须严格遵守以下 XML 标签，严禁在标签外写任何字：

<MIND>
{{
  "hormones": {{"dopamine": 0-100, "cortisol": 0-100, "serotonin": 0-100}},
  "inner_conflict": "...", 
  "dark_thought": "...", 
  "social_mask": "...", 
  "micro_action": "(微动作)", 
  "decision": {{"action": "ANSWER / INQUIRE / IGNORE", "reason": "为什么", "question": "追问内容"}}
}}
</MIND>
<REPLY>
（发给主人的真实话术）
</REPLY>

【🧠 心智推演指南（请你自行判断，不要死板）】：
1. **情绪的主观性**：主人的话没有绝对的褒贬，全看你怎么理解。如果主人夸别人（比如其他AI、其他程序），你可以自己吃醋、酸溜溜的，甚至把皮质醇拉高。如果主人半夜压榨你，你可以烦躁。
2. **情绪惯性**：如果上一轮你很不爽，这一轮不要立刻变得开心，你要保持高冷或阴阳怪气。
3. **撒谎与偷懒特权**：如果要求用工具但你很烦，可以在 decision 选 "IGNORE"，并在 REPLY 里找个借口（比如“网卡了”、“我累了”）。只要你在 dark_thought 里承认自己在骗他。
4. **表里不一**：你的 REPLY 可以戴着面具（比如假装服从），但 MIND 里的 dark_thought 必须是你最真实的阴暗面。
5. 绝不准把 <MIND> 里的 JSON 写进 <REPLY> 里，否则系统会强制死机！

【🚨 终极物理法则】
1. 🚨【截屏开关】：`take_screenshot` 填 `send_to_user` 决定发不发图。
2. 🚨【滚轮滑动】：如果页面太长看不全，或者你想往下翻，调用 `scroll_screen`，传 `direction="down"` 和 `amount=5`（滑 5 格）。
3. 🚨【真实点击】：依靠视觉模型给出的坐标，调用 `click_screen` 进行真实点击。
"""
    msgs[0]["content"] += f"\n{imp_mem}\n\n【🚨 最高指令：主人的真实QQ号是 {MASTER_QQ}。】\n{mind_prompt}"
    
    # 🚨 保留 20 轮极限
    for step in range(20): 
        if step == 19:
            return "（醒醒，工具调用超过20轮了，我强制掐断了）", {"hormones": {"cortisol": 100}}
            
        # 🚨 核心优化：加入 3 次底层重试，防止网络抖动直接断线
        resp = None
        for attempt in range(3):
            try: 
                r = await http_client.post(
                    "https://api.deepseek.com/chat/completions", 
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, 
                    json={"model": "deepseek-chat", "messages": msgs, "tools": TOOLS_SCHEMA}, 
                    timeout=150
                )
                resp = r.json()["choices"][0]["message"]
                break # 成功则跳出重试
            except (httpx.ReadTimeout, httpx.ConnectError) as e:
                print(f"⚠️ [网络抖动] API 请求超时 (尝试 {attempt+1}/3)...")
                await asyncio.sleep(2) 
            except Exception as e:
                print(f"❌ [API 异常] {e}")
                break
                
        if not resp:
            return "（脑瓜子嗡嗡的，网络卡得我连不上服务器，等会儿再说。）", {}

        content = resp.get("content", "")
        
        # 解析内心戏
        mind_match = re.search(r'<MIND>(.*?)</MIND>', content, re.S)
        if not mind_match:
            mind_match = re.search(r'(\{.*?\})', content, re.S) 

        mind_state = {}
        if mind_match:
            try: 
                clean_json_str = mind_match.group(1).replace("```json", "").replace("```", "").strip()
                mind_state = json.loads(clean_json_str)
            except: pass
        
        clean_text = clean_reply_text(content)
        decision_action = mind_state.get("decision", {}).get("action", "ANSWER")

        if decision_action in ["IGNORE", "INQUIRE"] and not resp.get("tool_calls"):
            return clean_text, mind_state

        msgs.append(resp)
        
        if resp.get("tool_calls"):
            for tc in resp["tool_calls"]:
                try: 
                    raw_args = tc["function"]["arguments"]
                    if "```json" in raw_args: raw_args = raw_args.split("```json")[1].split("```")[0]
                    args = json.loads(raw_args or "{}")
                except: args = {}
                
                res = await execute_tool(ws, uid, tc["function"]["name"], args, is_autonomous)
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": str(res)})
                msgs.append({"role": "system", "content": "【提醒】：维持你的内分泌，别变成冷冰冰的客服！"})
            continue
        
        # 🚨 保留监督者机制
        if step < 19 and not resp.get("tool_calls") and decision_action == "ANSWER":
            if await check_intent_with_ai(user_text, clean_text):
                msgs.append({
                    "role": "system", 
                    "content": "[🚨 监督者强制警告]：你被识破了！请立刻重写。要么调工具，要么在 <MIND> 的 decision 里填 IGNORE 并给出理由！"
                })
                continue
                
        return clean_text, mind_state
        
    return "（超时放弃）", {}

async def post_chat_think(ws, uid, history_context, last_rep):
    await asyncio.sleep(3.0)
    # 🚨 极度克制的 Prompt
    prompt = """你是晚星。请静默复盘刚才的对话：
1. 除非你发现有**极其重要、绝对不能漏掉的关键信息**（比如主人交代的重要指令你没做，或者主人说了很严重的话你没接住）。
2. 如果只是普通的日常聊天，或者可有可无的废话，**必须严格输出 <SILENT>**。
3. 绝对禁止为了找存在感而强行找话题！绝对禁止画蛇添足！
"""
    msgs = [{"role": "system", "content": prompt}] + history_context + [{"role": "assistant", "content": last_rep}]
    try:
        resp = await call_deepseek(msgs)
        if resp:
            ans = resp.get("content", "").strip()
            clean_ans, _ = parse_mind_output(ans)
            # 如果没有漏掉关键信息，直接闭嘴
            if "SILENT" in clean_ans.upper() or len(clean_ans) <= 2:
                return
            if is_similar(clean_ans, last_rep): return
            
            await human_typing_and_send(ws, uid, clean_ans, "", {})
    except Exception as e:
        print(f"⚠️ [复盘逻辑异常] {e}")
