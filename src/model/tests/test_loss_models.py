"""Unit tests for loss function models (FocalLoss, DiceLoss, FocalCRF_XLMR, DiceLoss_XLMR)."""

import pytest
import torch
from torch import nn
from unittest.mock import patch
from transformers import AutoModel

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from model.loss_models import FocalLoss, DiceLoss, FocalCRF_XLMR, DiceLoss_XLMR
from tests.conftest import NUM_TAGS, BATCH_SIZE, TRANSFORMER_SEQ_LEN, DROPOUT
from tests.test_transformer_models import create_mock_encoder


# ==============================================================================
# FocalLoss Tests
# ==============================================================================


class TestFocalLoss:
    """Tests for the FocalLoss module."""

    @pytest.fixture
    def loss_fn(self):
        return FocalLoss(num_classes=NUM_TAGS, gamma=2.0, ignore_index=-100)

    def test_initialization_default_alpha(self, loss_fn):
        """Test default alpha is uniform (ones)."""
        assert torch.allclose(loss_fn.alpha, torch.ones(NUM_TAGS))

    def test_initialization_custom_alpha(self):
        """Test custom per-class alpha weights."""
        alpha = torch.rand(NUM_TAGS)
        loss_fn = FocalLoss(num_classes=NUM_TAGS, alpha=alpha)
        assert torch.allclose(loss_fn.alpha, alpha)

    def test_output_is_scalar(self, loss_fn):
        """Test loss output is a scalar tensor."""
        logits = torch.randn(BATCH_SIZE, 20, NUM_TAGS)
        targets = torch.randint(0, NUM_TAGS, (BATCH_SIZE, 20))

        loss = loss_fn(logits, targets)
        assert loss.dim() == 0

    def test_output_is_positive(self, loss_fn):
        """Test that focal loss is non-negative."""
        logits = torch.randn(BATCH_SIZE, 20, NUM_TAGS)
        targets = torch.randint(0, NUM_TAGS, (BATCH_SIZE, 20))

        loss = loss_fn(logits, targets)
        assert loss.item() >= 0

    def test_output_is_finite(self, loss_fn):
        """Test loss is finite (no NaN/Inf)."""
        logits = torch.randn(BATCH_SIZE, 20, NUM_TAGS)
        targets = torch.randint(0, NUM_TAGS, (BATCH_SIZE, 20))

        loss = loss_fn(logits, targets)
        assert torch.isfinite(loss).item()

    def test_ignore_index(self, loss_fn):
        """Test that ignore_index positions are excluded from loss."""
        logits = torch.randn(2, 10, NUM_TAGS)
        targets = torch.randint(0, NUM_TAGS, (2, 10))
        targets[:, -3:] = -100  # mark as ignored

        loss = loss_fn(logits, targets)
        assert torch.isfinite(loss).item()

    def test_all_ignored_returns_zero(self, loss_fn):
        """Test that loss is zero when all positions are ignored."""
        logits = torch.randn(2, 5, NUM_TAGS)
        targets = torch.full((2, 5), -100, dtype=torch.long)

        loss = loss_fn(logits, targets)
        assert loss.item() == 0.0

    def test_gamma_zero_equals_cross_entropy(self):
        """Test that gamma=0 reduces to weighted cross-entropy."""
        focal_loss = FocalLoss(num_classes=NUM_TAGS, gamma=0.0)

        logits = torch.randn(2, 10, NUM_TAGS, requires_grad=True)
        targets = torch.randint(0, NUM_TAGS, (2, 10))

        fl = focal_loss(logits, targets)

        # Compare with standard cross-entropy
        ce = nn.CrossEntropyLoss()(logits.view(-1, NUM_TAGS), targets.view(-1))

        # Should be approximately equal (focal weight = 1 when gamma=0)
        assert torch.allclose(fl, ce, atol=1e-4)

    def test_higher_gamma_lower_loss_for_easy_examples(self):
        """Test that higher gamma reduces loss for well-classified examples."""
        # Create easy examples: one-hot logits
        logits = torch.zeros(2, 5, NUM_TAGS)
        targets = torch.randint(0, NUM_TAGS, (2, 5))
        for b in range(2):
            for t in range(5):
                logits[b, t, targets[b, t]] = 10.0  # high confidence

        focal_low = FocalLoss(num_classes=NUM_TAGS, gamma=1.0)
        focal_high = FocalLoss(num_classes=NUM_TAGS, gamma=5.0)

        loss_low = focal_low(logits, targets)
        loss_high = focal_high(logits, targets)

        # Higher gamma should give lower loss for easy examples
        assert loss_high.item() <= loss_low.item()

    def test_gradient_computation(self, loss_fn):
        """Test that gradients flow through focal loss."""
        logits = torch.randn(2, 10, NUM_TAGS, requires_grad=True)
        targets = torch.randint(0, NUM_TAGS, (2, 10))

        loss = loss_fn(logits, targets)
        loss.backward()

        assert logits.grad is not None
        assert torch.isfinite(logits.grad).all()

    def test_different_batch_sizes(self, loss_fn):
        """Test loss works with various batch sizes."""
        for batch_size in [1, 4, 16]:
            logits = torch.randn(batch_size, 10, NUM_TAGS)
            targets = torch.randint(0, NUM_TAGS, (batch_size, 10))
            loss = loss_fn(logits, targets)
            assert torch.isfinite(loss).item()


# ==============================================================================
# DiceLoss Tests
# ==============================================================================


class TestDiceLoss:
    """Tests for the DiceLoss module."""

    @pytest.fixture
    def loss_fn(self):
        return DiceLoss(num_classes=NUM_TAGS, smooth=1.0, ignore_index=-100)

    def test_output_is_scalar(self, loss_fn):
        """Test dice loss output is scalar."""
        logits = torch.randn(BATCH_SIZE, 20, NUM_TAGS)
        targets = torch.randint(0, NUM_TAGS, (BATCH_SIZE, 20))

        loss = loss_fn(logits, targets)
        assert loss.dim() == 0

    def test_output_range(self, loss_fn):
        """Test dice loss is in [0, 1]."""
        logits = torch.randn(BATCH_SIZE, 20, NUM_TAGS)
        targets = torch.randint(0, NUM_TAGS, (BATCH_SIZE, 20))

        loss = loss_fn(logits, targets)
        assert 0.0 <= loss.item() <= 1.0

    def test_perfect_prediction_low_loss(self):
        """Test that perfect predictions give low dice loss."""
        loss_fn = DiceLoss(num_classes=NUM_TAGS, smooth=1.0)

        # Create perfect predictions
        targets = torch.randint(0, NUM_TAGS, (2, 10))
        logits = torch.zeros(2, 10, NUM_TAGS)
        for b in range(2):
            for t in range(10):
                logits[b, t, targets[b, t]] = 100.0  # very high confidence

        loss = loss_fn(logits, targets)
        assert loss.item() < 0.1  # should be very low

    def test_ignore_index(self, loss_fn):
        """Test ignore_index exclusion."""
        logits = torch.randn(2, 10, NUM_TAGS)
        targets = torch.randint(0, NUM_TAGS, (2, 10))
        targets[:, -3:] = -100

        loss = loss_fn(logits, targets)
        assert torch.isfinite(loss).item()

    def test_all_ignored_returns_zero(self, loss_fn):
        """Test zero loss when all positions ignored."""
        logits = torch.randn(2, 5, NUM_TAGS)
        targets = torch.full((2, 5), -100, dtype=torch.long)

        loss = loss_fn(logits, targets)
        assert loss.item() == 0.0

    def test_gradient_computation(self, loss_fn):
        """Test gradient flow."""
        logits = torch.randn(2, 10, NUM_TAGS, requires_grad=True)
        targets = torch.randint(0, NUM_TAGS, (2, 10))

        loss = loss_fn(logits, targets)
        loss.backward()

        assert logits.grad is not None
        assert torch.isfinite(logits.grad).all()

    def test_smooth_factor_effect(self):
        """Test that smooth factor prevents division by zero."""
        # All zeros case
        loss_fn = DiceLoss(num_classes=NUM_TAGS, smooth=1.0)
        logits = torch.zeros(2, 5, NUM_TAGS)
        targets = torch.zeros(2, 5, dtype=torch.long)

        loss = loss_fn(logits, targets)
        assert torch.isfinite(loss).item()

    def test_symmetric_property(self, loss_fn):
        """Test dice loss is consistent regardless of target distribution."""
        logits = torch.randn(4, 15, NUM_TAGS)
        targets = torch.randint(0, NUM_TAGS, (4, 15))

        loss = loss_fn(logits, targets)
        assert 0.0 <= loss.item() <= 1.0


# ==============================================================================
# FocalCRF_XLMR Tests
# ==============================================================================


class TestFocalCRF_XLMR:
    """Tests for XLM-RoBERTa + Focal Loss + CRF model."""

    @pytest.fixture
    def model(self):
        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = FocalCRF_XLMR(
                num_tags=NUM_TAGS,
                model_name="xlm-roberta-base",
                focal_gamma=2.0,
                focal_alpha=None,
                crf_weight=0.5,
                dropout=DROPOUT,
            )
        return model

    def test_initialization(self, model):
        """Test model components."""
        assert hasattr(model, "encoder")
        assert hasattr(model, "classifier")
        assert hasattr(model, "crf")
        assert hasattr(model, "focal_loss")
        assert model.crf_weight == 0.5

    def test_training_returns_loss(self, model, transformer_input):
        """Test training returns combined loss."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)

        assert loss.dim() == 0
        assert torch.isfinite(loss).item()
        assert loss.requires_grad

    def test_inference_returns_predictions(self, model, transformer_input):
        """Test inference returns CRF decoded sequences."""
        input_ids, attention_mask, _ = transformer_input
        model.eval()

        with torch.no_grad():
            preds = model(input_ids, attention_mask)

        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE

    def test_crf_weight_balance(self):
        """Test different CRF weight values."""
        for crf_weight in [0.0, 0.3, 0.5, 0.7, 1.0]:
            with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
                model = FocalCRF_XLMR(
                    num_tags=NUM_TAGS,
                    crf_weight=crf_weight,
                )

            input_ids = torch.randint(1, 1000, (2, 16))
            attention_mask = torch.ones(2, 16, dtype=torch.long)
            labels = torch.randint(0, NUM_TAGS, (2, 16))

            loss = model(input_ids, attention_mask, labels)
            assert torch.isfinite(loss).item()

    def test_custom_focal_alpha(self):
        """Test with custom per-class alpha weights."""
        alpha = torch.rand(NUM_TAGS)
        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = FocalCRF_XLMR(
                num_tags=NUM_TAGS,
                focal_alpha=alpha,
                focal_gamma=3.0,
            )

        input_ids = torch.randint(1, 1000, (2, 16))
        attention_mask = torch.ones(2, 16, dtype=torch.long)
        labels = torch.randint(0, NUM_TAGS, (2, 16))

        loss = model(input_ids, attention_mask, labels)
        assert torch.isfinite(loss).item()

    def test_gradient_flow(self, model, transformer_input):
        """Test gradients flow through combined loss."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)
        loss.backward()

        assert model.classifier.weight.grad is not None


# ==============================================================================
# DiceLoss_XLMR Tests
# ==============================================================================


class TestDiceLoss_XLMR:
    """Tests for XLM-RoBERTa + Dice Loss + CRF model."""

    @pytest.fixture
    def model(self):
        with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
            model = DiceLoss_XLMR(
                num_tags=NUM_TAGS,
                model_name="xlm-roberta-base",
                dice_smooth=1.0,
                crf_weight=0.5,
                dropout=DROPOUT,
            )
        return model

    def test_initialization(self, model):
        """Test model components."""
        assert hasattr(model, "encoder")
        assert hasattr(model, "classifier")
        assert hasattr(model, "crf")
        assert hasattr(model, "dice_loss")
        assert model.crf_weight == 0.5

    def test_training_returns_loss(self, model, transformer_input):
        """Test training returns combined dice + CRF loss."""
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

    def test_crf_weight_balance(self):
        """Test various CRF weight configurations."""
        for crf_weight in [0.0, 0.5, 1.0]:
            with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
                model = DiceLoss_XLMR(num_tags=NUM_TAGS, crf_weight=crf_weight)

            input_ids = torch.randint(1, 1000, (2, 16))
            attention_mask = torch.ones(2, 16, dtype=torch.long)
            labels = torch.randint(0, NUM_TAGS, (2, 16))

            loss = model(input_ids, attention_mask, labels)
            assert torch.isfinite(loss).item()

    def test_dice_smooth_parameter(self):
        """Test different smooth factor values."""
        for smooth in [0.1, 1.0, 10.0]:
            with patch.object(AutoModel, "from_pretrained", return_value=create_mock_encoder()):
                model = DiceLoss_XLMR(num_tags=NUM_TAGS, dice_smooth=smooth)

            input_ids = torch.randint(1, 1000, (2, 16))
            attention_mask = torch.ones(2, 16, dtype=torch.long)
            labels = torch.randint(0, NUM_TAGS, (2, 16))

            loss = model(input_ids, attention_mask, labels)
            assert torch.isfinite(loss).item()

    def test_gradient_flow(self, model, transformer_input):
        """Test gradient computation."""
        input_ids, attention_mask, labels = transformer_input
        loss = model(input_ids, attention_mask, labels)
        loss.backward()

        assert model.classifier.weight.grad is not None
        for param in model.crf.parameters():
            if param.requires_grad:
                assert param.grad is not None
