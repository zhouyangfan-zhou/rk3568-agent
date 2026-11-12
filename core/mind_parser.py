import re, json

def parse_mind_output(content):
    mind_state = {}
    mind_match = re.search(r'(\{.*\})', content, re.S)
    if mind_match:
        try: 
            clean_json_str = mind_match.group(1).replace("```json", "").replace("```", "").strip()
            start = clean_json_str.find('{')
            end = clean_json_str.rfind('}') + 1
            if start != -1 and end != 0: mind_state = json.loads(clean_json_str[start:end])
        except: pass

    if "<REPLY>" in content:
        clean_text = content.split("<REPLY>")[-1].replace("</REPLY>", "").strip()
    else:
        clean_text = re.sub(r'<MIND>.*', '', content, flags=re.S)
        clean_text = re.sub(r'\{.*?\}', '', clean_text, flags=re.S)
        
    clean_text = re.sub(r'```.*?```', '', clean_text, flags=re.S)
    clean_text = re.sub(r'<tool_call>.*?</tool_call>', '', clean_text, flags=re.S)
    clean_text = re.sub(r'[\(（\[【].*?[\)）\]】]', '', clean_text)
    clean_text = clean_text.replace("正文：", "").replace("正文:", "").strip()
    
    if any(word in clean_text for word in ["规划师", "监督者", "系统强制", "被识破"]): clean_text = ""
    blacklist = ["hormones", "dopamine", "cortisol", "decision", "inner_conflict", "tool_call"]
    clean_text = '\n'.join([line for line in clean_text.split('\n') if not any(word in line for word in blacklist)]).strip()
    
    if clean_text and not re.search(r'[\w\u4e00-\u9fa5]', clean_text): clean_text = ""
    return clean_text, mind_state
