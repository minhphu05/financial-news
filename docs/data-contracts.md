# Data Contracts

<!-- BEGIN GENERATED OBSERVED DATA -->

## 1. Data Sources Currently Available

Observed by the standard-library profiler at `2026-09-20T06:49:44+00:00`. This section describes files, **not** a canonical Silver schema. The scanner visited `10,281` files under `data/` (683,920,819 bytes).

| Dataset/path pattern | Format | Files | Records | Source / purpose |
|---|---|---:|---:|---|
| `data/.DS_Store` | macos_metadata | 1 | 0 | System metadata; not a dataset |
| `data/eval/README.md` | markdown | 1 | 0 | Evaluation documentation |
| `data/eval/rag_eval.jsonl` | jsonl | 1 | 35 | RAG evaluation questions |
| `data/labeled/.DS_Store` | macos_metadata | 1 | 0 | System metadata; not a dataset |
| `data/labeled/ner/raw/output_ner.jsonl` | jsonl | 1 | 59,175 | NER/span research data |
| `data/labeled/ner/split/dev_raw.jsonl` | jsonl | 1 | 7,890 | NER/span research data |
| `data/labeled/ner/split/note.txt` | text | 1 | 0 | NER/span research data |
| `data/labeled/ner/split/test_raw.jsonl` | jsonl | 1 | 7,852 | NER/span research data |
| `data/labeled/ner/split/train_raw.jsonl` | jsonl | 1 | 36,750 | NER/span research data |
| `data/labeled/ner/syllables/dev_vifinner.jsonl` | jsonl | 1 | 7,890 | NER/span research data |
| `data/labeled/ner/syllables/final_dev_vifinner.jsonl` | jsonl | 1 | 7,890 | NER/span research data |
| `data/labeled/ner/syllables/final_test_vifinner.jsonl` | jsonl | 1 | 7,852 | NER/span research data |
| `data/labeled/ner/syllables/final_train_vifinner.jsonl` | jsonl | 1 | 36,750 | NER/span research data |
| `data/labeled/ner/syllables/test_vifinner.jsonl` | jsonl | 1 | 7,852 | NER/span research data |
| `data/labeled/ner/syllables/train_vifinner.jsonl` | jsonl | 1 | 36,750 | NER/span research data |
| `data/labeled/span/*.json` | json | 10,247 | 586,290 | NER/span research data |
| `data/labeled/span/.DS_Store` | macos_metadata | 1 | 0 | System metadata; not a dataset |
| `data/labeled/span_tags/0_PERSON.json` | json | 1 | 21,872 | NER/span research data |
| `data/labeled/span_tags/1_ASSET.json` | json | 1 | 30,297 | NER/span research data |
| `data/labeled/span_tags/2_ORG.json` | json | 1 | 180,569 | NER/span research data |
| `data/labeled/span_tags/3_EVENT.json` | json | 1 | 85,521 | NER/span research data |
| `data/labeled/span_tags/3_EVENT_clean.json` | json | 1 | 62,391 | NER/span research data |
| `data/labeled/span_tags/3_EVENT_unique.json` | json | 1 | 62,391 | NER/span research data |
| `data/labeled/span_tags/4_MONEY.json` | json | 1 | 61,587 | NER/span research data |
| `data/labeled/span_tags/5_DATE.json` | json | 1 | 86,523 | NER/span research data |
| `data/labeled/span_tags/6_RATE.json` | json | 1 | 74,106 | NER/span research data |
| `data/labeled/span_tags/7_TICKER.json` | json | 1 | 28,418 | NER/span research data |
| `data/labeled/span_tags/8_VOLUME.json` | json | 1 | 12,297 | NER/span research data |
| `data/labeled/span_tags/9_PRICE.json` | json | 1 | 5,027 | NER/span research data |
| `data/raw/.DS_Store` | macos_metadata | 1 | 0 | System metadata; not a dataset |
| `data/raw/cafeF_news.json` | json | 1 | 11,242 | CafeF article export |
| `data/raw/cafef_news_raw.json` | json | 1 | 11,242 | CafeF article export |
| `data/raw/cafef_news_raw_final.json` | json | 1 | 15,457 | CafeF article export |
| `data/raw/news_titles.jsonl` | jsonl | 1 | 11,242 | CafeF article-title derivative |
| `data/raw/vn30.xlsx` | xlsx | 1 | 30 | VN30 ticker/keyword reference workbook |

The URL host is inferred from the observed `link` values. It is not a publisher field stored in the raw JSON. Research and evaluation datasets are separate from article ingestion.

## 2. Directory and File Layout

```text
data/
├── raw/                 JSON article snapshots, title JSONL, VN30 XLSX
├── labeled/
│   ├── ner/             JSONL raw/split/syllable annotation data
│   ├── span/            many JSON arrays of labeled spans
│   └── span_tags/       label-specific JSON arrays
└── eval/                RAG evaluation JSONL and README
```

Observed format counts: `json` 10,262, `jsonl` 12, `macos_metadata` 4, `markdown` 1, `text` 1, `xlsx` 1. Text files were decoded as UTF-8 (BOM recorded where present); XLSX is OOXML ZIP/XML. `.DS_Store` files are binary system metadata, not datasets.

## 3. Observed Raw / Source Schema

The tables below are inferred from every parseable record in each dataset. `[]` denotes array items; item statistics use the observed item population rather than the record population. `Nullable` means a null or missing value was observed; it is **not** a proposed requirement.

### `data/eval/rag_eval.jsonl`

Records: **35**; file container: `line_records`; record root types: `{"object": 35}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `category` | `string` | No | interest_rate | present 35; missing 0.0%; length 2–15; distinct 14; values commodity, corporate_news, dividends, earnings, fx, interest_rate, ipo, macro, market_index, market_overview, policy, research, risk, sector_outlook |
| `difficulty` | `string` | No | easy | present 35; missing 0.0%; length 4–6; distinct 3; values easy, hard, medium |
| `expected_keywords` | `array` | No | ["lãi suất", "huy động"] | present 35; missing 0.0%; array length 1–3 |
| `expected_keywords[]` | `string` | No | lãi suất | present 93; length 2–20; distinct 88 |
| `expected_tickers` | `array` | No | ["ACB", "VCB", "BID", "CTG", "TCB", "VPB", "MBB", "STB"] | present 35; missing 0.0%; array length 0–8 |
| `expected_tickers[]` | `string` | No | ACB | present 40; length 3–3; distinct 33 |
| `id` | `string` | No | vif-001 | present 35; missing 0.0%; length 7–7; distinct 35 |
| `question` | `string` | No | Lãi suất huy động tiền gửi tại các ngân hàng lớn gần đây có xu hướng gì? | present 35; missing 0.0%; length 37–72; distinct 35 |

### `data/labeled/ner/raw/output_ner.jsonl`

Records: **59,175**; file container: `line_records`; record root types: `{"object": 59175}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `<empty field name>` | `array` | Yes | ["O", "O", "O", "B-ORG", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "B-ORG", "O", "O", "O", "… | present 1; missing 99.998%; array length 33–33 |
| `[]` | `string` | No | O | present 33; length 1–7; distinct 4; values B-MONEY, B-ORG, I-MONEY, O |
| `id` | `integer` | No | 0 | present 59,175; missing 0.0%; range 0–62390; distinct ≥20,000 |
| `sentence` | `string` | Yes | Sự xuất hiện của Lotusmiles Pay, sản phẩm hợp tác giữa ACB, Vietnam Airlines và Visa, cho phép người… | present 341; missing 99.424%; length 27–673; distinct 341 |
| `tags` | `array` | Yes | ["O", "O", "O", "B-ORG", "O", "O", "B-ASSET", "I-ASSET", "I-ASSET", "I-ASSET", "I-ASSET", "O", "O", … | present 59,173; missing 0.003%; array length 2–214 |
| `tags[]` | `string` | No | O | present 1,969,292; length 1–13; distinct 27 |
| `tokens` | `array` | Yes | ["Vì", "vậy,", "khi", "ACB", "ra", "mắt", "Chứng", "chỉ", "tiền", "gửi", "(CCTG)", "với", "lợi", "su… | present 59,174; missing 0.002%; array length 2–239 |
| `tokens[]` | `string` | No | Vì | present 1,980,666; blank string 7; length 0–109; distinct ≥20,000 |

### `data/labeled/ner/split/dev_raw.jsonl`

Records: **7,890**; file container: `line_records`; record root types: `{"object": 7890}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `tags` | `array` | No | ["O", "O", "B-DATE", "I-DATE", "O", "B-ORG", "I-ORG", "O", "O", "O", "O", "O", "O", "O", "O", "O", "… | present 7,890; missing 0.0%; array length 2–95 |
| `tags[]` | `string` | No | O | present 232,898; length 1–8; distinct 15; values B-ASSET, B-DATE, B-MONEY, B-ORG, B-PERSON, B-RATE, B-VOLUME, I-ASSET, I-DATE, I-MONEY, I-ORG, I-PERSON, I-RATE, I-VOLUME, O |
| `tokens` | `array` | No | ["Dự", "kiến", "năm", "2024", ",", "Hải", "Phòng", "tiếp", "tục", "khởi", "công", "dự", "án", "nhà",… | present 7,890; missing 0.0%; array length 2–95 |
| `tokens[]` | `string` | No | Dự | present 232,898; length 1–50; distinct 13,847 |

### `data/labeled/ner/split/test_raw.jsonl`

Records: **7,852**; file container: `line_records`; record root types: `{"object": 7852}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `tags` | `array` | No | ["O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "B-O… | present 7,852; missing 0.0%; array length 2–114 |
| `tags[]` | `string` | No | O | present 233,015; length 1–8; distinct 15; values B-ASSET, B-DATE, B-MONEY, B-ORG, B-PERSON, B-RATE, B-VOLUME, I-ASSET, I-DATE, I-MONEY, I-ORG, I-PERSON, I-RATE, I-VOLUME, O |
| `tokens` | `array` | No | ["Đồng", "thời,", "tập", "đoàn", "cũng", "ghi", "nhận", "các", "khoản", "đầu", "tư", "góp", "vốn", "… | present 7,852; missing 0.0%; array length 2–114 |
| `tokens[]` | `string` | No | Đồng | present 233,015; blank string 2; length 0–59; distinct 13,722 |

### `data/labeled/ner/split/train_raw.jsonl`

Records: **36,750**; file container: `line_records`; record root types: `{"object": 36750}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `tags` | `array` | No | ["O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "B-ORG", "I-ORG", "I-ORG", "I-ORG", "I-ORG", "B-O… | present 36,750; missing 0.0%; array length 2–118 |
| `tags[]` | `string` | No | O | present 1,090,695; length 1–13; distinct 17; values       B-MONEY,       O, B-ASSET, B-DATE, B-MONEY, B-ORG, B-PERSON, B-RATE, B-VOLUME, I-ASSET, I-DATE, I-MONEY, I-ORG, I-PERSON, I-RATE, I-VOLUME, O |
| `tokens` | `array` | No | ["Sự", "hợp", "tác", "được", "đồng", "hành", "và", "hỗ", "trợ", "bởi", "Cục", "Phát", "triển", "doan… | present 36,750; missing 0.0%; array length 2–118 |
| `tokens[]` | `string` | No | Sự | present 1,090,695; blank string 2; length 0–109; distinct ≥20,000 |

### `data/labeled/ner/syllables/dev_vifinner.jsonl`

Records: **7,890**; file container: `line_records`; record root types: `{"object": 7890}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `tags` | `array` | No | ["O", "O", "B-DATE", "I-DATE", "O", "B-ORG", "I-ORG", "O", "O", "O", "O", "O", "O", "O", "O", "O", "… | present 7,890; missing 0.0%; array length 3–100 |
| `tags[]` | `string` | No | O | present 237,579; length 1–8; distinct 15; values B-ASSET, B-DATE, B-MONEY, B-ORG, B-PERSON, B-RATE, B-VOLUME, I-ASSET, I-DATE, I-MONEY, I-ORG, I-PERSON, I-RATE, I-VOLUME, O |
| `tokens` | `array` | No | ["Dự", "kiến", "năm", "2024", ",", "Hải", "Phòng", "tiếp", "tục", "khởi", "công", "dự", "án", "nhà",… | present 7,890; missing 0.0%; array length 3–100 |
| `tokens[]` | `string` | No | Dự | present 237,579; length 1–50; distinct 12,332 |

### `data/labeled/ner/syllables/final_dev_vifinner.jsonl`

Records: **7,890**; file container: `line_records`; record root types: `{"object": 7890}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `tags` | `array` | No | ["O", "O", "B-DATE", "I-DATE", "O", "B-ORG", "I-ORG", "O", "O", "O", "O", "O", "O", "O", "O", "O", "… | present 7,890; missing 0.0%; array length 3–100 |
| `tags[]` | `string` | No | O | present 237,579; length 1–8; distinct 15; values B-ASSET, B-DATE, B-MONEY, B-ORG, B-PERSON, B-RATE, B-VOLUME, I-ASSET, I-DATE, I-MONEY, I-ORG, I-PERSON, I-RATE, I-VOLUME, O |
| `tokens` | `array` | No | ["Dự", "kiến", "năm", "2024", ",", "Hải", "Phòng", "tiếp", "tục", "khởi", "công", "dự", "án", "nhà",… | present 7,890; missing 0.0%; array length 3–100 |
| `tokens[]` | `string` | No | Dự | present 237,579; length 1–50; distinct 12,332 |

### `data/labeled/ner/syllables/final_test_vifinner.jsonl`

Records: **7,852**; file container: `line_records`; record root types: `{"object": 7852}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `tags` | `array` | No | ["O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "B-O… | present 7,852; missing 0.0%; array length 2–114 |
| `tags[]` | `string` | No | O | present 237,515; length 1–8; distinct 15; values B-ASSET, B-DATE, B-MONEY, B-ORG, B-PERSON, B-RATE, B-VOLUME, I-ASSET, I-DATE, I-MONEY, I-ORG, I-PERSON, I-RATE, I-VOLUME, O |
| `tokens` | `array` | No | ["Đồng", "thời,", "tập", "đoàn", "cũng", "ghi", "nhận", "các", "khoản", "đầu", "tư", "góp", "vốn", "… | present 7,852; missing 0.0%; array length 2–114 |
| `tokens[]` | `string` | No | Đồng | present 237,515; length 1–59; distinct 12,254 |

### `data/labeled/ner/syllables/final_train_vifinner.jsonl`

Records: **36,750**; file container: `line_records`; record root types: `{"object": 36750}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `tags` | `array` | No | ["O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "B-ORG", "I-ORG", "I-ORG", "I-ORG", "I-ORG", "B-O… | present 36,750; missing 0.0%; array length 2–120 |
| `tags[]` | `string` | No | O | present 1,112,179; length 1–8; distinct 15; values B-ASSET, B-DATE, B-MONEY, B-ORG, B-PERSON, B-RATE, B-VOLUME, I-ASSET, I-DATE, I-MONEY, I-ORG, I-PERSON, I-RATE, I-VOLUME, O |
| `tokens` | `array` | No | ["Sự", "hợp", "tác", "được", "đồng", "hành", "và", "hỗ", "trợ", "bởi", "Cục", "Phát", "triển", "doan… | present 36,750; missing 0.0%; array length 2–120 |
| `tokens[]` | `string` | No | Sự | present 1,112,179; length 1–109; distinct ≥20,000 |

### `data/labeled/ner/syllables/test_vifinner.jsonl`

Records: **7,852**; file container: `line_records`; record root types: `{"object": 7852}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `tags` | `array` | No | ["O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "B-O… | present 7,852; missing 0.0%; array length 2–114 |
| `tags[]` | `string` | No | O | present 237,515; length 1–8; distinct 15; values B-ASSET, B-DATE, B-MONEY, B-ORG, B-PERSON, B-RATE, B-VOLUME, I-ASSET, I-DATE, I-MONEY, I-ORG, I-PERSON, I-RATE, I-VOLUME, O |
| `tokens` | `array` | No | ["Đồng", "thời,", "tập", "đoàn", "cũng", "ghi", "nhận", "các", "khoản", "đầu", "tư", "góp", "vốn", "… | present 7,852; missing 0.0%; array length 2–114 |
| `tokens[]` | `string` | No | Đồng | present 237,515; length 1–59; distinct 12,254 |

### `data/labeled/ner/syllables/train_vifinner.jsonl`

Records: **36,750**; file container: `line_records`; record root types: `{"object": 36750}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `tags` | `array` | No | ["O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "B-ORG", "I-ORG", "I-ORG", "I-ORG", "I-ORG", "B-O… | present 36,750; missing 0.0%; array length 2–120 |
| `tags[]` | `string` | No | O | present 1,112,179; length 1–8; distinct 15; values B-ASSET, B-DATE, B-MONEY, B-ORG, B-PERSON, B-RATE, B-VOLUME, I-ASSET, I-DATE, I-MONEY, I-ORG, I-PERSON, I-RATE, I-VOLUME, O |
| `tokens` | `array` | No | ["Sự", "hợp", "tác", "được", "đồng", "hành", "và", "hỗ", "trợ", "bởi", "Cục", "Phát", "triển", "doan… | present 36,750; missing 0.0%; array length 2–120 |
| `tokens[]` | `string` | No | Sự | present 1,112,179; length 1–109; distinct ≥20,000 |

### `data/labeled/span/*.json`

Records: **586,290**; file container: `array`; record root types: `{"object": 586290}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Câu chuyện của ông P., lãnh đạo cấp cao tại một tập đoàn bất động sản lớn trong nước, là một minh ch… | present 586,290; missing 0.0%; length 1–2313; distinct ≥20,000 |
| `label` | `string` | No | PERSON | present 586,290; missing 0.0%; length 3–6; distinct 11; values ASSET, DATE, EVENT, MONEY, N/A, ORG, PERSON, PRICE, RATE, TICKER, VOLUME |
| `text` | `string` | No | ông P. | present 586,290; missing 0.0%; length 1–2313; distinct ≥20,000 |

### `data/labeled/span_tags/0_PERSON.json`

Records: **21,872**; file container: `array`; record root types: `{"object": 21872}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Câu chuyện của ông P., lãnh đạo cấp cao tại một tập đoàn bất động sản lớn trong nước, là một minh ch… | present 21,872; missing 0.0%; length 5–841; distinct 16,727 |
| `label` | `string` | No | PERSON | present 21,872; missing 0.0%; length 6–6; distinct 1; values PERSON |
| `text` | `string` | No | ông P. | present 21,872; missing 0.0%; length 1–127; distinct 6,315 |

### `data/labeled/span_tags/1_ASSET.json`

Records: **30,297**; file container: `array`; record root types: `{"object": 30297}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Sở hữu danh mục đầu tư đa dạng từ cổ phiếu, trái phiếu đến các dự án bất động sản quy mô lớn, ông qu… | present 30,297; missing 0.0%; length 3–1020; distinct ≥20,000 |
| `label` | `string` | No | ASSET | present 30,297; missing 0.0%; length 5–5; distinct 1; values ASSET |
| `text` | `string` | No | cổ phiếu | present 30,297; missing 0.0%; length 2–207; distinct 9,523 |

### `data/labeled/span_tags/2_ORG.json`

Records: **180,569**; file container: `array`; record root types: `{"object": 180569}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Vì vậy, khi ACB ra mắt Chứng chỉ tiền gửi (CCTG) với lợi suất cao và cơ chế rút linh hoạt, ông nhanh… | present 180,569; missing 0.0%; length 2–889; distinct ≥20,000 |
| `label` | `string` | No | ORG | present 180,569; missing 0.0%; length 3–3; distinct 1; values ORG |
| `text` | `string` | No | ACB | present 180,569; missing 0.0%; length 1–197; distinct ≥20,000 |

### `data/labeled/span_tags/3_EVENT.json`

Records: **85,521**; file container: `array`; record root types: `{"object": 85521}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Vì vậy, khi ACB ra mắt Chứng chỉ tiền gửi (CCTG) với lợi suất cao và cơ chế rút linh hoạt, ông nhanh… | present 85,521; missing 0.0%; length 7–2313; distinct ≥20,000 |
| `label` | `string` | No | EVENT | present 85,521; missing 0.0%; length 5–5; distinct 1; values EVENT |
| `text` | `string` | No | ACB ra mắt Chứng chỉ tiền gửi (CCTG) | present 85,521; missing 0.0%; length 2–2313; distinct ≥20,000 |

### `data/labeled/span_tags/3_EVENT_clean.json`

Records: **62,391**; file container: `array`; record root types: `{"object": 62391}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `sentence` | `string` | No | Vì vậy, khi ACB ra mắt Chứng chỉ tiền gửi (CCTG) với lợi suất cao và cơ chế rút linh hoạt, ông nhanh… | present 62,391; missing 0.0%; length 7–2313; distinct ≥20,000 |

### `data/labeled/span_tags/3_EVENT_unique.json`

Records: **62,391**; file container: `array`; record root types: `{"object": 62391}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `sentence` | `string` | No | Vì vậy, khi ACB ra mắt Chứng chỉ tiền gửi (CCTG) với lợi suất cao và cơ chế rút linh hoạt, ông nhanh… | present 62,391; missing 0.0%; length 7–2313; distinct ≥20,000 |

### `data/labeled/span_tags/4_MONEY.json`

Records: **61,587**; file container: `array`; record root types: `{"object": 61587}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Sau khi được tư vấn cơ chế tính lãi theo thời gian nắm giữ và khả năng sử dụng vốn linh hoạt, ông qu… | present 61,587; missing 0.0%; length 2–1020; distinct ≥20,000 |
| `label` | `string` | No | MONEY | present 61,587; missing 0.0%; length 5–5; distinct 1; values MONEY |
| `text` | `string` | No | 98 tỷ đồng | present 61,587; missing 0.0%; length 1–81; distinct 19,945 |

### `data/labeled/span_tags/5_DATE.json`

Records: **86,523**; file container: `array`; record root types: `{"object": 86523}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Ra mắt từ cuối tháng 10/2025, CCTG của ACB nhanh chóng thu hút sự quan tâm của giới đầu tư và khách … | present 86,523; missing 0.0%; length 4–889; distinct ≥20,000 |
| `label` | `string` | No | DATE | present 86,523; missing 0.0%; length 4–4; distinct 1; values DATE |
| `text` | `string` | No | cuối tháng 10/2025 | present 86,523; missing 0.0%; length 1–81; distinct 12,580 |

### `data/labeled/span_tags/6_RATE.json`

Records: **74,106**; file container: `array`; record root types: `{"object": 74106}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | - Lợi suất hấp dẫn – sinh lời mỗi ngày với mức lãi cố định lên đến 6%/năm, tính theo thời gian nắm g… | present 74,106; missing 0.0%; length 1–889; distinct ≥20,000 |
| `label` | `string` | No | RATE | present 74,106; missing 0.0%; length 4–4; distinct 1; values RATE |
| `text` | `string` | No | 6%/năm | present 74,106; missing 0.0%; length 1–132; distinct 12,211 |

### `data/labeled/span_tags/7_TICKER.json`

Records: **28,418**; file container: `array`; record root types: `{"object": 28418}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Theo Báo cáo tài chính hợp nhất Quý 3 năm 2025, tổng tài sản của Tập đoàn Bảo Việt (BVH) đạt 272.801… | present 28,418; missing 0.0%; length 2–635; distinct 17,332 |
| `label` | `string` | No | TICKER | present 28,418; missing 0.0%; length 6–6; distinct 1; values TICKER |
| `text` | `string` | No | BVH | present 28,418; missing 0.0%; length 2–16; distinct 943 |

### `data/labeled/span_tags/8_VOLUME.json`

Records: **12,297**; file container: `array`; record root types: `{"object": 12297}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Được biết, năm 2026, Dệt may Liên Phương sẽ mở nhà máy mới tại Đắk Lắk với tổng vốn đầu tư lên tới 5… | present 12,297; missing 0.0%; length 8–1020; distinct 8,739 |
| `label` | `string` | No | VOLUME | present 12,297; missing 0.0%; length 6–6; distinct 1; values VOLUME |
| `text` | `string` | No | 900.000 bộ veston | present 12,297; missing 0.0%; length 1–81; distinct 7,811 |

### `data/labeled/span_tags/9_PRICE.json`

Records: **5,027**; file container: `array`; record root types: `{"object": 5027}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `evidence` | `string` | No | Tạm tính theo mức giá đóng cửa 24.050 đồng của ACB tại ngày 29/4/2025, giá trị số cổ phiếu nói trên … | present 5,027; missing 0.0%; length 10–589; distinct 3,729 |
| `label` | `string` | No | PRICE | present 5,027; missing 0.0%; length 5–5; distinct 1; values PRICE |
| `text` | `string` | No | 24.050 đồng | present 5,027; missing 0.0%; length 2–85; distinct 2,993 |

### `data/raw/cafeF_news.json`

Records: **11,242**; file container: `array`; record root types: `{"object": 11242}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `_id` | `string` | No | 69183bc4239a8c1b0ca0b82d | present 11,242; missing 0.0%; length 24–24; distinct 11,242 |
| `context` | `string` | No | Thời gian vàng, sinh lời vàng – Triết lý tài chính của nhà đầu tư hiện đại Câu chuyện của ông P., lã… | present 11,242; missing 0.0%; blank string 21; length 0–22859; distinct 9,219 |
| `index` | `integer` | No | 0 | present 11,242; missing 0.0%; range 0–11241; distinct 11,242 |
| `keyword` | `string` | No | ACB | present 11,242; missing 0.0%; length 3–28; distinct 86 |
| `link` | `string` | No | https://cafef.vn/chung-chi-tien-gui-acb-sinh-loi-tu-thoi-gian-vang-188251113064554631.chn | present 11,242; missing 0.0%; length 63–251; distinct 9,236 |
| `metadata` | `object` | No | {"Date": "2025-11-15", "Time": "15:37:24"} | present 11,242; missing 0.0% |
| `metadata.Date` | `string` | No | 2025-11-15 | present 11,242; missing 0.0%; length 10–10; distinct 1; date/time iso_date: 11,242; values 2025-11-15 |
| `metadata.Time` | `string` | No | 15:37:24 | present 11,242; missing 0.0%; length 8–8; distinct 7,135; date/time clock_24h: 11,242 |
| `page` | `integer` | No | 1 | present 11,242; missing 0.0%; range 1–59; distinct 59 |
| `post date` | `string` | No | 13-11-2025 - 07:30 AM | present 11,242; missing 0.0%; length 21–21; distinct 8,958; date/time cafef_12h: 4,926, cafef_24h_with_meridiem_nonstandard: 6,316 |
| `summary` | `string` | No | Trong giới đầu tư, thời điểm chính là chìa khóa của lợi nhuận. Những nhà đầu tư am hiểu tài chính lu… | present 11,242; missing 0.0%; length 17–484; distinct 9,213 |
| `ticket name` | `string` | No | Ngân hàng TMCP Á Châu | present 11,242; missing 0.0%; length 8–52; distinct 30 |
| `ticket symbol` | `string` | No | ACB | present 11,242; missing 0.0%; length 3–3; distinct 30 |

### `data/raw/cafef_news_raw.json`

Records: **11,242**; file container: `array`; record root types: `{"object": 11242}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `_id` | `string` | No | 69183bc4239a8c1b0ca0b82d | present 11,242; missing 0.0%; length 24–24; distinct 11,242 |
| `context` | `string` | No | Thời gian vàng, sinh lời vàng – Triết lý tài chính của nhà đầu tư hiện đại Câu chuyện của ông P., lã… | present 11,242; missing 0.0%; blank string 21; length 0–22859; distinct 9,219 |
| `index` | `integer` | No | 0 | present 11,242; missing 0.0%; range 0–11241; distinct 11,242 |
| `keyword` | `string` | No | ACB | present 11,242; missing 0.0%; length 3–28; distinct 86 |
| `link` | `string` | No | https://cafef.vn/chung-chi-tien-gui-acb-sinh-loi-tu-thoi-gian-vang-188251113064554631.chn | present 11,242; missing 0.0%; length 63–251; distinct 9,236 |
| `metadata` | `object` | No | {"Date": "2025-11-15", "Time": "15:37:24"} | present 11,242; missing 0.0% |
| `metadata.Date` | `string` | No | 2025-11-15 | present 11,242; missing 0.0%; length 10–10; distinct 1; date/time iso_date: 11,242; values 2025-11-15 |
| `metadata.Time` | `string` | No | 15:37:24 | present 11,242; missing 0.0%; length 8–8; distinct 7,135; date/time clock_24h: 11,242 |
| `page` | `integer` | No | 1 | present 11,242; missing 0.0%; range 1–59; distinct 59 |
| `post date` | `string` | No | 13-11-2025 - 07:30 AM | present 11,242; missing 0.0%; length 21–21; distinct 8,958; date/time cafef_12h: 4,926, cafef_24h_with_meridiem_nonstandard: 6,316 |
| `summary` | `string` | No | Trong giới đầu tư, thời điểm chính là chìa khóa của lợi nhuận. Những nhà đầu tư am hiểu tài chính lu… | present 11,242; missing 0.0%; length 17–484; distinct 9,213 |
| `ticket name` | `string` | No | Ngân hàng TMCP Á Châu | present 11,242; missing 0.0%; length 8–52; distinct 30 |
| `ticket symbol` | `string` | No | ACB | present 11,242; missing 0.0%; length 3–3; distinct 30 |
| `title` | `string` | No | Chứng chỉ tiền gửi ACB: Sinh lời từ "thời gian vàng" | present 11,242; missing 0.0%; length 21–212; distinct 9,229 |

### `data/raw/cafef_news_raw_final.json`

Records: **15,457**; file container: `array`; record root types: `{"object": 15457}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `_id` | `string` | No | 6981a01e05862df07893031f | present 15,457; missing 0.0%; length 24–24; distinct 15,457 |
| `context` | `null, string` | Yes | Tết không còn là mùa mua nhiều, mà là mua sắm có tính toán Những mùa mua sắm cuối năm gần đây cho th… | present 15,457; missing 0.0%; null 2; blank string 23; length 0–24831; distinct 12,677 |
| `index` | `integer` | No | 0 | present 15,457; missing 0.0%; range 0–15456; distinct 15,457 |
| `keyword` | `string` | No | ACB | present 15,457; missing 0.0%; length 3–28; distinct 90 |
| `link` | `string` | No | https://cafef.vn/tet-nay-neu-van-chi-tieu-bang-tien-mat-ban-co-dang-bo-lo-uu-dai-tu-acb-188260202073… | present 15,457; missing 0.0%; length 54–251; distinct 12,698 |
| `metadata` | `object` | No | {"Date": "2026-02-03", "Time": "14:13:34"} | present 15,457; missing 0.0% |
| `metadata.Date` | `string` | No | 2026-02-03 | present 15,457; missing 0.0%; length 10–10; distinct 1; date/time iso_date: 15,457; values 2026-02-03 |
| `metadata.Time` | `string` | No | 14:13:34 | present 15,457; missing 0.0%; length 8–8; distinct 5,014; date/time clock_24h: 15,457 |
| `page` | `integer` | No | 1 | present 15,457; missing 0.0%; range 1–77; distinct 77 |
| `post date` | `string` | No | 02-02-2026 - 07:32 AM | present 15,457; missing 0.0%; length 21–21; distinct 12,311; date/time cafef_12h: 6,757, cafef_24h_with_meridiem_nonstandard: 8,700 |
| `summary` | `string` | No | Ngày càng nhiều người trẻ bắt đầu nhìn lại những khoản chi sau kỳ nghỉ và tự hỏi: món nào thật sự đá… | present 15,457; missing 0.0%; length 17–484; distinct 12,624 |
| `ticket name` | `string` | No | Ngân hàng TMCP Á Châu | present 15,457; missing 0.0%; length 8–52; distinct 30 |
| `ticket symbol` | `string` | No | ACB | present 15,457; missing 0.0%; length 3–3; distinct 30 |
| `title` | `string` | No | Tết này, nếu vẫn chi tiêu bằng tiền mặt, bạn có đang bỏ lỡ ưu đãi từ ACB? | present 15,457; missing 0.0%; length 15–212; distinct 12,683 |

### `data/raw/news_titles.jsonl`

Records: **11,242**; file container: `line_records`; record root types: `{"object": 11242}`; encoding: `UTF-8`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `_id` | `string` | No | 69183bc4239a8c1b0ca0b82d | present 11,242; missing 0.0%; length 24–24; distinct 11,242 |
| `link` | `string` | No | https://cafef.vn/chung-chi-tien-gui-acb-sinh-loi-tu-thoi-gian-vang-188251113064554631.chn | present 11,242; missing 0.0%; length 63–251; distinct 9,236 |
| `title` | `string` | No | Chứng chỉ tiền gửi ACB: Sinh lời từ "thời gian vàng" | present 11,242; missing 0.0%; length 21–212; distinct 9,229 |

### `data/raw/vn30.xlsx`

Records: **30**; file container: `workbook_rows`; record root types: `{"object": 30}`; encoding: `OOXML ZIP/XML`.

| Field | Observed Type | Nullable | Example | Notes |
|---|---|---|---|---|
| `Keywords` | `string` | No | ["ACB", "Ngân hàng Á Châu", "Asia Commercial Bank", "ACB Bank", "Ngân hàng ACB"] | present 30; missing 0.0%; length 52–164; distinct 30 |
| `company_name_en` | `string` | No | Asia Commercial Bank | present 30; missing 0.0%; length 15–71; distinct 30 |
| `company_name_vi` | `string` | No | Ngân hàng TMCP Á Châu | present 30; missing 0.0%; length 8–52; distinct 30 |
| `ticket_symbol` | `string` | No | ACB | present 30; missing 0.0%; length 3–3; distinct 30 |

## 4. Data Quality Observations

The following are observations or heuristics; they are not silently corrected by profiling.

| Dataset | Observation | Count | Examples / interpretation |
|---|---|---:|---|
| `data/labeled/ner/raw/output_ner.jsonl` | `empty_field_name` | 1 | data/labeled/ner/raw/output_ner.jsonl:30763 |
| `data/labeled/ner/raw/output_ner.jsonl` | Missing/null `<empty field name>` | 59,174 | missing 59,174; explicit null 0. |
| `data/labeled/ner/raw/output_ner.jsonl` | Missing/null `sentence` | 58,834 | missing 58,834; explicit null 0. |
| `data/labeled/ner/raw/output_ner.jsonl` | Missing/null `tags` | 2 | missing 2; explicit null 0. |
| `data/labeled/ner/raw/output_ner.jsonl` | Missing/null `tokens` | 1 | missing 1; explicit null 0. |
| `data/raw/cafeF_news.json` | Repeated URL rows | 2,006 | 9,236 distinct observed URLs; repeated rows may carry different ticker/keyword values. |
| `data/raw/cafeF_news.json` | `blank_text_value` | 21 | context |
| `data/raw/cafeF_news.json` | `html_entity_in_text` | 4 | summary |
| `data/raw/cafeF_news.json` | `nonstandard_timestamp_values` | 6,316 | post date: 09-11-2025 - 15:36 PM |
| `data/raw/cafef_news_raw.json` | Repeated URL rows | 2,006 | 9,236 distinct observed URLs; repeated rows may carry different ticker/keyword values. |
| `data/raw/cafef_news_raw.json` | `blank_text_value` | 21 | context |
| `data/raw/cafef_news_raw.json` | `html_entity_in_text` | 4 | summary |
| `data/raw/cafef_news_raw.json` | `nonstandard_timestamp_values` | 6,316 | post date: 09-11-2025 - 15:36 PM |
| `data/raw/cafef_news_raw_final.json` | Repeated URL rows | 2,759 | 12,698 distinct observed URLs; repeated rows may carry different ticker/keyword values. |
| `data/raw/cafef_news_raw_final.json` | `blank_text_value` | 23 | context |
| `data/raw/cafef_news_raw_final.json` | `html_entity_in_text` | 25 | summary |
| `data/raw/cafef_news_raw_final.json` | `nonstandard_timestamp_values` | 8,700 | post date: 28-01-2026 - 16:44 PM |
| `data/raw/cafef_news_raw_final.json` | Missing/null `context` | 2 | missing 0; explicit null 2. |
| `data/raw/news_titles.jsonl` | Repeated URL rows | 2,006 | 9,236 distinct observed URLs; repeated rows may carry different ticker/keyword values. |

### Cross-file schema differences relative to the largest article snapshot

- `data/raw/cafeF_news.json`: only here `[]`; only in `data/raw/cafef_news_raw_final.json` `['title']`; type differences `{'context': {'primary': ['null', 'string'], 'dataset': ['string']}}`.
- `data/raw/cafef_news_raw.json`: only here `[]`; only in `data/raw/cafef_news_raw_final.json` `[]`; type differences `{'context': {'primary': ['null', 'string'], 'dataset': ['string']}}`.
- `data/raw/news_titles.jsonl`: only here `[]`; only in `data/raw/cafef_news_raw_final.json` `['context', 'index', 'keyword', 'metadata', 'metadata.Date', 'metadata.Time', 'page', 'post date', 'summary', 'ticket name', 'ticket symbol']`; type differences `{}`.

### Article-export findings requiring review

- `data/raw/cafef_news_raw_final.json` has 12,698 distinct URLs in 15,457 observations; 2,759 rows repeat an earlier URL. Its observed URL hosts are `{'cafef.vn': 15457}` and schemes are `{'https': 15457}`. Basic URL parsing found 0 malformed URL values.
- `context` contains 23 blank/whitespace strings and 2 explicit nulls. HTML-tag and HTML-entity counts are heuristic checks; the source may still contain non-HTML boilerplate or formatting problems.
- `post date` has 8,700 values with a 24-hour hour plus `AM`/`PM`. The profiler labels them nonstandard and does not rewrite them. `metadata.Date`/`metadata.Time` remain separate export metadata until their semantics are confirmed.
- The selected article export has no observed image URL, author, or editorial category field. The earlier `cafeF_news.json` lacks `title`; the title JSONL is only a derivative. No duplicate JSON object keys were detected in the article exports by this scan.

Check source-to-canonical mapping health separately: all currently required source fields were observed with string values.

<!-- END GENERATED OBSERVED DATA -->




## 5. Proposed Bronze Contract

Bronze preserves the exact source object bytes in immutable storage. Each source record retains its original field names, nesting, values, order within the file, and optional/null fields. The JSON array snapshot is not rewritten into a guessed canonical schema. An ingestion manifest adds only `ingestion_id`, `source` (derived from the verified URL host, currently `cafef.vn`), `source_file`, `ingested_at` (UTC time of import, **not** publication time), `ingestion_date`, `raw_record_hash` or source-file SHA-256, byte size, record count, and source row position where record-level lineage is needed. Hashing/canonicalization rules must be versioned. These are system metadata, not original CafeF fields. The current `_id` is an export ID and must remain intact in Bronze.

## 6. Proposed Canonical Silver Article Contract

**Engineering proposal, version 1.** This section is intentionally outside the generated observed block. Regenerating a source profile must not change this contract without review. `required` refers to accepted Silver articles; a malformed observation goes to a rejects dataset with batch/row/reason lineage. The article grain is one `(source, canonical_url)`; retain repeated search/ticker associations in a separate `article_mentions` table.

| Canonical Field | Type | Required | Source Mapping | Transformation | Notes |
|---|---|---|---|---|---|
| `article_id` | string | Yes | `link` plus derived `source` | Deterministic ID from source and canonical URL | Do not use Mongo `_id` as the article key. |
| `source` | string | Yes | `link` host | Validate host and map to provider code | Current observed provider: CafeF only. |
| `source_url` | string | Yes | `link` | Preserve original value | Required for source citation. |
| `canonical_url` | string | Yes | `link` | Apply documented URL normalization | Do not erase original URL. |
| `title` | string | Yes | `title` | Unicode/whitespace normalization | Present in selected final snapshot; absent in older `cafeF_news.json`. |
| `description` | string? | No | `summary` | Conservative text normalization | A teaser, not the article body. |
| `content` | string | Yes | `context` | HTML/text cleanup, Unicode NFC, whitespace normalization | Empty/null bodies are rejected or quarantined; Bronze preserves them. |
| `published_at` | timestamp? | No | `post date` | Parse only reviewed CafeF formats with an explicit Asia/Ho_Chi_Minh policy | Keep raw string and parse status. The observed 24-hour-plus-meridiem form is nonstandard; leave it null until its interpretation is approved. |
| `published_at_raw` | string? | No | `post date` | Preserve source string | Avoid invented time. |
| `content_hash` | string | Yes | normalized `content` | Deterministic hash with versioned normalization | Same content on different URLs is flagged, not automatically merged. |
| `processing_version` | string | Yes | system configuration | Record normalization/schema version | Supports reproducible replay. |
| `source_ingestion_id` | string | Yes | Bronze manifest | Carry lineage | Links Silver to immutable source. |
| `author` | string? | No | Unavailable | No mapping | Cannot currently be populated from checked-in article JSON. |
| `crawled_at` | timestamp? | No | Unavailable | No mapping | `metadata.Date`/`Time` may be export/capture metadata, but semantics are unverified. |
| `category` | string? | No | Unavailable | No mapping | `keyword` is a search term, not a confirmed editorial category. |
| `image_urls` | array<string> | No | Unavailable | No mapping | No image URL field observed in article export. |

`article_mentions` records distinct `(article_id, ticker_symbol, keyword)` observations with original `ticket name`, `page`, `index`, and source row lineage. These source fields are search/discovery metadata; a ticker association is **not** proof the article's text mentions that security. A single article can have multiple associations.

## 7. Source-to-Canonical Mapping

Current canonical seed: `data/raw/cafef_news_raw_final.json`. Explicit source mappings:

| Current source field | Canonical destination | Status |
|---|---|---|
| `link` | `source_url`, `canonical_url`, and derived `article_id`/`source` | Observed; validate URL. |
| `title` | `title` | Observed in final snapshot. |
| `summary` | `description` | Observed. |
| `context` | `content` then `content_hash` | Observed; can be empty/null. |
| `post date` | `published_at_raw`, parsed `published_at` | Observed; some values malformed. |
| `ticket symbol` | `article_mentions.ticker_symbol` | Observed; source spelling preserved in Bronze. |
| `ticket name` | `article_mentions.ticker_name` | Observed. |
| `keyword` | `article_mentions.keyword` | Observed search term. |
| `page`, `index` | `article_mentions.source_page`, `source_index` | Observed positional metadata. |
| `_id` | Bronze lineage only | Observed export identifier, not canonical article ID. |
| `metadata.Date`, `metadata.Time` | Bronze lineage only | Observed; do not call publication/crawl time without provenance. |

## 8. Future Enrichment Contract

An optional enrichment output may add `entities` (typed mentions with spans and model version), `stock_symbols` (resolved security identifiers with confidence/provenance), and `financial_events` (event type, evidence span, time, model version). These are **future ViFinNER/NLP outputs**. The current raw sample has search ticker tags but does not provide these enriched fields. Silver and Gold creation must work when enrichment is unavailable; record `enrichment_status` and `enricher_version` when an enricher is used.

## 9. Gold RAG Chunk Contract

This is a proposed future projection from versioned Silver/Gold articles, not an observed raw schema.

| Field | Type | Availability / derivation |
|---|---|---|
| `chunk_id` | string | Deterministic from `article_id`, article content version, chunker version, chunk index. |
| `article_id` | string | From accepted Silver article. |
| `chunk_index` | integer | Generated by chunker, ordered from zero. |
| `text` | string | Slice of normalized `content`. |
| `title` | string | Propagated from article. |
| `source` | string | Derived/validated from URL host. |
| `source_url` | string | Propagated original article URL. |
| `published_at` | timestamp? | Parsed if valid; otherwise null. |
| `stock_symbols` | array<string> | Search ticker associations available now; resolved in-text entities are future enrichment and must be distinguished. |
| `entities` | array<object>? | Future enrichment; absent/null now. |
| `processing_version` | string | From article/chunker configuration. |

Embeddings and Qdrant point IDs are separate, rebuildable projections of committed Gold chunks. A chunk is valid without an embedding.

## 10. Open Questions

1. What exactly do export `metadata.Date` and `metadata.Time` mean, and what timezone were they recorded in?
2. Which URL canonicalization and article-version policy should handle source edits, redirects, and tracking parameters?
3. Should malformed `post date` strings such as a 24-hour hour paired with `PM` be parsed by a documented exception or left null for manual review?
4. Are `ticket symbol`/`keyword` merely search provenance, or may any be promoted to verified article-level tags?
5. How should the project govern content-identical articles published at different URLs and older overlapping snapshots?
6. Which future providers and license/provenance rules will apply? Only CafeF article URLs were observed in this repository.

## Regeneration and drift workflow

- Run `make data-contracts` after adding or changing files under `data/`. It rescans recursively, replaces only sections 1–4 between generator markers, and writes `artifacts/data-profile.json`. Sections 5–10 are review-owned and preserved.
- Run `make data-contracts-check` in review/CI before regeneration. It rescans read-only, compares with the saved profile, prints source schema drift and count changes, and exits nonzero for structural drift. It does not change either output file.
- A changed observed field is **source schema drift**, not automatic approval to change the Silver contract. Review mapping health, update source adapters/tests if needed, and change sections 5–10 only through an explicit engineering decision.
- The machine profile records UTC scan time, so timestamps change when regenerated. Dataset ordering and all other output are stable for unchanged input.
