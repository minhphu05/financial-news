import json
from pipeline import run_pipeline

def main():
    # load data
    with open("/Users/kittnguyen/Documents/DS201_Finance/data/raw/cafef_news_raw.json", "r", encoding="utf-8") as f:
        data_list = json.load(f)

    # Lấy list contexts
    contexts = [item["context"] for item in data_list]
    output_dir = "/Users/kittnguyen/Documents/DS201_Finance/data/labeled/span"
    run_pipeline(
        contexts=contexts,
        filedir=output_dir,
        start_index=0,
        end_index=1
    )
    
if __name__ == "__main__":
    main()