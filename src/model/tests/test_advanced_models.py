"""Unit tests for advanced NER architectures.

Tests for:
- XLMR_BiLSTM_CRF (Transformer + BiLSTM + CRF hybrid)
- XLMR_MultiHead_Attn_CRF (Transformer + NER-specific attention + CRF)
- XLMR_Adaptive_Fusion_CRF (Transformer + Adaptive Layer Fusion + CRF)
"""

import pytest
import torch
from torch import nn
from unittest.mock import patch
from transformers import AutoModel, AutoConfig

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import NUM_TAGS, BATCH_SIZE, TRANSFORMER_SEQ_LEN, DROPOUT
from tests.test_transformer_models import create_mock_encoder


# ==============================================================================
# Helper: encoder with hidden_states output
# ==============================================================================

def create_mock_encoder_with_hidden_states(hidden_size=64, num_hidden_layers=4):
    """Create encoder that also returns all hidden states (for Adaptive Fusion)."""
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
            hidden = torch.randn(batch_size, seq_len, hidden_size)
            # Generate all hidden states (embedding + each layer)
            all_hidden = tuple(
                torch.randn(batch_size, seq_len, hidden_size)
                for _ in range(num_hidden_layers + 1)
            )
            output = type("Output", (), {
                "last_hidden_state": hidden,
                "hidden_states": all_hidden,
            })()
            return output

        def parameters(self):
            return iter([self.linear.weight, self.linear.bias])

    return FakeEncoder()


# ==============================================================================
# XLMR_BiLSTM_CRF Tests
# ==============================================================================


class TestXLMR_BiLSTM_CRF:
    """Tests for XLM-RoBERTa + BiLSTM + CRF hybrid model."""

    @pytest.fixture
    def model(self):
        from model.XLMR_BiLSTM_CRF import XLMR_BiLSTM_CRF

        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = XLMR_BiLSTM_CRF(
                num_tags=NUM_TAGS,
                model_name="xlm-roberta-base",
                lstm_hidden_size=32,
                lstm_num_layers=1,
                dropout=DROPOUT,
                freeze_encoder=False,
            )
        return model

    def test_initialization(self, model):
        """Test hybrid model components."""
        assert hasattr(model, "encoder")
        assert hasattr(model, "bilstm")
        assert hasattr(model, "classifier")
        assert hasattr(model, "crf")
        assert model.crf.num_tags == NUM_TAGS

    def test_bilstm_is_bidirectional(self, model):
        """Test that BiLSTM layer is bidirectional."""
        assert model.bilstm.bidirectional is True

    def test_classifier_input_size(self, model):
        """Test classifier matches BiLSTM output (2 * hidden_size)."""
        assert model.classifier.in_features == 32 * 2  # bidirectional

    def test_training_returns_loss(self, model, transformer_input):
        """Test training forward pass returns scalar loss."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)

        assert loss.dim() == 0
        assert loss.item() > 0
        assert torch.isfinite(loss).item()

    def test_inference_returns_predictions(self, model, transformer_input):
        """Test inference returns decoded tag sequences."""
        input_ids, attention_mask, _ = transformer_input
        model.eval()

        with torch.no_grad():
            preds = model(input_ids, attention_mask)

        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE
        for seq in preds:
            assert all(0 <= t < NUM_TAGS for t in seq)

    def test_predictions_respect_mask(self, model, transformer_input):
        """Test prediction lengths match valid positions."""
        input_ids, attention_mask, _ = transformer_input
        model.eval()

        with torch.no_grad():
            preds = model(input_ids, attention_mask)

        for pred, mask in zip(preds, attention_mask):
            assert len(pred) == mask.sum().item()

    def test_freeze_encoder(self):
        """Test encoder freezing behavior."""
        from model.XLMR_BiLSTM_CRF import XLMR_BiLSTM_CRF

        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = XLMR_BiLSTM_CRF(
                num_tags=NUM_TAGS,
                freeze_encoder=True,
            )

        for param in model.encoder.parameters():
            assert param.requires_grad is False

        # BiLSTM and classifier should still be trainable
        for param in model.bilstm.parameters():
            assert param.requires_grad is True

    def test_gradient_flow_to_bilstm(self, model, transformer_input):
        """Test gradients reach BiLSTM layer."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)
        loss.backward()

        for param in model.bilstm.parameters():
            if param.requires_grad:
                assert param.grad is not None

    def test_different_lstm_configs(self, transformer_input):
        """Test various BiLSTM configurations."""
        from model.XLMR_BiLSTM_CRF import XLMR_BiLSTM_CRF

        for lstm_hidden, lstm_layers in [(64, 1), (128, 2), (256, 3)]:
            with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
                model = XLMR_BiLSTM_CRF(
                    num_tags=NUM_TAGS,
                    lstm_hidden_size=lstm_hidden,
                    lstm_num_layers=lstm_layers,
                )

            input_ids, attention_mask, labels = transformer_input
            loss = model(input_ids, attention_mask, labels)
            assert torch.isfinite(loss).item()


# ==============================================================================
# XLMR_MultiHead_Attn_CRF Tests
# ==============================================================================


class TestXLMR_MultiHead_Attn_CRF:
    """Tests for XLM-RoBERTa + Multi-Head NER Attention + CRF."""

    @pytest.fixture
    def model(self):
        from model.XLMR_MultiHead_Attn_CRF import XLMR_MultiHead_Attn_CRF

        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = XLMR_MultiHead_Attn_CRF(
                num_tags=NUM_TAGS,
                model_name="xlm-roberta-base",
                num_attn_heads=4,  # 64 / 4 = 16 head_dim
                attn_dropout=0.1,
                classifier_dropout=DROPOUT,
                freeze_encoder=False,
            )
        return model

    def test_initialization(self, model):
        """Test model has attention and CRF components."""
        assert hasattr(model, "encoder")
        assert hasattr(model, "ner_attention")
        assert hasattr(model, "classifier")
        assert hasattr(model, "crf")

    def test_training_returns_loss(self, model, transformer_input):
        """Test training returns scalar loss."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)

        assert loss.dim() == 0
        assert torch.isfinite(loss).item()

    def test_inference_returns_predictions(self, model, transformer_input):
        """Test inference returns predictions."""
        input_ids, attention_mask, _ = transformer_input
        model.eval()

        with torch.no_grad():
            preds = model(input_ids, attention_mask)

        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE

    def test_attention_preserves_shape(self):
        """Test that NER attention does not change hidden state dimensions."""
        from model.XLMR_MultiHead_Attn_CRF import NERMultiHeadAttention

        hidden_size = 64
        attn = NERMultiHeadAttention(
            hidden_size=hidden_size,
            num_heads=4,
            dropout=0.1,
        )

        hidden = torch.randn(BATCH_SIZE, TRANSFORMER_SEQ_LEN, hidden_size)
        mask = torch.ones(BATCH_SIZE, TRANSFORMER_SEQ_LEN, dtype=torch.long)

        output = attn(hidden, mask)
        assert output.shape == hidden.shape

    def test_attention_with_padding_mask(self):
        """Test attention properly handles padding mask."""
        from model.XLMR_MultiHead_Attn_CRF import NERMultiHeadAttention

        hidden_size = 64
        attn = NERMultiHeadAttention(
            hidden_size=hidden_size,
            num_heads=4,
            dropout=0.1,
        )

        hidden = torch.randn(2, 10, hidden_size)
        mask = torch.ones(2, 10, dtype=torch.long)
        mask[0, 7:] = 0  # padding for first sample
        mask[1, 5:] = 0

        output = attn(hidden, mask)
        assert output.shape == (2, 10, hidden_size)

    def test_relative_position_encoding(self):
        """Test RelativePositionEncoding module."""
        from model.XLMR_MultiHead_Attn_CRF import RelativePositionEncoding

        rpe = RelativePositionEncoding(max_relative_position=32, num_heads=4)
        seq_len = 16
        bias = rpe(seq_len)

        # Shape: (1, num_heads, seq_len, seq_len)
        assert bias.shape == (1, 4, seq_len, seq_len)

    def test_gradient_flow_through_attention(self, model, transformer_input):
        """Test gradients flow through attention layer."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)
        loss.backward()

        # Check attention parameters have gradients
        for name, param in model.ner_attention.named_parameters():
            if param.requires_grad:
                assert param.grad is not None, f"No gradient for attention.{name}"


# ==============================================================================
# XLMR_Adaptive_Fusion_CRF Tests
# ==============================================================================


class TestXLMR_Adaptive_Fusion_CRF:
    """Tests for XLM-RoBERTa + Adaptive Layer Fusion + CRF."""

    @pytest.fixture
    def model(self):
        from model.XLMR_Adaptive_Fusion_CRF import XLMR_Adaptive_Fusion_CRF

        encoder = create_mock_encoder_with_hidden_states(hidden_size=64, num_hidden_layers=4)

        with patch.object(AutoModel, "from_pretrained", return_value=encoder):
            with patch.object(AutoConfig, "from_pretrained", return_value=type("Config", (), {
                "hidden_size": 64,
                "num_hidden_layers": 4,
            })()):
                model = XLMR_Adaptive_Fusion_CRF(
                    num_tags=NUM_TAGS,
                    model_name="xlm-roberta-base",
                    dropout=DROPOUT,
                    freeze_encoder=False,
                )
        return model

    def test_initialization(self, model):
        """Test model has fusion and CRF components."""
        assert hasattr(model, "encoder")
        assert hasattr(model, "layer_fusion")
        assert hasattr(model, "classifier")
        assert hasattr(model, "crf")

    def test_adaptive_fusion_module(self):
        """Test AdaptiveLayerFusion standalone."""
        from model.XLMR_Adaptive_Fusion_CRF import AdaptiveLayerFusion

        num_layers = 6
        hidden_size = 64
        fusion = AdaptiveLayerFusion(num_layers=num_layers, hidden_size=hidden_size)

        # Simulate hidden states from transformer (skip embedding at index 0)
        all_hidden = tuple(
            torch.randn(BATCH_SIZE, TRANSFORMER_SEQ_LEN, hidden_size)
            for _ in range(num_layers + 1)  # embedding + num_layers
        )

        output = fusion(all_hidden)
        assert output.shape == (BATCH_SIZE, TRANSFORMER_SEQ_LEN, hidden_size)

    def test_fusion_weights_sum_to_one(self):
        """Test that softmax-normalized layer weights sum to 1."""
        from model.XLMR_Adaptive_Fusion_CRF import AdaptiveLayerFusion

        fusion = AdaptiveLayerFusion(num_layers=6, hidden_size=64)
        weights = torch.softmax(fusion.layer_weights, dim=0)
        assert torch.allclose(weights.sum(), torch.tensor(1.0), atol=1e-6)

    def test_fusion_gamma_parameter(self):
        """Test gamma scaling parameter exists and is learnable."""
        from model.XLMR_Adaptive_Fusion_CRF import AdaptiveLayerFusion

        fusion = AdaptiveLayerFusion(num_layers=6, hidden_size=64)
        assert hasattr(fusion, "gamma")
        assert fusion.gamma.requires_grad is True
        assert fusion.gamma.item() == 1.0  # initialized to 1

    def test_training_returns_loss(self, model, transformer_input):
        """Test training forward pass."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)

        assert loss.dim() == 0
        assert torch.isfinite(loss).item()

    def test_inference_returns_predictions(self, model, transformer_input):
        """Test inference returns decoded sequences."""
        input_ids, attention_mask, _ = transformer_input
        model.eval()

        with torch.no_grad():
            preds = model(input_ids, attention_mask)

        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE

    def test_gradient_flow_to_fusion(self, model, transformer_input):
        """Test gradients reach fusion layer weights."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)
        loss.backward()

        assert model.layer_fusion.layer_weights.grad is not None
        assert model.layer_fusion.gamma.grad is not None

    def test_different_num_layers(self):
        """Test fusion with various layer counts."""
        from model.XLMR_Adaptive_Fusion_CRF import AdaptiveLayerFusion

        for num_layers in [1, 4, 12, 24]:
            fusion = AdaptiveLayerFusion(num_layers=num_layers, hidden_size=64)
            all_hidden = tuple(
                torch.randn(2, 10, 64) for _ in range(num_layers + 1)
            )
            output = fusion(all_hidden)
            assert output.shape == (2, 10, 64)

    def test_layer_norm_in_fusion(self):
        """Test LayerNorm is applied in fusion output."""
        from model.XLMR_Adaptive_Fusion_CRF import AdaptiveLayerFusion

        fusion = AdaptiveLayerFusion(num_layers=4, hidden_size=64)
        assert hasattr(fusion, "layer_norm")
        assert isinstance(fusion.layer_norm, nn.LayerNorm)
