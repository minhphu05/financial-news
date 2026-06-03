"""Re-populate Qdrant after server upgrade."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.rag.config import get_settings
from src.rag.databases import MongoRepository, QdrantRepository
from src.rag.ingestion.embedder import VoyageAIEmbedder
from src.rag.ingestion.pipeline import IngestionPipeline

settings = get_settings()
mongo = MongoRepository(settings=settings)
qdrant = QdrantRepository(settings=settings)
embedder = VoyageAIEmbedder(settings=settings)

pipeline = IngestionPipeline(mongo=mongo, qdrant=qdrant, embedder=embedder, settings=settings)
report = pipeline.run(max_articles=20)
print(f"Cleaned: {report.cleaned_articles}, Embedded: {report.embedded_articles}, Chunks: {report.chunks_written}")
