"""Unit tests for Span-based NER model (XLMR_Span_NER, SpanWidthEmbedding, BiaffineClassifier)."""

import pytest
import torch
from torch import nn
from unittest.mock import patch
from transformers import AutoModel

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from model.XLMR_Span_NER import SpanWidthEmbedding, BiaffineClassifier, XLMR_Span_NER
from tests.conftest import BATCH_SIZE, TRANSFORMER_SEQ_LEN, DROPOUT
from tests.test_transformer_models import create_mock_encoder

NUM_ENTITY_TYPES = 10  # 10 entity types for Vietnamese Financial NER


# ==============================================================================
# SpanWidthEmbedding Tests
# ==============================================================================


class TestSpanWidthEmbedding:
    """Tests for the SpanWidthEmbedding module."""

    @pytest.fixture
    def module(self):
        return SpanWidthEmbedding(max_span_width=30, embedding_dim=128)

    def test_initialization(self, module):
        """Test embedding layer dimensions."""
        assert module.width_embedding.num_embeddings == 31  # 0 to 30
        assert module.width_embedding.embedding_dim == 128

    def test_output_shape(self, module):
        """Test output shape for various inputs."""
        widths = torch.tensor([1, 2, 3, 5, 10, 20])
        output = module(widths)
        assert output.shape == (6, 128)

    def test_clamping_large_widths(self, module):
        """Test that widths exceeding max are clamped."""
        widths = torch.tensor([50, 100, 200])
        output = module(widths)
        # Should not raise error, widths are clamped to max_span_width
        assert output.shape == (3, 128)

    def test_clamping_negative_widths(self, module):
        """Test that negative widths are clamped to 0."""
        widths = torch.tensor([-1, -5, 0])
        output = module(widths)
        assert output.shape == (3, 128)

    def test_same_width_same_embedding(self, module):
        """Test that same widths produce same embeddings."""
        widths = torch.tensor([5, 5, 5])
        output = module(widths)
        assert torch.allclose(output[0], output[1])
        assert torch.allclose(output[1], output[2])

    def test_different_widths_different_embeddings(self, module):
        """Test that different widths produce different embeddings."""
        widths = torch.tensor([1, 2, 3])
        output = module(widths)
        # Very unlikely to be equal for different indices
        assert not torch.allclose(output[0], output[1])

    def test_gradient_flow(self, module):
        """Test gradient computation."""
        widths = torch.tensor([1, 3, 5])
        output = module(widths)
        loss = output.sum()
        loss.backward()
        assert module.width_embedding.weight.grad is not None

    def test_different_configs(self):
        """Test various configuration combinations."""
        for max_width, emb_dim in [(5, 32), (50, 256), (100, 64)]:
            module = SpanWidthEmbedding(max_span_width=max_width, embedding_dim=emb_dim)
            widths = torch.randint(0, max_width, (10,))
            output = module(widths)
            assert output.shape == (10, emb_dim)


# ==============================================================================
# BiaffineClassifier Tests
# ==============================================================================


class TestBiaffineClassifier:
    """Tests for the BiaffineClassifier module."""

    @pytest.fixture
    def module(self):
        return BiaffineClassifier(input_size=64, num_classes=NUM_ENTITY_TYPES + 1)

    def test_initialization(self, module):
        """Test biaffine weight and linear layers."""
        assert module.num_classes == NUM_ENTITY_TYPES + 1
        assert module.biaffine_weight.shape == (NUM_ENTITY_TYPES + 1, 64, 64)
        assert module.start_linear.in_features == 64
        assert module.start_linear.out_features == NUM_ENTITY_TYPES + 1
        assert module.end_linear.in_features == 64
        assert module.end_linear.out_features == NUM_ENTITY_TYPES + 1

    def test_output_shape(self, module):
        """Test output is (B, T, T, C)."""
        batch_size, seq_len, dim = 2, 10, 64
        start = torch.randn(batch_size, seq_len, dim)
        end = torch.randn(batch_size, seq_len, dim)

        scores = module(start, end)
        assert scores.shape == (batch_size, seq_len, seq_len, NUM_ENTITY_TYPES + 1)

    def test_output_shape_various_sizes(self, module):
        """Test with different sequence lengths."""
        for seq_len in [5, 16, 32]:
            start = torch.randn(BATCH_SIZE, seq_len, 64)
            end = torch.randn(BATCH_SIZE, seq_len, 64)
            scores = module(start, end)
            assert scores.shape == (BATCH_SIZE, seq_len, seq_len, NUM_ENTITY_TYPES + 1)

    def test_gradient_flow(self, module):
        """Test gradients flow through biaffine computation."""
        start = torch.randn(2, 10, 64, requires_grad=True)
        end = torch.randn(2, 10, 64, requires_grad=True)

        scores = module(start, end)
        loss = scores.sum()
        loss.backward()

        assert start.grad is not None
        assert end.grad is not None
        assert module.biaffine_weight.grad is not None

    def test_bias_initialization(self, module):
        """Test bias is initialized to zeros."""
        assert torch.allclose(module.bias, torch.zeros(NUM_ENTITY_TYPES + 1))

    def test_asymmetric_scores(self, module):
        """Test that biaffine scores are asymmetric (start->end != end->start)."""
        start = torch.randn(1, 5, 64)
        end = torch.randn(1, 5, 64)

        scores = module(start, end)
        # Score[i,j] should differ from Score[j,i] in general
        # Check the full matrix is not symmetric
        assert not torch.allclose(scores[0], scores[0].transpose(0, 1))


# ==============================================================================
# XLMR_Span_NER Tests
# ==============================================================================


class TestXLMR_Span_NER:
    """Tests for the full Span-based NER model."""

    @pytest.fixture
    def model(self):
        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = XLMR_Span_NER(
                num_entity_types=NUM_ENTITY_TYPES,
                model_name="xlm-roberta-base",
                span_hidden_size=32,
                max_span_width=15,
                dropout=DROPOUT,
                negative_sample_ratio=1.0,
            )
        return model

    def test_initialization(self, model):
        """Test model components."""
        assert hasattr(model, "encoder")
        assert hasattr(model, "start_ffn")
        assert hasattr(model, "end_ffn")
        assert hasattr(model, "width_embedding")
        assert hasattr(model, "biaffine")
        assert model.max_span_width == 15
        assert model.num_entity_types == NUM_ENTITY_TYPES

    def test_training_returns_loss_and_scores(self, model, span_input):
        """Test training forward returns dict with loss and span_scores."""
        input_ids, attention_mask, span_labels = span_input
        output = model(input_ids, attention_mask, span_labels)

        assert isinstance(output, dict)
        assert "loss" in output
        assert "span_scores" in output
        assert output["loss"].dim() == 0
        assert torch.isfinite(output["loss"]).item()

    def test_inference_returns_scores_and_mask(self, model, span_input):
        """Test inference returns span_scores and span_mask."""
        input_ids, attention_mask, _ = span_input
        model.eval()

        with torch.no_grad():
            output = model(input_ids, attention_mask)

        assert isinstance(output, dict)
        assert "span_scores" in output
        assert "span_mask" in output

    def test_span_scores_shape(self, model, span_input):
        """Test span_scores has correct shape (B, T, T, num_types+1)."""
        input_ids, attention_mask, _ = span_input
        model.eval()

        with torch.no_grad():
            output = model(input_ids, attention_mask)

        expected_shape = (
            BATCH_SIZE, TRANSFORMER_SEQ_LEN, TRANSFORMER_SEQ_LEN,
            NUM_ENTITY_TYPES + 1,
        )
        assert output["span_scores"].shape == expected_shape

    def test_span_mask_shape(self, model, span_input):
        """Test span_mask has correct shape (B, T, T)."""
        input_ids, attention_mask, _ = span_input
        model.eval()

        with torch.no_grad():
            output = model(input_ids, attention_mask)

        assert output["span_mask"].shape == (BATCH_SIZE, TRANSFORMER_SEQ_LEN, TRANSFORMER_SEQ_LEN)

    def test_span_mask_is_upper_triangular(self, model, span_input):
        """Test span mask only allows end >= start."""
        input_ids, attention_mask, _ = span_input
        model.eval()

        with torch.no_grad():
            output = model(input_ids, attention_mask)

        mask = output["span_mask"][0]
        # Check that positions where end < start are masked out
        for i in range(TRANSFORMER_SEQ_LEN):
            for j in range(i):
                assert mask[i, j].item() is False

    def test_span_mask_respects_max_width(self, model, span_input):
        """Test span mask enforces max_span_width constraint."""
        input_ids, attention_mask, _ = span_input
        model.eval()

        with torch.no_grad():
            output = model(input_ids, attention_mask)

        mask = output["span_mask"][0]
        # Spans wider than max_span_width should be masked out
        for i in range(TRANSFORMER_SEQ_LEN):
            for j in range(i + model.max_span_width, TRANSFORMER_SEQ_LEN):
                assert mask[i, j].item() is False

    def test_span_mask_respects_attention_mask(self, model):
        """Test span mask excludes padded positions."""
        input_ids = torch.randint(1, 1000, (2, 10))
        attention_mask = torch.ones(2, 10, dtype=torch.long)
        attention_mask[0, 7:] = 0  # padding from position 7

        model.eval()
        with torch.no_grad():
            output = model(input_ids, attention_mask)

        mask = output["span_mask"][0]
        # Spans starting or ending in padding should be masked
        assert mask[8, 9].item() is False
        assert mask[0, 8].item() is False

    def test_decode_method(self, model, span_input):
        """Test decode produces valid entity tuples."""
        input_ids, attention_mask, _ = span_input
        model.eval()

        with torch.no_grad():
            output = model(input_ids, attention_mask)

        predictions = model.decode(
            output["span_scores"],
            output["span_mask"],
            threshold=0.5,
        )

        assert isinstance(predictions, list)
        assert len(predictions) == BATCH_SIZE

        for batch_preds in predictions:
            assert isinstance(batch_preds, list)
            for pred in batch_preds:
                start, end, entity_type = pred
                assert isinstance(start, int)
                assert isinstance(end, int)
                assert isinstance(entity_type, int)
                assert end >= start
                assert entity_type >= 1  # 0 is non-entity

    def test_decode_threshold_filtering(self, model, span_input):
        """Test that higher threshold produces fewer predictions."""
        input_ids, attention_mask, _ = span_input
        model.eval()

        with torch.no_grad():
            output = model(input_ids, attention_mask)

        preds_low = model.decode(output["span_scores"], output["span_mask"], threshold=0.1)
        preds_high = model.decode(output["span_scores"], output["span_mask"], threshold=0.9)

        total_low = sum(len(p) for p in preds_low)
        total_high = sum(len(p) for p in preds_high)

        # Higher threshold should produce fewer or equal predictions
        assert total_high <= total_low

    def test_loss_is_finite_with_no_entities(self, model):
        """Test loss computation when span_labels are all zeros (no entities)."""
        input_ids = torch.randint(1, 1000, (2, 16))
        attention_mask = torch.ones(2, 16, dtype=torch.long)
        span_labels = torch.zeros(2, 16, 16, dtype=torch.long)

        output = model(input_ids, attention_mask, span_labels)
        assert torch.isfinite(output["loss"]).item()

    def test_gradient_flow(self, model, span_input):
        """Test gradients flow through entire model."""
        input_ids, attention_mask, span_labels = span_input
        output = model(input_ids, attention_mask, span_labels)
        output["loss"].backward()

        # Check FFN layers have gradients
        for param in model.start_ffn.parameters():
            if param.requires_grad:
                assert param.grad is not None

        for param in model.end_ffn.parameters():
            if param.requires_grad:
                assert param.grad is not None

    def test_different_max_span_widths(self):
        """Test model with different max_span_width settings."""
        for max_width in [5, 10, 30]:
            with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
                model = XLMR_Span_NER(
                    num_entity_types=NUM_ENTITY_TYPES,
                    max_span_width=max_width,
                    span_hidden_size=32,
                )

            input_ids = torch.randint(1, 1000, (2, 16))
            attention_mask = torch.ones(2, 16, dtype=torch.long)

            model.eval()
            with torch.no_grad():
                output = model(input_ids, attention_mask)

            assert output["span_scores"].shape[-1] == NUM_ENTITY_TYPES + 1
