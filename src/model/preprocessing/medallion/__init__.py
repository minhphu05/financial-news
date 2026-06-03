"""Medallion data engineering layers for ViFinNER.

Each layer is intentionally side-effect-free at the **transform** level
and only touches storage at well-defined boundaries:

* ``bronze`` — extract from the scrape store (MongoDB ``cafef_raw``).
* ``silver`` — Polars-native transformations (clean, dedup, normalise).
* ``gold``   — chunk + embed and load into PGVector.
* ``pipeline`` — orchestrator that wires the three stages together.
"""

from src.preprocessing.medallion.bronze import BronzeStage
from src.preprocessing.medallion.gold import GoldStage
from src.preprocessing.medallion.pipeline import MedallionPipeline, MedallionReport
from src.preprocessing.medallion.silver import SilverStage

__all__ = [
    "BronzeStage",
    "SilverStage",
    "GoldStage",
    "MedallionPipeline",
    "MedallionReport",
]
