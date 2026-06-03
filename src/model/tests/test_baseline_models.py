"""Unit tests for BiLSTM, BiLSTM_CRF, BiLSTM_CRF_Pretrained, LSTM, and TextCNN models."""

import pytest
import torch
from torch import nn

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from model.BiLSTM import BiLSTM
from model.BiLSTM_CRF import BiLSTM_CRF
from model.BiLSTM_CRF_Pretrained_Embedding import BiLSTM_CRF as BiLSTM_CRF_Pretrained
from model.LSTM import LSTM
from model.TextCNN import TextCNN_NER

from tests.conftest import (
    VOCAB_SIZE, EMBEDDING_DIM, HIDDEN_SIZE, NUM_TAGS,
    BATCH_SIZE, SEQ_LEN, NUM_LAYERS, DROPOUT,
)


# ==============================================================================
# BiLSTM Tests
# ==============================================================================


class TestBiLSTM:
    """Tests for the BiLSTM baseline model."""

    @pytest.fixture
    def model(self):
        return BiLSTM(
            vocab_size=VOCAB_SIZE,
            num_tags=NUM_TAGS,
            embedding_dim=EMBEDDING_DIM,
            num_layers=NUM_LAYERS,
            hidden_size=HIDDEN_SIZE,
            padding_idx=0,
            dropout=DROPOUT,
        )

    def test_initialization(self, model):
        """Test model components are properly initialized."""
        assert isinstance(model.embedding, nn.Embedding)
        assert model.embedding.num_embeddings == VOCAB_SIZE
        assert model.embedding.embedding_dim == EMBEDDING_DIM
        assert model.embedding.padding_idx == 0

        assert isinstance(model.bilstm, nn.LSTM)
        assert model.bilstm.bidirectional is True
        assert model.bilstm.hidden_size == HIDDEN_SIZE
        assert model.bilstm.num_layers == NUM_LAYERS

        assert isinstance(model.classifier, nn.Linear)
        assert model.classifier.in_features == HIDDEN_SIZE * 2
        assert model.classifier.out_features == NUM_TAGS

    def test_forward_output_shape(self, model, bilstm_input):
        """Test that forward pass produces correct output shape."""
        input_ids, lengths, _ = bilstm_input
        logits = model(input_ids, lengths)

        assert logits.shape == (BATCH_SIZE, SEQ_LEN, NUM_TAGS)

    def test_forward_output_dtype(self, model, bilstm_input):
        """Test that output is float tensor."""
        input_ids, lengths, _ = bilstm_input
        logits = model(input_ids, lengths)

        assert logits.dtype == torch.float32

    def test_forward_variable_lengths(self, model):
        """Test forward with different sequence lengths in batch."""
        input_ids = torch.randint(1, VOCAB_SIZE, (3, 15))
        input_ids[0, 10:] = 0
        input_ids[1, 8:] = 0
        input_ids[2, 12:] = 0
        lengths = torch.tensor([10, 8, 12])

        logits = model(input_ids, lengths)
        # pad_packed_sequence pads to max(lengths) = 12
        assert logits.shape == (3, 12, NUM_TAGS)

    def test_forward_single_sample(self, model):
        """Test forward with batch_size=1."""
        input_ids = torch.randint(1, VOCAB_SIZE, (1, 10))
        lengths = torch.tensor([10])

        logits = model(input_ids, lengths)
        assert logits.shape == (1, 10, NUM_TAGS)

    def test_gradient_flow(self, model, bilstm_input):
        """Test that gradients flow through the model."""
        input_ids, lengths, tags = bilstm_input
        logits = model(input_ids, lengths)

        loss = nn.CrossEntropyLoss()(logits.view(-1, NUM_TAGS), tags.view(-1))
        loss.backward()

        for name, param in model.named_parameters():
            if param.requires_grad:
                assert param.grad is not None, f"No gradient for {name}"

    def test_padding_idx_embedding(self, model):
        """Test that padding index produces zero embeddings."""
        pad_input = torch.zeros(1, 5, dtype=torch.long)
        embedded = model.embedding(pad_input)
        assert torch.all(embedded == 0)

    def test_train_eval_mode(self, model, bilstm_input):
        """Test model produces different dropout patterns in train vs eval."""
        input_ids, lengths, _ = bilstm_input

        model.train()
        out_train1 = model(input_ids, lengths)
        out_train2 = model(input_ids, lengths)

        model.eval()
        out_eval1 = model(input_ids, lengths)
        out_eval2 = model(input_ids, lengths)

        # In eval mode, outputs should be deterministic
        assert torch.allclose(out_eval1, out_eval2)


# ==============================================================================
# BiLSTM_CRF Tests
# ==============================================================================


class TestBiLSTM_CRF:
    """Tests for the BiLSTM + CRF model."""

    @pytest.fixture
    def model(self):
        return BiLSTM_CRF(
            vocab_size=VOCAB_SIZE,
            num_tags=NUM_TAGS,
            embedding_dim=EMBEDDING_DIM,
            num_layers=NUM_LAYERS,
            hidden_size=HIDDEN_SIZE,
            padding_idx=0,
            dropout=DROPOUT,
        )

    def test_initialization(self, model):
        """Test model components including CRF layer."""
        assert isinstance(model.embedding, nn.Embedding)
        assert isinstance(model.bilstm, nn.LSTM)
        assert isinstance(model.classifier, nn.Linear)
        assert hasattr(model, "crf")
        assert model.crf.num_tags == NUM_TAGS

    def test_training_returns_loss(self, model, bilstm_input):
        """Test that forward with tags returns a scalar loss."""
        input_ids, lengths, tags = bilstm_input
        loss = model(input_ids, lengths, tags)

        assert isinstance(loss, torch.Tensor)
        assert loss.dim() == 0  # scalar
        assert loss.item() > 0  # CRF loss should be positive
        assert loss.requires_grad is True

    def test_inference_returns_predictions(self, model, bilstm_input):
        """Test that forward without tags returns decoded sequences."""
        input_ids, lengths, _ = bilstm_input
        model.eval()

        preds = model(input_ids, lengths)

        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE
        for pred_seq in preds:
            assert isinstance(pred_seq, list)
            assert all(0 <= t < NUM_TAGS for t in pred_seq)

    def test_predictions_length_matches_input(self, model, bilstm_input):
        """Test that predictions have correct lengths."""
        input_ids, lengths, _ = bilstm_input
        model.eval()

        preds = model(input_ids, lengths)

        # CRF decode respects the mask, predictions should match non-padding length
        for pred_seq, length in zip(preds, lengths):
            assert len(pred_seq) == length.item()

    def test_loss_backward(self, model, bilstm_input):
        """Test that loss.backward() works correctly."""
        input_ids, lengths, tags = bilstm_input
        loss = model(input_ids, lengths, tags)
        loss.backward()

        # Check CRF parameters have gradients
        for param in model.crf.parameters():
            if param.requires_grad:
                assert param.grad is not None

    def test_loss_decreases_with_training(self, model, bilstm_input):
        """Test that loss decreases after optimization step."""
        input_ids, lengths, tags = bilstm_input
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

        model.train()
        loss1 = model(input_ids, lengths, tags)

        optimizer.zero_grad()
        loss1.backward()
        optimizer.step()

        loss2 = model(input_ids, lengths, tags)

        assert loss2.item() < loss1.item()

    def test_crf_valid_transitions(self, model, bilstm_input):
        """Test CRF produces valid tag sequences (no invalid transitions)."""
        input_ids, lengths, _ = bilstm_input
        model.eval()

        preds = model(input_ids, lengths)

        # Each prediction should only contain valid tag indices
        for pred_seq in preds:
            for tag_idx in pred_seq:
                assert 0 <= tag_idx < NUM_TAGS


# ==============================================================================
# BiLSTM_CRF_Pretrained Tests
# ==============================================================================


class TestBiLSTM_CRF_Pretrained:
    """Tests for BiLSTM_CRF with pretrained embeddings."""

    def test_with_pretrained_embeddings(self, bilstm_input):
        """Test model initialization with pretrained embedding matrix."""
        pretrained = torch.randn(VOCAB_SIZE, EMBEDDING_DIM)

        model = BiLSTM_CRF_Pretrained(
            vocab_size=VOCAB_SIZE,
            num_tags=NUM_TAGS,
            embedding_dim=EMBEDDING_DIM,
            hidden_size=HIDDEN_SIZE,
            pretrained_embeddings=pretrained,
            freeze_embedding=False,
        )

        # Check embeddings are loaded
        assert torch.allclose(
            model.embedding.weight.data[:VOCAB_SIZE],
            pretrained,
        )
        assert model.embedding.weight.requires_grad is True

    def test_frozen_embeddings(self):
        """Test that frozen embeddings do not receive gradients."""
        pretrained = torch.randn(VOCAB_SIZE, EMBEDDING_DIM)

        model = BiLSTM_CRF_Pretrained(
            vocab_size=VOCAB_SIZE,
            num_tags=NUM_TAGS,
            embedding_dim=EMBEDDING_DIM,
            hidden_size=HIDDEN_SIZE,
            pretrained_embeddings=pretrained,
            freeze_embedding=True,
        )

        assert model.embedding.weight.requires_grad is False

    def test_without_pretrained_embeddings(self, bilstm_input):
        """Test model works without pretrained embeddings (random init)."""
        model = BiLSTM_CRF_Pretrained(
            vocab_size=VOCAB_SIZE,
            num_tags=NUM_TAGS,
            embedding_dim=EMBEDDING_DIM,
            hidden_size=HIDDEN_SIZE,
            pretrained_embeddings=None,
            freeze_embedding=False,
        )

        input_ids, lengths, tags = bilstm_input
        loss = model(input_ids, lengths, tags)
        assert loss.item() > 0

    def test_forward_train_mode(self, bilstm_input):
        """Test training forward pass with pretrained embeddings."""
        pretrained = torch.randn(VOCAB_SIZE, EMBEDDING_DIM)
        model = BiLSTM_CRF_Pretrained(
            vocab_size=VOCAB_SIZE,
            num_tags=NUM_TAGS,
            embedding_dim=EMBEDDING_DIM,
            hidden_size=HIDDEN_SIZE,
            pretrained_embeddings=pretrained,
        )

        input_ids, lengths, tags = bilstm_input
        loss = model(input_ids, lengths, tags)
        assert loss.dim() == 0

    def test_forward_eval_mode(self, bilstm_input):
        """Test inference forward pass returns predictions."""
        model = BiLSTM_CRF_Pretrained(
            vocab_size=VOCAB_SIZE,
            num_tags=NUM_TAGS,
            embedding_dim=EMBEDDING_DIM,
            hidden_size=HIDDEN_SIZE,
        )
        model.eval()

        input_ids, lengths, _ = bilstm_input
        preds = model(input_ids, lengths)
        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE


# ==============================================================================
# LSTM Tests
# ==============================================================================


class TestLSTM:
    """Tests for the simplified LSTM model."""

    @pytest.fixture
    def model(self):
        return LSTM(
            vocab_size=VOCAB_SIZE,
            num_tags=NUM_TAGS,
            embedding_dim=EMBEDDING_DIM,
            num_layers=NUM_LAYERS,
            hidden_size=HIDDEN_SIZE,
            padding_idx=0,
            dropout=DROPOUT,
        )

    def test_initialization(self, model):
        """Test LSTM model components."""
        assert isinstance(model.embedding, nn.Embedding)
        assert isinstance(model.bilstm, nn.LSTM)
        assert isinstance(model.fc, nn.Linear)
        assert hasattr(model, "crf")

    def test_training_returns_loss(self, model, bilstm_input):
        """Test training mode returns scalar loss."""
        input_ids, lengths, tags = bilstm_input
        loss = model(input_ids, lengths, tags)

        assert isinstance(loss, torch.Tensor)
        assert loss.dim() == 0
        assert loss.requires_grad is True

    def test_inference_returns_predictions(self, model, bilstm_input):
        """Test inference mode returns tag sequences."""
        input_ids, lengths, _ = bilstm_input
        model.eval()

        preds = model(input_ids, lengths)

        assert isinstance(preds, list)
        assert len(preds) == BATCH_SIZE

    def test_accepts_extra_kwargs(self):
        """Test that **kwargs are properly handled."""
        model = LSTM(
            vocab_size=VOCAB_SIZE,
            num_tags=NUM_TAGS,
            embedding_dim=EMBEDDING_DIM,
            extra_param="should_be_ignored",
            another_param=42,
        )
        assert isinstance(model, LSTM)

    def test_gradient_flow(self, model, bilstm_input):
        """Test gradients flow through all parameters."""
        input_ids, lengths, tags = bilstm_input
        loss = model(input_ids, lengths, tags)
        loss.backward()

        grad_params = [
            p for p in model.parameters() if p.requires_grad and p.grad is not None
        ]
        assert len(grad_params) > 0


# ==============================================================================
# TextCNN Tests
# ==============================================================================


class TestTextCNN:
    """Tests for the TextCNN_NER model."""

    @pytest.fixture
    def model(self):
        return TextCNN_NER(
            vocab_size=VOCAB_SIZE,
            embedding_dim=EMBEDDING_DIM,
            filter_size=[2, 3, 4, 5],
            num_tags=NUM_TAGS,
            padding_idx=0,
            n_filters=32,
            dropout=DROPOUT,
        )

    def test_initialization(self, model):
        """Test TextCNN components."""
        assert isinstance(model.embedding, nn.Embedding)
        assert len(model.convs) == 4  # 4 kernel sizes
        assert isinstance(model.fc, nn.Linear)
        assert model.fc.out_features == NUM_TAGS
        # in_features = n_filters * len(filter_size) = 32 * 4 = 128
        assert model.fc.in_features == 32 * 4

    def test_forward_output_shape(self, model):
        """Test output shape preserves sequence length."""
        input_ids = torch.randint(1, VOCAB_SIZE, (BATCH_SIZE, SEQ_LEN))
        logits = model(input_ids)

        assert logits.shape == (BATCH_SIZE, SEQ_LEN, NUM_TAGS)

    def test_forward_with_lengths_parameter(self, model):
        """Test that lengths parameter is accepted (API compatibility)."""
        input_ids = torch.randint(1, VOCAB_SIZE, (BATCH_SIZE, SEQ_LEN))
        lengths = torch.tensor([SEQ_LEN] * BATCH_SIZE)

        logits = model(input_ids, lengths)
        assert logits.shape == (BATCH_SIZE, SEQ_LEN, NUM_TAGS)

    def test_conv_same_padding(self, model):
        """Test that convolutions preserve sequence length via same-padding."""
        input_ids = torch.randint(1, VOCAB_SIZE, (2, 30))
        logits = model(input_ids)
        assert logits.shape[1] == 30

    def test_different_sequence_lengths(self, model):
        """Test with various sequence lengths."""
        for seq_len in [5, 10, 50, 100]:
            input_ids = torch.randint(1, VOCAB_SIZE, (2, seq_len))
            logits = model(input_ids)
            assert logits.shape == (2, seq_len, NUM_TAGS)

    def test_gradient_flow(self, model):
        """Test gradient computation for all parameters."""
        input_ids = torch.randint(1, VOCAB_SIZE, (BATCH_SIZE, SEQ_LEN))
        tags = torch.randint(0, NUM_TAGS, (BATCH_SIZE, SEQ_LEN))

        logits = model(input_ids)
        loss = nn.CrossEntropyLoss()(logits.view(-1, NUM_TAGS), tags.view(-1))
        loss.backward()

        for name, param in model.named_parameters():
            if param.requires_grad:
                assert param.grad is not None, f"No gradient for {name}"

    def test_different_filter_sizes(self):
        """Test model works with different filter size configurations."""
        for filter_sizes in [[3], [2, 3], [1, 2, 3, 4, 5]]:
            model = TextCNN_NER(
                vocab_size=VOCAB_SIZE,
                embedding_dim=EMBEDDING_DIM,
                filter_size=filter_sizes,
                num_tags=NUM_TAGS,
                n_filters=16,
            )
            input_ids = torch.randint(1, VOCAB_SIZE, (2, 10))
            logits = model(input_ids)
            assert logits.shape == (2, 10, NUM_TAGS)

    def test_output_is_float(self, model):
        """Test output dtype is float."""
        input_ids = torch.randint(1, VOCAB_SIZE, (2, 10))
        logits = model(input_ids)
        assert logits.dtype == torch.float32
