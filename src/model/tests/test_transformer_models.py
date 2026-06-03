"""Unit tests for transformer-based NER models (XLM-R, PhoBERT).

These tests use a mock/tiny transformer config to avoid downloading
large pretrained models during testing. The structural tests verify
forward pass shapes, loss computation, and CRF decoding behavior.
"""

import pytest
import torch
from torch import nn
from unittest.mock import patch, MagicMock
from transformers import AutoConfig, AutoModel

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import (
    NUM_TAGS, BATCH_SIZE, TRANSFORMER_SEQ_LEN, DROPOUT,
)


# ==============================================================================
# Helper: Create a tiny transformer model for fast testing
# ==============================================================================

def create_mock_encoder(hidden_size=64, num_hidden_layers=2):
    """Create a minimal transformer encoder for testing.

    Returns a mock that behaves like AutoModel output.
    """
    class FakeEncoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.config = type("Config", (), {
                "hidden_size": hidden_size,
                "num_hidden_layers": num_hidden_layers,
            })()
            self.linear = nn.Linear(hidden_size, hidden_size)

        def forward(self, input_ids=None, attention_mask=None, **kwargs):
            batch_size, seq_len = input_ids.shape
            # Generate fake hidden states
            hidden = torch.randn(batch_size, seq_len, hidden_size)
            output = type("Output", (), {
                "last_hidden_state": hidden,
                "hidden_states": tuple(
                    torch.randn(batch_size, seq_len, hidden_size)
                    for _ in range(num_hidden_layers + 1)
                ),
            })()
            return output

        def parameters(self):
            return iter([self.linear.weight, self.linear.bias])

    return FakeEncoder()


# ==============================================================================
# XLMR_CRF Tests
# ==============================================================================


class TestXLMR_CRF:
    """Tests for XLM-RoBERTa + CRF model."""

    @pytest.fixture
    def model(self):
        """Create model with mocked encoder."""
        from model.XLM_R import XLMR_CRF

        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = XLMR_CRF(num_tags=NUM_TAGS, model_name="xlm-roberta-base", dropout=DROPOUT)
        return model

    def test_initialization(self, model):
        """Test model architecture components."""
        assert hasattr(model, "encoder")
        assert hasattr(model, "dropout")
        assert hasattr(model, "classifier")
        assert hasattr(model, "crf")
        assert model.crf.num_tags == NUM_TAGS
        assert model.classifier.out_features == NUM_TAGS

    def test_training_returns_loss(self, model, transformer_input):
        """Test forward with labels returns scalar loss."""
        input_ids, attention_mask, labels = transformer_input
        model.train()

        loss = model(input_ids, attention_mask, labels)

        assert isinstance(loss, torch.Tensor)
        assert loss.dim() == 0
        assert loss.item() > 0
        assert loss.requires_grad is True

    def test_inference_returns_predictions(self, model, transformer_input):
        """Test forward without labels returns decoded sequences."""
        input_ids, attention_mask, _ = transformer_input
        model.eval()

        with torch.no_grad():
            preds = model(input_ids, attention_mask)

        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE
        for seq in preds:
            assert isinstance(seq, list)
            assert all(isinstance(t, int) for t in seq)
            assert all(0 <= t < NUM_TAGS for t in seq)

    def test_predictions_respect_mask(self, model, transformer_input):
        """Test that predictions respect attention mask (no predictions at pad positions)."""
        input_ids, attention_mask, _ = transformer_input
        model.eval()

        with torch.no_grad():
            preds = model(input_ids, attention_mask)

        valid_len = attention_mask[0].sum().item()
        # CRF decode with mask should produce sequences matching valid length
        for pred, mask in zip(preds, attention_mask):
            expected_len = mask.sum().item()
            assert len(pred) == expected_len

    def test_loss_backward(self, model, transformer_input):
        """Test gradient computation through loss."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)
        loss.backward()

        # Check classifier and CRF have gradients
        assert model.classifier.weight.grad is not None
        for param in model.crf.parameters():
            if param.requires_grad:
                assert param.grad is not None

    def test_loss_is_finite(self, model, transformer_input):
        """Test that loss does not produce NaN or Inf."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)

        assert torch.isfinite(loss).item()

    def test_different_batch_sizes(self, model):
        """Test model with various batch sizes."""
        for batch_size in [1, 2, 8]:
            input_ids = torch.randint(1, 1000, (batch_size, 16))
            attention_mask = torch.ones(batch_size, 16, dtype=torch.long)
            labels = torch.randint(0, NUM_TAGS, (batch_size, 16))

            loss = model(input_ids, attention_mask, labels)
            assert loss.dim() == 0

    def test_different_seq_lengths(self, model):
        """Test model handles different sequence lengths."""
        for seq_len in [8, 16, 32, 64]:
            input_ids = torch.randint(1, 1000, (2, seq_len))
            attention_mask = torch.ones(2, seq_len, dtype=torch.long)
            labels = torch.randint(0, NUM_TAGS, (2, seq_len))

            loss = model(input_ids, attention_mask, labels)
            assert torch.isfinite(loss).item()


# ==============================================================================
# XLMR_Large_CRF Tests
# ==============================================================================


class TestXLMR_Large_CRF:
    """Tests for XLM-RoBERTa Large + CRF model."""

    @pytest.fixture
    def model(self):
        """Create model with mocked encoder (1024-dim like large)."""
        from model.XLMR_Large import XLMR_Large_CRF

        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder(hidden_size=1024)):
            model = XLMR_Large_CRF(num_tags=NUM_TAGS, dropout=DROPOUT)
        return model

    def test_initialization(self, model):
        """Test large model has correct hidden size."""
        assert model.classifier.in_features == 1024
        assert model.classifier.out_features == NUM_TAGS
        assert model.crf.num_tags == NUM_TAGS

    def test_training_returns_loss(self, model, transformer_input):
        """Test training forward pass."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)

        assert loss.dim() == 0
        assert loss.item() > 0

    def test_inference_returns_predictions(self, model, transformer_input):
        """Test inference forward pass."""
        input_ids, attention_mask, _ = transformer_input
        model.eval()

        with torch.no_grad():
            preds = model(input_ids, attention_mask)

        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE

    def test_hidden_size_difference_from_base(self):
        """Test that large model uses 1024 vs base 768."""
        from model.XLMR_Large import XLMR_Large_CRF

        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder(hidden_size=1024)):
            large = XLMR_Large_CRF(num_tags=NUM_TAGS)

        assert large.classifier.in_features == 1024


# ==============================================================================
# PhoBERT_CRF Tests
# ==============================================================================


class TestPhoBERT_CRF:
    """Tests for PhoBERT + CRF model."""

    @pytest.fixture
    def model(self):
        """Create PhoBERT_CRF with mocked encoder."""
        from model.PhoBERT_CRF import PhoBERT_CRF

        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = PhoBERT_CRF(
                num_tags=NUM_TAGS,
                model_name="vinai/phobert-base-v2",
                dropout=DROPOUT,
                freeze_encoder=False,
            )
        return model

    def test_initialization(self, model):
        """Test PhoBERT model components."""
        assert hasattr(model, "encoder")
        assert hasattr(model, "classifier")
        assert hasattr(model, "crf")
        assert model.crf.num_tags == NUM_TAGS

    def test_training_returns_loss(self, model, transformer_input):
        """Test training mode loss."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)

        assert loss.dim() == 0
        assert torch.isfinite(loss).item()

    def test_inference_returns_predictions(self, model, transformer_input):
        """Test inference mode predictions."""
        input_ids, attention_mask, _ = transformer_input
        model.eval()

        with torch.no_grad():
            preds = model(input_ids, attention_mask)

        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE

    def test_freeze_encoder(self):
        """Test that freeze_encoder stops encoder gradient flow."""
        from model.PhoBERT_CRF import PhoBERT_CRF

        encoder = create_mock_encoder()
        with patch.object(AutoModel, "from_pretrained", return_value=encoder):
            model = PhoBERT_CRF(
                num_tags=NUM_TAGS,
                freeze_encoder=True,
            )

        for param in model.encoder.parameters():
            assert param.requires_grad is False

    def test_unfreeze_encoder(self):
        """Test that encoder parameters are trainable when not frozen."""
        from model.PhoBERT_CRF import PhoBERT_CRF

        encoder = create_mock_encoder()
        with patch.object(AutoModel, "from_pretrained", return_value=encoder):
            model = PhoBERT_CRF(
                num_tags=NUM_TAGS,
                freeze_encoder=False,
            )

        for param in model.encoder.parameters():
            assert param.requires_grad is True

    def test_loss_backward_with_frozen_encoder(self):
        """Test backprop works with frozen encoder (only head trained)."""
        from model.PhoBERT_CRF import PhoBERT_CRF

        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = PhoBERT_CRF(num_tags=NUM_TAGS, freeze_encoder=True)

        input_ids = torch.randint(1, 1000, (2, 16))
        attention_mask = torch.ones(2, 16, dtype=torch.long)
        labels = torch.randint(0, NUM_TAGS, (2, 16))

        loss = model(input_ids, attention_mask, labels)
        loss.backward()

        # Classifier should have gradients
        assert model.classifier.weight.grad is not None
