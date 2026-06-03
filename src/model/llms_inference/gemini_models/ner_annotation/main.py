from pipeline import run_pipeline

def main():
    run_pipeline(
        input_json_file="/Users/kittnguyen/Documents/DS201_Finance/data/labeled/span_tags/3_EVENT_clean.json",
        output_jsonl_file="/Users/kittnguyen/Documents/DS201_Finance/data/labeled/ner/raw/output_ner.jsonl",
        start_index=0,
        end_index=2
    )

if __name__ == "__main__":
    main()