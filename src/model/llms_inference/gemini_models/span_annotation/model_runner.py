import os
import json
import time
import random
from dotenv import load_dotenv
from google import genai
from google.genai import types
# Modules
from prompts import build_en_prompt
from parser import extract_json

load_dotenv(
    dotenv_path="/Users/kittnguyen/Documents/DS201_Finance/src/llms_inference/gemini_models/config/.env",
    override=True
)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
models = [
    # "gemini-2.0-flash",
    # "gemini-2.5-pro",
    "gemini-2.5-flash",
    # "gemini-3-pro-preview"
]
usable_models = models.copy()  # Ban đầu tất cả đều có thể dùng

def process_context(context, idx, filedir):
    global usable_models
    if not usable_models:
        print("Hết model khả dụng, dừng xử lý.")
        return False
    
    for model_name in usable_models[:]:  # Duyệt bản sao để có thể xóa model khi cần
        print(f"Thử model {model_name} cho context thứ {idx}")
        
        #gemini = genai.GenerativeModel(model_name)
        client = genai.Client(api_key=GEMINI_API_KEY)
        system_instruction, user_prompt = build_en_prompt(context)
        
        # prompt = [
        #     {"role": "system", "content": system_instruction},
        #     {"role": "user", "content": user_prompt}
        # ]
                
        success = False
        attempt = 0
        max_attempts_per_model = 5
        while not success and attempt < max_attempts_per_model:
            try:
                #response = gemini.models.generate_text(
                # response = gemini.generate_text(
                #     #model="gemini-2.5-flash",
                #     prompt=prompt,
                #     temperature=0.1  # deterministic output
                # )
                
                response = client.models.generate_content(
                    model=model_name,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction
                        #thinking_config=types.ThinkingConfig(thinking_level="low")
                    ),
                    contents=user_prompt
                )
                
                data = extract_json(response)
                
                if data:
                    # Tạo folder nếu chưa tồn tại
                    os.makedirs(filedir, exist_ok=True)
                    filename = os.path.join(filedir, f"{idx}.json")
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    print(f"Đã lưu kết quả vào file {filename} với model {model_name}")
                else:
                    print("Không có dữ liệu để lưu.")
                success = True
                return True
            except Exception as e:
                attempt += 1
                wait = min(60, 2 ** attempt + random.uniform(0, 3))
                print(f"Model {model_name} bị lỗi, chờ {wait:.1f}s rồi thử lại...")
                print(f'Error: {e}\n')
                time.sleep(wait)
        
        if not success:
            # Loại model này khỏi usable_models vì bị lỗi liên tục
            print(f"Model {model_name} không thành công sau {max_attempts_per_model} lần thử, loại khỏi danh sách dùng được.")
            usable_models.remove(model_name)
    
    print(f"Không model nào xử lý được context thứ {idx}, dừng lại.")
    return False