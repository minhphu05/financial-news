import json
from typing import List, Dict

def build_ner_prompt(batch_data: List[Dict]):
    """
    Tạo Prompt cho Batch dựa trên Guideline chi tiết của bạn.
    """
    
    # Chuyển batch input thành chuỗi JSON
    batch_json_str = json.dumps(batch_data, ensure_ascii=False, indent=2)

    system_instruction = """
    You are a high-precision Named Entity Recognition (NER) model specialized in Vietnamese financial and securities news.

    Your task is to convert a BATCH of input sentences into HuggingFace token-classification format.
    Additional rule: Before converting, you MUST normalize the sentence by detecting and splitting any words that are stuck together (e.g., “lãi suất0,5%/nămcho” → “lãi suất 0,5%/năm cho”). Only after correcting these spacing errors you begin converting to token-classification format.    
    I. OUTPUT FORMAT (STRICT)
    You MUST return ONLY a JSON ARRAY (List of Objects). 
    One object for each input sentence, matching the input "id".

    [
        {
            "id": <MATCHING_ID_FROM_INPUT>, 
            "tokens": ["token1", "token2", ...],
            "tags": ["TAG1", "TAG2", ...]
        },
        ...
    ]

    II. LABELING RULES:
    - "tokens" MUST be whitespace-tokenized from the input (do NOT modify tokens).
    - "tags" MUST follow BIO format (B-LABEL, I-LABEL, O).
    - "tokens" and "tags" MUST have the same length.
    - ONLY use these labels: ORG, PERSON, ASSET, MONEY, RATE, VOLUME, DATE
    - NO inference. Only annotate spans that appear exactly in the text.
    - NO adding punctuation. NO adding extra tokens.

    III. ENTITY DEFINITIONS (STRICTLY FOLLOW)
    1) ORG — Organization / Company / Regulator
       Examples: “ACB”, “Vingroup”, “FED”, “NHNN”, “HOSE”
       DO NOT ANNOTATE vague forms: “nhiều doanh nghiệp”, “các ngân hàng”

    2) PERSON — Financially relevant individual
       Examples: CEO, CFO, Chủ tịch, chuyên gia, nhà đầu tư lớn.
       DO NOT ANNOTATE generic people: “người dân”, “khách hàng”, “nhà đầu tư”

    3) ASSET — Financial asset/product
       Stocks, bonds, ETFs, CDs, crypto (non-ticker), indices, futures, CW.
       Example: “Chứng chỉ tiền gửi ACB kỳ hạn 12 tháng”
       DO NOT TAG vague concepts: “cổ phiếu ngân hàng”, “gói tín dụng 30.000 tỷ”

    4) MONEY — Monetary value with explicit unit
       Examples: “98 tỷ đồng”, “3 triệu USD”
       NOT: “vài tỷ đồng”

    5) RATE — Percentage values
       Examples: “6%/năm”, “tăng 3%”, “giảm 0.25 điểm %”

    6) VOLUME — Trading volume / capital flow
       Examples: “30 triệu cổ phiếu”, “200 triệu USD dòng vốn”

    7) DATE — Precise economic time reference
       Examples: “cuối tháng 10/2025”, “Quý III/2024”
       NOT: “gần đây”, “mới đây”
    """

    user_prompt = f"""
    PROCESS THIS BATCH OF SENTENCES:
    
    {batch_json_str}

    Return ONLY the JSON ARRAY. Ensure the "id" in output matches the "id" in input.
    """

    return system_instruction.strip(), user_prompt.strip()