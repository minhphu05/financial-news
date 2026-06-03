"""Unit tests for DataUtils (Vocab, phoNERT dataset, NERDataset, collate_fn)."""

import pytest
import json
import torch
from torch.utils.data import DataLoader

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from DataUtils.NER_dataset import (
    Vocab,
    phoNERT,
    collate_fn,
    read_json_or_jsonl,
    extract_data,
)


# ==============================================================================
# read_json_or_jsonl Tests
# ==============================================================================


class TestReadJsonOrJsonl:
    """Tests for file reading utility."""

    def test_read_jsonl_file(self, tmp_path):
        """Test reading JSON Lines format."""
        filepath = tmp_path / "data.jsonl"
        records = [
            {"tokens": ["A", "B"], "tags": ["O", "O"]},
            {"tokens": ["C", "D"], "tags": ["B-ORG", "I-ORG"]},
        ]
        with open(filepath, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        data = read_json_or_jsonl(str(filepath))
        assert len(data) == 2
        assert data[0]["tokens"] == ["A", "B"]
        assert data[1]["tags"] == ["B-ORG", "I-ORG"]

    def test_read_json_array_file(self, tmp_path):
        """Test reading standard JSON array format."""
        filepath = tmp_path / "data.json"
        records = [
            {"tokens": ["X", "Y"], "tags": ["O", "B-PERSON"]},
        ]
        with open(filepath, "w") as f:
            json.dump(records, f)

        data = read_json_or_jsonl(str(filepath))
        assert len(data) == 1
        assert data[0]["tokens"] == ["X", "Y"]

    def test_read_empty_file(self, tmp_path):
        """Test reading empty file."""
        filepath = tmp_path / "empty.jsonl"
        filepath.write_text("")

        data = read_json_or_jsonl(str(filepath))
        assert len(data) == 0

    def test_skips_malformed_lines(self, tmp_path):
        """Test that malformed lines in JSONL are skipped."""
        filepath = tmp_path / "mixed.jsonl"
        with open(filepath, "w") as f:
            f.write('{"tokens": ["A"], "tags": ["O"]}\n')
            f.write("not valid json\n")
            f.write('{"tokens": ["B"], "tags": ["O"]}\n')

        data = read_json_or_jsonl(str(filepath))
        assert len(data) == 2


# ==============================================================================
# extract_data Tests
# ==============================================================================


class TestExtractData:
    """Tests for the extract_data utility function."""

    def test_tokens_and_tags_keys(self):
        """Test extraction with 'tokens' and 'tags' keys."""
        item = {"tokens": ["A", "B"], "tags": ["O", "B-ORG"]}
        tokens, tags = extract_data(item)
        assert tokens == ["A", "B"]
        assert tags == ["O", "B-ORG"]

    def test_words_and_ner_tags_keys(self):
        """Test extraction with 'words' and 'ner_tags' keys."""
        item = {"words": ["C", "D"], "ner_tags": ["O", "O"]}
        tokens, tags = extract_data(item)
        assert tokens == ["C", "D"]
        assert tags == ["O", "O"]

    def test_syllables_key(self):
        """Test extraction with 'syllables' key."""
        item = {"syllables": ["Ngân", "hàng"], "tags": ["B-ORG", "I-ORG"]}
        tokens, tags = extract_data(item)
        assert tokens == ["Ngân", "hàng"]

    def test_missing_keys_raises_error(self):
        """Test that missing keys raise ValueError."""
        item = {"text": "hello", "label": "O"}
        with pytest.raises(ValueError, match="Cannot find key"):
            extract_data(item)

    def test_partial_missing_keys(self):
        """Test when only tokens present but no tags."""
        item = {"tokens": ["A", "B"]}
        with pytest.raises(ValueError):
            extract_data(item)


# ==============================================================================
# Vocab Tests
# ==============================================================================


class TestVocab:
    """Tests for the Vocab class."""

    def test_initialization(self, tmp_jsonl_file):
        """Test vocab builds correctly from JSONL."""
        vocab = Vocab(tmp_jsonl_file)

        assert vocab.vocab_size > 2  # at least <pad> + <unk> + some words
        assert vocab.num_tags > 0

    def test_special_tokens(self, tmp_jsonl_file):
        """Test <pad> is index 0, <unk> is index 1."""
        vocab = Vocab(tmp_jsonl_file)

        assert vocab.word2idx["<pad>"] == 0
        assert vocab.word2idx["<unk>"] == 1

    def test_tag_mapping(self, tmp_jsonl_file):
        """Test all tags from data are in tag2idx."""
        vocab = Vocab(tmp_jsonl_file)

        expected_tags = {"O", "B-ORG", "I-ORG", "B-TICKER", "B-RATE", "I-RATE",
                         "B-DATE", "I-DATE", "B-MONEY", "I-MONEY"}
        for tag in expected_tags:
            assert tag in vocab.tag2idx

    def test_pad_tag_index(self, tmp_jsonl_file):
        """Test pad_tag has index -100."""
        vocab = Vocab(tmp_jsonl_file)
        assert vocab.tag2idx["<pad_tag>"] == -100

    def test_vocab_size_property(self, tmp_jsonl_file):
        """Test vocab_size property returns correct count."""
        vocab = Vocab(tmp_jsonl_file)
        assert vocab.vocab_size == len(vocab.word2idx)

    def test_num_tags_property(self, tmp_jsonl_file):
        """Test num_tags excludes pad_tag."""
        vocab = Vocab(tmp_jsonl_file)
        # num_tags should not count the -100 pad_tag entry
        actual_tags = [k for k, v in vocab.tag2idx.items() if v != -100]
        assert vocab.num_tags == len(actual_tags)

    def test_encode_tokens(self, tmp_jsonl_file):
        """Test token encoding to indices."""
        vocab = Vocab(tmp_jsonl_file)
        tokens = ["ngân", "hàng", "acb"]

        encoded = vocab.encode_tokens(tokens)

        assert isinstance(encoded, torch.Tensor)
        assert encoded.dtype == torch.long
        assert len(encoded) == 3
        # All should be valid indices (not unk) since they're in vocab
        assert all(idx != 1 for idx in encoded.tolist())

    def test_encode_unknown_token(self, tmp_jsonl_file):
        """Test that unknown tokens map to <unk> index."""
        vocab = Vocab(tmp_jsonl_file)
        tokens = ["xyz_never_seen_before_token"]

        encoded = vocab.encode_tokens(tokens)
        assert encoded[0].item() == vocab.word2idx["<unk>"]

    def test_encode_is_case_insensitive(self, tmp_jsonl_file):
        """Test that encoding is case-insensitive."""
        vocab = Vocab(tmp_jsonl_file)

        upper = vocab.encode_tokens(["FPT"])
        lower = vocab.encode_tokens(["fpt"])

        assert upper[0].item() == lower[0].item()

    def test_encode_tags(self, tmp_jsonl_file):
        """Test tag encoding."""
        vocab = Vocab(tmp_jsonl_file)
        tags = ["O", "B-ORG", "I-ORG"]

        encoded = vocab.encode_tags(tags)

        assert isinstance(encoded, torch.Tensor)
        assert encoded.dtype == torch.long
        assert len(encoded) == 3
        assert all(idx >= 0 for idx in encoded.tolist())

    def test_encode_unknown_tag(self, tmp_jsonl_file):
        """Test unknown tags encode to -100."""
        vocab = Vocab(tmp_jsonl_file)
        tags = ["UNKNOWN_TAG"]

        encoded = vocab.encode_tags(tags)
        assert encoded[0].item() == -100

    def test_decode_tokens(self, tmp_jsonl_file):
        """Test token decoding from indices."""
        vocab = Vocab(tmp_jsonl_file)
        tokens = ["ngân", "hàng"]

        encoded = vocab.encode_tokens(tokens)
        decoded = vocab.decode_tokens(encoded)

        assert decoded == tokens

    def test_decode_tags(self, tmp_jsonl_file):
        """Test tag decoding from indices."""
        vocab = Vocab(tmp_jsonl_file)
        tags = ["O", "B-ORG", "I-ORG"]

        encoded = vocab.encode_tags(tags)
        decoded = vocab.decode_tags(encoded)

        assert decoded == tags

    def test_decode_tokens_from_tensor(self, tmp_jsonl_file):
        """Test decoding from a Tensor directly."""
        vocab = Vocab(tmp_jsonl_file)
        tokens = ["fpt", "tăng"]

        encoded = vocab.encode_tokens(tokens)
        decoded = vocab.decode_tokens(encoded)  # encoded is already a Tensor

        assert decoded == tokens

    def test_roundtrip_encode_decode(self, tmp_jsonl_file):
        """Test encode->decode roundtrip preserves data."""
        vocab = Vocab(tmp_jsonl_file)
        original_tokens = ["ngân", "hàng", "acb"]
        original_tags = ["B-ORG", "I-ORG", "I-ORG"]

        token_ids = vocab.encode_tokens(original_tokens)
        tag_ids = vocab.encode_tags(original_tags)

        recovered_tokens = vocab.decode_tokens(token_ids)
        recovered_tags = vocab.decode_tags(tag_ids)

        assert recovered_tokens == original_tokens
        assert recovered_tags == original_tags

    def test_empty_file_raises_error(self, tmp_path):
        """Test that empty data file raises ValueError."""
        filepath = tmp_path / "empty.jsonl"
        filepath.write_text("")

        with pytest.raises(ValueError, match="empty"):
            Vocab(str(filepath))

    def test_idx2word_consistency(self, tmp_jsonl_file):
        """Test idx2word is inverse of word2idx."""
        vocab = Vocab(tmp_jsonl_file)

        for word, idx in vocab.word2idx.items():
            assert vocab.idx2word[idx] == word

    def test_idx2tag_consistency(self, tmp_jsonl_file):
        """Test idx2tag is inverse of tag2idx."""
        vocab = Vocab(tmp_jsonl_file)

        for tag, idx in vocab.tag2idx.items():
            assert vocab.idx2tag[idx] == tag


# ==============================================================================
# phoNERT Dataset Tests
# ==============================================================================


class TestPhoNERT:
    """Tests for the phoNERT dataset class."""

    def test_initialization(self, tmp_jsonl_file, sample_vocab):
        """Test dataset loads data correctly."""
        dataset = phoNERT(tmp_jsonl_file, sample_vocab)
        assert len(dataset) == 3  # 3 samples in fixture

    def test_getitem_returns_dict(self, tmp_jsonl_file, sample_vocab):
        """Test __getitem__ returns correct dictionary."""
        dataset = phoNERT(tmp_jsonl_file, sample_vocab)
        item = dataset[0]

        assert isinstance(item, dict)
        assert "input_ids" in item
        assert "tags_ids" in item

    def test_getitem_types(self, tmp_jsonl_file, sample_vocab):
        """Test that returned tensors have correct types."""
        dataset = phoNERT(tmp_jsonl_file, sample_vocab)
        item = dataset[0]

        assert isinstance(item["input_ids"], torch.Tensor)
        assert isinstance(item["tags_ids"], torch.Tensor)
        assert item["input_ids"].dtype == torch.long
        assert item["tags_ids"].dtype == torch.long

    def test_getitem_lengths_match(self, tmp_jsonl_file, sample_vocab):
        """Test that input_ids and tags_ids have same length."""
        dataset = phoNERT(tmp_jsonl_file, sample_vocab)

        for i in range(len(dataset)):
            item = dataset[i]
            assert len(item["input_ids"]) == len(item["tags_ids"])

    def test_all_samples_accessible(self, tmp_jsonl_file, sample_vocab):
        """Test iterating through all samples."""
        dataset = phoNERT(tmp_jsonl_file, sample_vocab)

        for i in range(len(dataset)):
            item = dataset[i]
            assert item["input_ids"].numel() > 0

    def test_first_sample_content(self, tmp_jsonl_file, sample_vocab):
        """Test first sample has correct token count."""
        dataset = phoNERT(tmp_jsonl_file, sample_vocab)
        item = dataset[0]

        # First sample: ["Ngân", "hàng", "ACB", "đạt", "lợi", "nhuận"] = 6 tokens
        assert len(item["input_ids"]) == 6
        assert len(item["tags_ids"]) == 6


# ==============================================================================
# collate_fn Tests
# ==============================================================================


class TestCollateFn:
    """Tests for the collate_fn padding function."""

    def test_basic_padding(self):
        """Test collate pads to longest sequence."""
        items = [
            {"input_ids": torch.tensor([1, 2, 3]), "tags_ids": torch.tensor([0, 1, 0])},
            {"input_ids": torch.tensor([4, 5]), "tags_ids": torch.tensor([2, 0])},
        ]

        batch = collate_fn(items)

        assert batch["input_ids"].shape == (2, 3)
        assert batch["tags_ids"].shape == (2, 3)
        assert batch["lengths"].tolist() == [3, 2]

    def test_padding_values(self):
        """Test correct padding values: 0 for inputs, -100 for tags."""
        items = [
            {"input_ids": torch.tensor([1, 2, 3]), "tags_ids": torch.tensor([0, 1, 2])},
            {"input_ids": torch.tensor([4]), "tags_ids": torch.tensor([0])},
        ]

        batch = collate_fn(items)

        # Second sample should be padded
        assert batch["input_ids"][1, 1].item() == 0
        assert batch["input_ids"][1, 2].item() == 0
        assert batch["tags_ids"][1, 1].item() == -100
        assert batch["tags_ids"][1, 2].item() == -100

    def test_lengths_correct(self):
        """Test lengths tensor contains original sequence lengths."""
        items = [
            {"input_ids": torch.tensor([1, 2, 3, 4, 5]), "tags_ids": torch.tensor([0, 1, 2, 0, 1])},
            {"input_ids": torch.tensor([6, 7]), "tags_ids": torch.tensor([0, 0])},
            {"input_ids": torch.tensor([8, 9, 10]), "tags_ids": torch.tensor([1, 1, 0])},
        ]

        batch = collate_fn(items)
        assert batch["lengths"].tolist() == [5, 2, 3]

    def test_single_item(self):
        """Test collate with a single item (no padding needed)."""
        items = [
            {"input_ids": torch.tensor([1, 2, 3]), "tags_ids": torch.tensor([0, 1, 0])},
        ]

        batch = collate_fn(items)
        assert batch["input_ids"].shape == (1, 3)
        assert batch["lengths"].tolist() == [3]

    def test_same_length_sequences(self):
        """Test collate when all sequences have same length."""
        items = [
            {"input_ids": torch.tensor([1, 2, 3]), "tags_ids": torch.tensor([0, 1, 0])},
            {"input_ids": torch.tensor([4, 5, 6]), "tags_ids": torch.tensor([2, 0, 1])},
        ]

        batch = collate_fn(items)
        assert batch["input_ids"].shape == (2, 3)
        # No padding should be needed
        assert batch["input_ids"][0].tolist() == [1, 2, 3]
        assert batch["input_ids"][1].tolist() == [4, 5, 6]

    def test_with_dataloader(self, tmp_jsonl_file, sample_vocab):
        """Test collate_fn works with PyTorch DataLoader."""
        dataset = phoNERT(tmp_jsonl_file, sample_vocab)
        loader = DataLoader(dataset, batch_size=2, collate_fn=collate_fn)

        for batch in loader:
            assert "input_ids" in batch
            assert "tags_ids" in batch
            assert "lengths" in batch
            assert batch["input_ids"].dim() == 2
            break

    def test_output_dtypes(self):
        """Test output tensor dtypes."""
        items = [
            {"input_ids": torch.tensor([1, 2]), "tags_ids": torch.tensor([0, 1])},
        ]

        batch = collate_fn(items)
        assert batch["input_ids"].dtype == torch.long
        assert batch["tags_ids"].dtype == torch.long
        assert batch["lengths"].dtype == torch.long


# ==============================================================================
# NERDataset (XLM-R) Tests
# ==============================================================================


class TestNERDatasetXLMR:
    """Tests for the XLM-RoBERTa NER Dataset.

    Note: These tests require the transformers library and will
    download the tokenizer on first run.
    """

    @pytest.fixture
    def label2id(self):
        """Standard BIO label mapping."""
        return {
            "O": 0,
            "B-ORG": 1, "I-ORG": 2,
            "B-PERSON": 3, "I-PERSON": 4,
            "B-TICKER": 5, "I-TICKER": 6,
            "B-DATE": 7, "I-DATE": 8,
            "B-MONEY": 9, "I-MONEY": 10,
            "B-RATE": 11, "I-RATE": 12,
            "B-ASSET": 13, "I-ASSET": 14,
        }

    @pytest.fixture
    def sample_data(self):
        """Sample tokenized NER data."""
        return [
            {
                "tokens": ["Ngân", "hàng", "ACB", "đạt", "lợi", "nhuận"],
                "tags": ["B-ORG", "I-ORG", "I-ORG", "O", "O", "O"],
            },
            {
                "tokens": ["FPT", "tăng", "10", "%"],
                "tags": ["B-TICKER", "O", "B-RATE", "I-RATE"],
            },
        ]

    @pytest.mark.skipif(
        not os.environ.get("RUN_SLOW_TESTS"),
        reason="Requires downloading XLM-R tokenizer. Set RUN_SLOW_TESTS=1 to enable.",
    )
    def test_initialization(self, sample_data, label2id):
        """Test dataset initialization."""
        from DataUtils.xlmr_dataset import NERDataset

        dataset = NERDataset(sample_data, label2id, max_len=32)
        assert len(dataset) == 2

    @pytest.mark.skipif(
        not os.environ.get("RUN_SLOW_TESTS"),
        reason="Requires downloading XLM-R tokenizer.",
    )
    def test_getitem_keys(self, sample_data, label2id):
        """Test __getitem__ returns correct keys."""
        from DataUtils.xlmr_dataset import NERDataset

        dataset = NERDataset(sample_data, label2id, max_len=32)
        item = dataset[0]

        assert "input_ids" in item
        assert "attention_mask" in item
        assert "labels" in item

    @pytest.mark.skipif(
        not os.environ.get("RUN_SLOW_TESTS"),
        reason="Requires downloading XLM-R tokenizer.",
    )
    def test_max_length_enforced(self, sample_data, label2id):
        """Test that output is truncated/padded to max_len."""
        from DataUtils.xlmr_dataset import NERDataset

        max_len = 16
        dataset = NERDataset(sample_data, label2id, max_len=max_len)
        item = dataset[0]

        assert item["input_ids"].shape == (max_len,)
        assert item["attention_mask"].shape == (max_len,)
        assert item["labels"].shape == (max_len,)

    @pytest.mark.skipif(
        not os.environ.get("RUN_SLOW_TESTS"),
        reason="Requires downloading XLM-R tokenizer.",
    )
    def test_labels_use_label2id(self, sample_data, label2id):
        """Test that labels are correctly mapped from tag strings."""
        from DataUtils.xlmr_dataset import NERDataset

        dataset = NERDataset(sample_data, label2id, max_len=32)
        item = dataset[0]

        # All labels should be valid indices or -100
        for label_val in item["labels"].tolist():
            assert label_val in list(label2id.values()) or label_val == -100

    @pytest.mark.skipif(
        not os.environ.get("RUN_SLOW_TESTS"),
        reason="Requires downloading XLM-R tokenizer.",
    )
    def test_attention_mask_binary(self, sample_data, label2id):
        """Test attention mask only contains 0s and 1s."""
        from DataUtils.xlmr_dataset import NERDataset

        dataset = NERDataset(sample_data, label2id, max_len=32)
        item = dataset[0]

        unique_vals = item["attention_mask"].unique().tolist()
        assert all(v in [0, 1] for v in unique_vals)
