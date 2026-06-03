import time
from google.genai import types
# Modules
from prompts import build_ner_prompt
from parser import extract_json


def process_batch(client, batch_data, batch_idx, model_name):
    """Gửi batch và retry nếu lỗi."""
    system_instruction, user_prompt = build_ner_prompt(batch_data)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"   ➤ Gửi Batch {batch_idx} (Lần {attempt+1}) tới {model_name}...")
            
            response = client.models.generate_content(
                model=model_name,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1
                ),
                contents=user_prompt
            )
            
            data = extract_json(response)
            
            # Validate dữ liệu
            if data and isinstance(data, list) and len(data) > 0:
                if 'id' in data[0] or (isinstance(data[0], list) and len(data[0]) >= 3):
                    print(f"   ✅ Batch {batch_idx} thành công: {len(data)} items.")
                    return data
            
            print(f"   ⚠️ Batch {batch_idx}: Response không hợp lệ. Thử lại...")
            
        except Exception as e:
            wait = (attempt + 1) * 10
            print(f"   🔥 Lỗi API (Lần {attempt+1}): {e}. Chờ {wait}s...")
            time.sleep(wait)
            
    print(f"   ❌ Batch {batch_idx} thất bại sau {max_retries} lần thử.")
    return None