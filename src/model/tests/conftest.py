"""Pytest configuration and shared fixtures for model unit tests."""

import pytest
import torch


# ==============================================================================
# Constants
# ==============================================================================

VOCAB_SIZE = 500
EMBEDDING_DIM = 64
HIDDEN_SIZE = 32
NUM_TAGS = 15  # BIO tags for 10 entity types: B/I for each + O = 21? No: 15 per spec
BATCH_SIZE = 4
SEQ_LEN = 20
NUM_LAYERS = 2
DROPOUT = 0.1

# For transformer-based models (use tiny config for speed)
TRANSFORMER_SEQ_LEN = 32


# ==============================================================================
# Device
# ==============================================================================

@pytest.fixture
def device():
    """Return available compute device."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


# ==============================================================================
# BiLSTM fixtures
# ==============================================================================

@pytest.fixture
def bilstm_input():
    """Generate random input for BiLSTM-style models."""
    input_ids = torch.randint(1, VOCAB_SIZE, (BATCH_SIZE, SEQ_LEN))
    lengths = torch.tensor([SEQ_LEN] * BATCH_SIZE)
    tags = torch.randint(0, NUM_TAGS, (BATCH_SIZE, SEQ_LEN))
    return input_ids, lengths, tags


# ==============================================================================
# Transformer fixtures
# ==============================================================================

@pytest.fixture
def transformer_input():
    """Generate random input for transformer-based models.

    Returns input_ids, attention_mask, and labels compatible with
    XLM-RoBERTa tokenizer output format.
    """
    input_ids = torch.randint(1, 250000, (BATCH_SIZE, TRANSFORMER_SEQ_LEN))
    attention_mask = torch.ones(BATCH_SIZE, TRANSFORMER_SEQ_LEN, dtype=torch.long)
    # Simulate padding at end
    attention_mask[:, -5:] = 0
    labels = torch.randint(0, NUM_TAGS, (BATCH_SIZE, TRANSFORMER_SEQ_LEN))
    return input_ids, attention_mask, labels


@pytest.fixture
def span_input():
    """Generate random input for span-based NER model.

    Returns input_ids, attention_mask, and span_labels matrix.
    """
    input_ids = torch.randint(1, 250000, (BATCH_SIZE, TRANSFORMER_SEQ_LEN))
    attention_mask = torch.ones(BATCH_SIZE, TRANSFORMER_SEQ_LEN, dtype=torch.long)
    attention_mask[:, -5:] = 0
    # Span labels: (B, T, T) with 0 = non-entity
    span_labels = torch.zeros(
        BATCH_SIZE, TRANSFORMER_SEQ_LEN, TRANSFORMER_SEQ_LEN, dtype=torch.long
    )
    # Add some entity spans
    for b in range(BATCH_SIZE):
        span_labels[b, 2, 4] = 1  # entity type 1 from token 2 to 4
        span_labels[b, 7, 8] = 3  # entity type 3 from token 7 to 8
    return input_ids, attention_mask, span_labels


# ==============================================================================
# Temporary data fixtures
# ==============================================================================

@pytest.fixture
def tmp_jsonl_file(tmp_path):
    """Create a temporary JSONL file with NER data."""
    import json

    data = [
        {
            "tokens": ["Ngân", "hàng", "ACB", "đạt", "lợi", "nhuận"],
            "tags": ["B-ORG", "I-ORG", "I-ORG", "O", "O", "O"],
        },
        {
            "tokens": ["FPT", "tăng", "10", "%"],
            "tags": ["B-TICKER", "O", "B-RATE", "I-RATE"],
        },
        {
            "tokens": ["Năm", "2024", "doanh", "thu", "đạt", "100", "tỷ"],
            "tags": ["B-DATE", "I-DATE", "O", "O", "O", "B-MONEY", "I-MONEY"],
        },
    ]

    filepath = tmp_path / "test_data.jsonl"
    with open(filepath, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return str(filepath)


@pytest.fixture
def sample_vocab(tmp_jsonl_file):
    """Build a Vocab instance from test data."""
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from DataUtils.NER_dataset import Vocab

    return Vocab(tmp_jsonl_file)
