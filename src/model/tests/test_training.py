"""Unit tests for training utility functions.

Tests for:
- train_advanced.py: read_jsonl, build_label_vocab, get_device, compute_class_weights
- Model registry validation
"""

import pytest
import json
import torch
from unittest.mock import patch

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ==============================================================================
# read_jsonl Tests
# ==============================================================================


class TestReadJsonl:
    """Tests for the read_jsonl utility."""

    def test_reads_valid_jsonl(self, tmp_path):
        """Test reading a valid JSONL file."""
        from training.train_advanced import read_jsonl

        filepath = tmp_path / "data.jsonl"
        records = [
            {"tokens": ["A", "B"], "tags": ["O", "B-ORG"]},
            {"tokens": ["C"], "tags": ["O"]},
        ]
        with open(filepath, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        result = read_jsonl(str(filepath))
        assert len(result) == 2
        assert result[0]["tokens"] == ["A", "B"]

    def test_skips_empty_lines(self, tmp_path):
        """Test that empty lines are skipped."""
        from training.train_advanced import read_jsonl

        filepath = tmp_path / "data.jsonl"
        with open(filepath, "w") as f:
            f.write('{"tokens": ["A"], "tags": ["O"]}\n')
            f.write("\n")
            f.write("\n")
            f.write('{"tokens": ["B"], "tags": ["O"]}\n')

        result = read_jsonl(str(filepath))
        assert len(result) == 2

    def test_empty_file(self, tmp_path):
        """Test reading empty file returns empty list."""
        from training.train_advanced import read_jsonl

        filepath = tmp_path / "empty.jsonl"
        filepath.write_text("")

        result = read_jsonl(str(filepath))
        assert result == []


# ==============================================================================
# build_label_vocab Tests
# ==============================================================================


class TestBuildLabelVocab:
    """Tests for the build_label_vocab function."""

    def test_builds_from_training_data(self):
        """Test label vocab is correctly built."""
        from training.train_advanced import build_label_vocab

        train_data = [
            {"tokens": ["A"], "tags": ["O"]},
            {"tokens": ["B", "C"], "tags": ["B-ORG", "I-ORG"]},
            {"tokens": ["D"], "tags": ["B-PERSON"]},
        ]

        label2id = build_label_vocab(train_data)

        assert "O" in label2id
        assert "B-ORG" in label2id
        assert "I-ORG" in label2id
        assert "B-PERSON" in label2id
        assert len(label2id) == 4

    def test_ids_are_sequential(self):
        """Test IDs are 0-indexed and sequential."""
        from training.train_advanced import build_label_vocab

        train_data = [
            {"tokens": ["A", "B", "C"], "tags": ["O", "B-ORG", "I-ORG"]},
        ]

        label2id = build_label_vocab(train_data)

        ids = sorted(label2id.values())
        assert ids == list(range(len(label2id)))

    def test_sorted_labels(self):
        """Test labels are sorted alphabetically."""
        from training.train_advanced import build_label_vocab

        train_data = [
            {"tokens": ["A", "B", "C"], "tags": ["O", "B-ORG", "B-ASSET"]},
        ]

        label2id = build_label_vocab(train_data)
        labels_by_id = sorted(label2id.keys(), key=lambda k: label2id[k])

        assert labels_by_id == sorted(labels_by_id)

    def test_empty_data(self):
        """Test with no data returns empty vocab."""
        from training.train_advanced import build_label_vocab

        label2id = build_label_vocab([])
        assert label2id == {}

    def test_single_tag(self):
        """Test with only one tag."""
        from training.train_advanced import build_label_vocab

        train_data = [{"tokens": ["A"], "tags": ["O"]}]
        label2id = build_label_vocab(train_data)
        assert label2id == {"O": 0}


# ==============================================================================
# get_device Tests
# ==============================================================================


class TestGetDevice:
    """Tests for device detection."""

    def test_returns_torch_device(self):
        """Test that get_device returns a torch.device."""
        from training.train_advanced import get_device

        device = get_device()
        assert isinstance(device, torch.device)

    def test_device_is_valid(self):
        """Test returned device is one of cuda/mps/cpu."""
        from training.train_advanced import get_device

        device = get_device()
        assert device.type in ("cuda", "mps", "cpu")


# ==============================================================================
# compute_class_weights Tests
# ==============================================================================


class TestComputeClassWeights:
    """Tests for inverse-frequency class weight computation."""

    def test_output_shape(self):
        """Test output has correct number of classes."""
        from training.train_advanced import compute_class_weights

        train_data = [
            {"tags": ["O", "O", "B-ORG", "I-ORG", "O"]},
            {"tags": ["O", "B-PERSON", "O"]},
        ]
        label2id = {"O": 0, "B-ORG": 1, "I-ORG": 2, "B-PERSON": 3}
        device = torch.device("cpu")

        weights = compute_class_weights(train_data, label2id, device)
        assert weights.shape == (4,)

    def test_weights_are_positive(self):
        """Test all weights are positive."""
        from training.train_advanced import compute_class_weights

        train_data = [{"tags": ["O", "B-ORG", "O", "O"]}]
        label2id = {"O": 0, "B-ORG": 1}
        device = torch.device("cpu")

        weights = compute_class_weights(train_data, label2id, device)
        assert (weights > 0).all()

    def test_rare_class_higher_weight(self):
        """Test that rare classes get higher weights."""
        from training.train_advanced import compute_class_weights

        train_data = [
            {"tags": ["O", "O", "O", "O", "O", "O", "O", "O", "B-ORG", "O"]},
        ]
        label2id = {"O": 0, "B-ORG": 1}
        device = torch.device("cpu")

        weights = compute_class_weights(train_data, label2id, device)
        # B-ORG is much rarer so should have higher weight
        assert weights[1] > weights[0]

    def test_weights_normalize(self):
        """Test that weights are normalized (sum to num_classes)."""
        from training.train_advanced import compute_class_weights

        train_data = [
            {"tags": ["O", "O", "B-ORG", "I-ORG"]},
            {"tags": ["O", "B-DATE", "I-DATE", "O"]},
        ]
        label2id = {"O": 0, "B-ORG": 1, "I-ORG": 2, "B-DATE": 3, "I-DATE": 4}
        device = torch.device("cpu")

        weights = compute_class_weights(train_data, label2id, device)
        # Sum should equal num_classes (5)
        assert torch.allclose(weights.sum(), torch.tensor(5.0), atol=1e-4)

    def test_device_placement(self):
        """Test weights are placed on correct device."""
        from training.train_advanced import compute_class_weights

        train_data = [{"tags": ["O", "B-ORG"]}]
        label2id = {"O": 0, "B-ORG": 1}
        device = torch.device("cpu")

        weights = compute_class_weights(train_data, label2id, device)
        assert weights.device == device


# ==============================================================================
# MODEL_REGISTRY Tests
# ==============================================================================


class TestModelRegistry:
    """Tests for the MODEL_REGISTRY and TOKENIZER_MAP."""

    def test_registry_has_all_models(self):
        """Test all expected model names are registered."""
        from training.train_advanced import MODEL_REGISTRY

        expected_models = [
            "xlmr_crf",
            "xlmr_large_crf",
            "phobert_crf",
            "xlmr_bilstm_crf",
            "xlmr_multihead_attn_crf",
            "xlmr_adaptive_fusion_crf",
            "focal_crf_xlmr",
            "dice_loss_xlmr",
        ]

        for model_name in expected_models:
            assert model_name in MODEL_REGISTRY

    def test_registry_values_are_classes(self):
        """Test registry values are nn.Module subclasses."""
        from training.train_advanced import MODEL_REGISTRY

        for name, cls in MODEL_REGISTRY.items():
            assert issubclass(cls, torch.nn.Module), f"{name} is not nn.Module"

    def test_tokenizer_map_matches_registry(self):
        """Test every model in registry has a tokenizer entry."""
        from training.train_advanced import MODEL_REGISTRY, TOKENIZER_MAP

        for model_name in MODEL_REGISTRY:
            assert model_name in TOKENIZER_MAP, f"{model_name} missing from TOKENIZER_MAP"

    def test_tokenizer_map_values_are_strings(self):
        """Test tokenizer map values are valid model identifiers."""
        from training.train_advanced import TOKENIZER_MAP

        for name, tokenizer_id in TOKENIZER_MAP.items():
            assert isinstance(tokenizer_id, str)
            assert len(tokenizer_id) > 0
