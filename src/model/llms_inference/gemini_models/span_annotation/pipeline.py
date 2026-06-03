import time
import random
from model_runner import process_context

def run_pipeline(contexts: list, filedir: str, start_index: int = 0, end_index: int = None):
    """
    Chạy pipeline NER (Gọi LLM) trên một phạm vi xác định của danh sách contexts.

    Args:
        contexts (list): Danh sách đầy đủ các đoạn văn bản cần phân tích.
        start_index (int): Chỉ mục bắt đầu (bao gồm) trong danh sách contexts gốc. Mặc định là 0.
        end_index (int): Chỉ mục kết thúc (không bao gồm) trong danh sách contexts gốc. 
                         Mặc định là None (chạy đến cuối danh sách).
                         
    Returns:
        None
    """
    # Validate input
    if not contexts:
        print("Context list is empty.")
        return

    if end_index is None:
        end_index = len(contexts)

    if start_index < 0 or start_index >= end_index or start_index >= len(contexts):
        print(f"Invalid range: start={start_index}, end={end_index}")
        return

    # Lấy lát cắt contexts cần xử lý
    contexts_to_process = contexts[start_index:end_index]
    total_to_process = len(contexts_to_process)

    print(f"Bắt đầu xử lý {total_to_process} contexts.")
    print(f"   Phạm vi gốc: Từ index {start_index} đến {end_index - 1}.")
    print("---")

    for relative_idx, context in enumerate(contexts_to_process):
        # *** Đây là logic quan trọng: Tính toán Chỉ mục Gốc ***
        original_idx = start_index + relative_idx 
        
        print(f"Xử lý context thứ {original_idx} / {end_index - 1} (Relative index: {relative_idx} / {total_to_process - 1})")
        
        # Gọi hàm xử lý đã được định nghĩa
        success = process_context(context, original_idx, filedir)
        
        if not success:
            print(f"Không thể xử lý context thứ {original_idx} với tất cả các model khả dụng. Dừng chương trình.")
            # Có thể thêm logic lưu lại chỉ mục bị lỗi để chạy lại sau
            break 
        
        # Tạm dừng giữa các lần gọi để tránh bị rate limit
        time.sleep(random.uniform(1, 3)) 

    print("---")
    print("Hoàn thành xử lý phạm vi đã chọn.")