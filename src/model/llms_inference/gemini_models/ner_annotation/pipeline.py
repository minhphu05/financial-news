import os
import json
import time
from typing import Set
from dotenv import load_dotenv
from google import genai
from model_runner import process_batch

load_dotenv(
    dotenv_path="/Users/kittnguyen/Documents/DS201_Finance/src/llms_inference/gemini_models/config/.env",
    override=True
)
# --- CẤU HÌNH ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Thay đổi model ở đây nếu cần
MODELS = [
    # "gemini-2.0-flash",
    # "gemini-2.5-pro",
    "gemini-2.5-flash",
    # "gemini-3-pro-preview"
]
usable_models = MODELS.copy()
BATCH_SIZE = 50  # Số câu mỗi lần gửi

def get_processed_ids(output_file_path: str) -> Set[int]:
    """Đọc file kết quả để lấy các ID đã làm xong (Resume capability)."""
    processed_ids = set()
    if not os.path.exists(output_file_path):
        return processed_ids

    print(f"📂 Đang tải dữ liệu đã xử lý từ: {output_file_path}")
    try:
        with open(output_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                    if 'id' in data:
                        processed_ids.add(int(data['id']))
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"⚠️ Lỗi đọc file output cũ: {e}")
    
    print(f"✅ Đã tìm thấy {len(processed_ids)} ID đã hoàn thành.")
    return processed_ids

def run_pipeline(input_json_file: str, output_jsonl_file: str, start_index: int = 0, end_index: int = None):
    """
    Chạy pipeline NER theo lô (Batch 20) trong khoảng [start_index, end_index).
    """

    # 1. Load Data
    try:
        with open(input_json_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        # Chuẩn hóa ID
        all_items = []
        for i, item in enumerate(raw_data):
            sentence = item.get("sentence", "").strip()
            if sentence:
                # Ưu tiên dùng ID có sẵn, nếu không thì dùng index của mảng
                item_id = item.get("id", i) 
                all_items.append({"id": int(item_id), "sentence": sentence})
        
        total_items = len(all_items)
        if end_index is None or end_index > total_items:
            end_index = total_items
            
        print(f"📊 Dữ liệu gốc: {total_items} câu.")
        print(f"🎯 Phạm vi xử lý yêu cầu: Index {start_index} -> {end_index}")

    except Exception as e:
        print(f"❌ Lỗi đọc file input: {e}")
        return

    # 2. Lọc phạm vi (Slicing)
    target_items = all_items[start_index:end_index]
    if not target_items:
        print("⚠️ Không có dữ liệu trong phạm vi yêu cầu.")
        return

    # 3. Resume Logic (Loại bỏ các ID đã có trong Output file)
    processed_ids = get_processed_ids(output_jsonl_file)
    
    # Chỉ giữ lại những item nằm trong target scope VÀ chưa được xử lý
    todo_items = [item for item in target_items if item["id"] not in processed_ids]

    print(f"📝 Số lượng câu thực tế cần chạy (đã trừ cái cũ): {len(todo_items)}")
    
    if not todo_items:
        print("🎉 Đã hoàn thành phạm vi này trước đó!")
        return

    # 4. Chia Batch
    batches = [todo_items[i:i + BATCH_SIZE] for i in range(0, len(todo_items), BATCH_SIZE)]
    print(f"📦 Tổng số Batch: {len(batches)} (Kích thước: {BATCH_SIZE})")
    print("-" * 50)

    # 5. Khởi tạo Client
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 6. Chạy Loop
    for i, batch in enumerate(batches):
        batch_num = i + 1
        start_id = batch[0]['id']
        end_id = batch[-1]['id']
        
        print(f"\n🚀 Processing Batch {batch_num}/{len(batches)} (IDs: {start_id} -> {end_id})")

        results = process_batch(client, batch, batch_num, MODELS[0])

        if results:
            # Ghi file
            success_count = 0
            with open(output_jsonl_file, "a", encoding="utf-8") as f:
                for res in results:
                    # Đảm bảo format chuẩn
                    if isinstance(res, dict):
                        json_line = json.dumps(res, ensure_ascii=False)
                        f.write(json_line + '\n')
                        
                        # Cập nhật ID đã xử lý (để nếu crash chạy lại sẽ biết)
                        if 'id' in res:
                            processed_ids.add(int(res['id']))
                        success_count += 1
            print(f"   💾 Đã lưu {success_count} dòng.")
        else:
            print(f"   ❌ Batch {batch_num} lỗi. DỪNG CHƯƠNG TRÌNH")
            return
        
        # Rate Limit Sleep
        print("   💤 Nghỉ 15s...")
        time.sleep(15)

    print("\n🏁 HOÀN THÀNH QUÁ TRÌNH XỬ LÝ.")