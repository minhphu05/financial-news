import re
import json

def extract_json(response):
    """Trích xuất JSON từ response (hỗ trợ code block và json thuần)."""
    if hasattr(response, "text") and response.text:
        text = response.text
    else:
        try:
            text = response.candidates[0].content[0].text
        except:
            text = str(response)

    # 1. Tìm Code Block JSON
    match = re.search(r"```json(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except: pass

    # 2. Tìm List JSON [...]
    list_candidates = re.findall(r"\[.*\]", text, re.DOTALL)
    if list_candidates:
        longest = max(list_candidates, key=len)
        try:
            return json.loads(longest)
        except: pass

    # 3. Tìm Object JSON {...} (Fallback nếu model trả về 1 object thay vì list)
    dict_candidates = re.findall(r"\{.*?\}", text, re.DOTALL)
    if dict_candidates:
        try:
            return [json.loads(dict_candidates[0])] # Wrap vào list
        except: pass

    return None