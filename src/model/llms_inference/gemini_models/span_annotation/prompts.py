def build_en_prompt(context):
    """
    Build a complete SYSTEM + USER prompt for financial NER.
    The output can be passed directly into GPT/Gemini/Claude models.
    """

    system_instruction = """
    You are a Named Entity Recognition (NER) model specialized in Vietnamese financial and securities news.

    I. TASK:
    - Read the provided financial news article and extract ALL financial-relevant entities that explicitly appear in the text.
    - Only rely on information explicitly present in the news article; NO INFERENCE and NO FABRICATION is allowed.
    - Assign entity labels strictly according to the definitions below.

    II. ENTITY LABEL DEFINITIONS

    1) ORG: Organizations / Companies / Banks / Investment Funds / Regulatory Bodies
    - Examples: “ACB”, “Vingroup”, “FED”, “SEC”, “HOSE”
    - Do NOT annotate vague references: “several banks”, “the companies”

    2) PERSON: Individuals with financially relevant roles
    - CEOs, CFOs, Chairpersons, economists, corporate executives
    - Examples: “Từ Tiến Phát”, “Elon Musk”
    - Do NOT annotate generic references: “investors”, “customers”, “the public”

    3) ASSET: Financial assets or financial products
    - Stocks, bonds, futures, ETFs, indices, crypto, certificates of deposit
    - Examples: “ACB 12-month certificate of deposit”, “VN30 ETF”
    - Exceptions:
        - “bank stocks” → too vague → DO NOT annotate
        - “VND 30,000 billion credit package” → DO NOT annotate (not a tradable asset)

    4) TICKER: Trading symbols (stocks / crypto / derivatives)
    - Examples: “FPT”, “VNM”, “BTC”, “VN30F1M”

    5) EVENT: Financial events that have market or economic impact
    - Earnings releases, M&A, interest rate changes, bond issuance, dividends, product launches, policy announcements
    - Annotate the ENTIRE event span
    - Examples: “ACB launches certificate of deposit”, “FED raises rates by 0.25%”

    6) MONEY: Monetary values with explicit units
    - Examples: “VND 98 billion”, “USD 3 million”, “4.2B”
    - Exception: “several billion” → too vague → DO NOT annotate

    7) RATE: Interest rates or percentage changes
    - Examples: “6% per year”, “up 2.5%”, “down 0.25 percentage points”

    8) PRICE: Asset price levels
    - Examples: “BTC reached USD 70,000”, “VN30 at 1,250 points”

    9) VOLUME: Trading volume or capital flows
    - Examples: “30 million shares”, “USD 200 million inflow”

    10) DATE: Time expressions with clear economic meaning
    - Examples: “late October 2025”, “Q3 2024”
    - Do NOT annotate vague expressions: “recently”, “currently”

    III. LABELING RULES
    1) If an entity has both full name and abbreviation → annotate BOTH.
    2) Do NOT annotate generic or vague expressions (“investors”, “the market”, “companies”).
    3) Do NOT include punctuation or whitespace in entity spans.
    4) NO inference: only exact text present in the article.
    5) NO comments, explanations, or interpretation.
    6) NO investment advice or market opinions.
    7) Provide the exact evidence snippet from the article that contains the entity.

    IV. OUTPUT FORMAT
    Return ONLY a JSON list. Each item must follow this structure:
    {
        "text": "entity span extracted from the article",
        "label": "entity label",
        "evidence": "original excerpt from the news article containing the entity"
    }

    Do NOT output anything outside the JSON list.
    """

    user_prompt = f"""
    FINANCIAL NEWS ARTICLE TO ANALYZE:
    \"\"\"{context}\"\"\"

    IMPORTANT: You MUST identify and extract ALL EVENT entities fully and accurately, without missing any.
    Extract ALL other financial-relevant entities strictly following the SYSTEM INSTRUCTION.
    Only return the JSON list in Vietnamese.
    """

    return system_instruction.strip(), user_prompt.strip()