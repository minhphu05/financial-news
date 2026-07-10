"""CDC-driven medallion ingestion from scraped article files into Qdrant."""

from src.rag.cdc.processor import CdcMedallionProcessor
from src.rag.cdc.settings import CdcSettings

__all__ = ["CdcMedallionProcessor", "CdcSettings"]
