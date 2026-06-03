import json
import re

def extract_json(response):
    """
    Trích JSON từ response của mô hình (Gemini / GPT ...),
    tự động tìm JSON dù mô hình trả trong code block hoặc trả JSON thuần.
    """

    # 1) Lấy toàn bộ text của response
    #    (tự động tương thích Gemini, GPT, Claude)
    if hasattr(response, "text") and response.text:
        text = response.text
    else:
        try:
            text = response.candidates[0].content[0].text
        except:
            text = str(response)

    # 2) Thử tìm code block dạng ```json ... ```
    match = re.search(r"```json(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass  # Nếu code block lỗi → thử phương án 2

    # 3) Nếu không có code block → tìm JSON thuần bằng regex cân ngoặc {}
    #    Lấy đoạn JSON dài nhất (thường là đoạn đầu tiên)
    json_candidates = re.findall(r"\{.*?\}", text, re.DOTALL)
    if json_candidates:
        for jc in json_candidates:
            try:
                return json.loads(jc)
            except json.JSONDecodeError:
                continue  # thử đoạn tiếp theo

    # 4) Nếu mô hình trả về dạng list JSON: [ {...}, {...} ]
    list_candidates = re.findall(r"\[.*?\]", text, re.DOTALL)
    if list_candidates:
        for lc in list_candidates:
            try:
                return json.loads(lc)
            except json.JSONDecodeError:
                continue

    print("Không tìm thấy JSON hợp lệ trong response.")
    return None