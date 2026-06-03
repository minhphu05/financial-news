# All tickers (reads the only .xlsx in data/raw/, takes Keywords column)
python -m src.scraper.run

# A specific ticker, capped at N pages per keyword
python -m src.scraper.run --ticker BCM --max-pages 1
python -m src.scraper.run --ticker BCM --ticker FPT --max-pages 3