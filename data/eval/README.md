# RAG evaluation dataset

`rag_eval.jsonl` is a small Vietnamese-language evaluation set used to
sanity-check the ViFinNER RAG system. Each line is a JSON object with
the following fields:

| Field               | Type      | Description |
|---------------------|-----------|-------------|
| `id`                | `string`  | Stable identifier (`vif-XXX`). |
| `question`          | `string`  | User question in Vietnamese. |
| `expected_keywords` | `string[]`| Keywords expected to appear in a good answer. |
| `expected_tickers`  | `string[]`| Tickers expected to surface in the retrieved citations. Empty for cross-cutting questions. |
| `category`          | `string`  | Coarse-grained topic (interest_rate, corporate_news, earnings, …). |
| `difficulty`        | `string`  | `easy` / `medium` / `hard`. |

The evaluation runner (`src/rag/evaluation/runner.py`) computes the
following metrics:

* **Retrieval recall** — fraction of items where at least one retrieved
  citation matches an `expected_ticker` (skipped when `expected_tickers`
  is empty).
* **Keyword recall** — fraction of `expected_keywords` that appear in the
  generated answer.
* **Refusal rate** — fraction of items where the model returned a
  "không tìm thấy thông tin" style refusal.
* **Latency** — p50 / p95 wall-clock latency per question.

All metrics + per-item traces are logged to MLflow under the
experiment `MLFLOW_EXPERIMENT_RAG`.
