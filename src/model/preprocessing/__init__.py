"""ViFinNER preprocessing — medallion-style data engineering.

The ``medallion`` subpackage implements the **Bronze → Silver → Gold**
flow used by the RAG ingestion pipeline:

* **Bronze**: raw HTML/JSON articles persisted to MongoDB.
* **Silver**: Polars-powered cleaning, dedup and normalisation.
* **Gold**: chunk + embed + load into PGVector.
"""

from src.preprocessing.medallion.pipeline import (  # noqa: F401
    MedallionPipeline,
    MedallionReport,
)
