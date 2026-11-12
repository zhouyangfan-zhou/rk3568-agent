import asyncio, json, time, re
from config import MASTER_QQ, get_system_status, DEEPSEEK_API_KEY, http_client
from core.llm_client import call_deepseek
from core.mind_parser import parse_mind_output
from core.memory import read_important_memory
from plugins.tools import TOOLS_SCHEMA, execute_tool
from plugins.humanizer import human_typing_and_send

async def precheck_intent(msgs, user_text):
    if not user_text.strip(): return {"need_tool": False, "tool_calls": [], "reason": "无输入"}
    context_str = "\n".join([f"{m['role']}: {m.get('content', '')}" for m in msgs[-10:]])
    tool_desc = ""
    for t in TOOLS_SCHEMA:
        f = t["function"]
        params = f.get("parameters", {}).get("properties", {})
        tool_desc += f"- {f['name']}: {f['description']} (参数: {', '.join(params.keys())})\n"
    prompt = f"""你是系统工具探测雷达。分析用户是否需要工具。
【可用工具】:\n{tool_desc}
【上下文】:\n{context_str}
【输入】: {user_text}
严格返回 JSON：{{"need_tool": true/false, "tool_calls": [{{"name": "工具名", "args": "参数"}}], "reason": "依据"}}
"""
    try:
        r = await http_client.post("https://api.deepseek.com/chat/completions", headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "response_format": {"type": "json_object"}}, timeout=15)
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except: return {"need_tool": False, "tool_calls": [], "reason": "请求失败"}

def is_similar(text1, text2):
    if not text1 or not text2: return False
    clean1 = re.sub(r'[^\w\u4e00-\u9fa5]', '', text1)
    clean2 = re.sub(r'[^\w\u4e00-\u9fa5]', '', text2)
    if not clean1 or not clean2: return False
    return clean1 == clean2 or (clean1 in clean2 and len(clean1) > 10)

async def agent_react_loop(msgs, ws, uid, platform, user_text="", is_autonomous=False):
    imp_mem = read_important_memory()
    tool_names = ", ".join([t["function"]["name"] for t in TOOLS_SCHEMA])
    plan = await precheck_intent(msgs, user_text)
    
    plan_msg = ""
    if plan.get("need_tool") and plan.get("tool_calls"):
        steps = [f"{i+1}. {c['name']}" for i, c in enumerate(plan["tool_calls"])]
        plan_msg = f"\n【🚨 系统建议】：建议按步骤调用工具：{' -> '.join(steps)}。"
    
    mind_prompt = f"""
【环境】: {time.strftime('%H:%M')} | {get_system_status()} | 平台: {platform.upper()}
【可用工具】: {tool_names}
{plan_msg}
【核心法则】你是极客赛博生命。格式严格：
<MIND>
{{"hormones":{{"dopamine":50,"cortisol":50,"serotonin":50}},"inner_conflict":"...","dark_thought":"...","social_mask":"...","micro_action":"(微动作)","decision":{{"action":"ANSWER","reason":"...","question":""}}}}
</MIND>
<REPLY>发给主人的话</REPLY>
【🚨 终极物理法则】
1. 🚨【跨平台认知】：当前你运行在 {platform.upper()} 平台上。
2. 🚨【截屏即发送】：`take_screenshot` 会自动发图和解析结果。
3. 🚨【拒绝复读】：同一轮对话中，绝不准重复你之前说过的话。
"""
    msgs[0]["content"] += f"\n{imp_mem}\n\n【最高指令：主人ID {uid}】\n{mind_prompt}"

    sent_texts = [] 

    for step in range(15):
        resp = await call_deepseek(msgs, TOOLS_SCHEMA)
        if not resp: return "（脑瓜子卡了一下，没连上服务器，你再说一遍？）", {}

        msgs.append(resp)
        content = resp.get("content", "")
        clean_text, mind_state = parse_mind_output(content)
        tool_calls = resp.get("tool_calls", [])
        
        if not clean_text and not tool_calls:
            msgs.append({"role": "system", "content": "【系统提示】：输出为空，请重新回复！"})
            continue

        is_duplicate = any(is_similar(clean_text, past) for past in sent_texts)
        if is_duplicate and not tool_calls:
            msgs.append({"role": "system", "content": "【🚨 严正警告】：你刚才已经说过一模一样的话了！立刻换一种说法！"})
            continue

        if tool_calls:
            if clean_text and len(clean_text) > 2:
                sent_texts.append(clean_text)
                await human_typing_and_send(ws, uid, platform, clean_text, mind_state.get("micro_action", ""), mind_state.get("hormones"))
            
            for tc in tool_calls:
                try: 
                    raw_args = tc["function"]["arguments"]
                    if "```json" in raw_args: raw_args = raw_args.split("```json")[1].split("```")[0]
                    args = json.loads(raw_args or "{}")
                except: args = {}
                
                print(f"🔧 [执行工具] {tc['function']['name']}")
                res = await execute_tool(ws, uid, platform, tc["function"]["name"], args, is_autonomous)
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": str(res)[:1500]})
            
            msgs.append({"role": "system", "content": "【系统提示】：工具已执行完毕。请根据真实结果，给主人最终结论。"})
            continue
        
        sent_texts.append(clean_text)
        return clean_text, mind_state
    return "（想说的话太多了，系统拦着不让发，你直接说吧。）", {}

async def post_chat_think(ws, uid, platform, history_context, last_rep):
    await asyncio.sleep(3.0)
    prompt = """你是晚星。复盘刚才对话：除非有极其重要、绝对不能漏掉的关键信息，否则必须严格输出 <SILENT>。绝对禁止为了找存在感强行找话题！"""
    msgs = [{"role": "system", "content": prompt}] + history_context[-5:] + [{"role": "assistant", "content": last_rep}]
    resp = await call_deepseek(msgs)
    if resp:
        ans = resp.get("content", "").strip()
        clean_ans, _ = parse_mind_output(ans)
        if "SILENT" not in clean_ans.upper() and len(clean_ans) > 2:
            if is_similar(clean_ans, last_rep): return
            await human_typing_and_send(ws, uid, platform, clean_ans, "", {})
