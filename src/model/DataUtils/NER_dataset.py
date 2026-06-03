"""
NER Dataset utilities for BiLSTM-based models.

Provides vocabulary building, token/tag encoding, dataset class, and collate function
for padding variable-length sequences in a batch.

Supports JSONL data format with fields: "tokens"/"words"/"syllables" and "tags"/"ner_tags".
"""

import os
import json
import string
from collections import Counter
import torch
from torch import nn
from torch.utils.data import Dataset
from torch.nn.utils.rnn import pad_sequence


def collate_fn(items: list[dict]) -> dict:
    """Collate function for DataLoader that pads variable-length sequences.

    Gathers input_ids and tags_ids from each item, pads them to the longest
    sequence in the batch, and returns a dictionary of tensors.

    Args:
        items: List of dicts with "input_ids" and "tags_ids" tensors.

    Returns:
        Dictionary with keys:
            - "input_ids": Padded input tensor (batch_size, max_len), pad=0.
            - "tags_ids": Padded tag tensor (batch_size, max_len), pad=-100.
            - "lengths": Actual lengths tensor (batch_size,).
    """
    input_ids = [item["input_ids"] for item in items]
    tags_ids = [item["tags_ids"] for item in items]

    # Store actual sequence lengths before padding
    lengths = torch.tensor([len(seq) for seq in input_ids], dtype=torch.long)

    padded_inputs = pad_sequence(
        input_ids,
        batch_first=True,
        padding_value=0
    )
    padded_tags = pad_sequence(
        tags_ids,
        batch_first=True,
        padding_value=-100
    )
    return {
        "input_ids": padded_inputs,
        "tags_ids": padded_tags,
        "lengths": lengths
    }


def read_json_or_jsonl(filepath: str) -> list:
    """Read a JSON or JSONL file and return a list of records.

    Attempts to parse as a single JSON array first. If that fails,
    falls back to reading line-by-line as JSON Lines format.

    Args:
        filepath: Path to the JSON/JSONL file.

    Returns:
        List of dictionaries parsed from the file.
    """
    data = []
    try:
        with open(filepath, 'r', encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"File {filepath} appears to be JSON Lines. Reading line by line...")
        with open(filepath, 'r', encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    print("Data loading complete.")
    return data


def extract_data(item: dict):
    """Extract tokens and tags from a data record.

    Supports multiple key naming conventions:
        - Tokens: "tokens", "words", or "syllables"
        - Tags: "tags" or "ner_tags"

    Args:
        item: Dictionary containing token and tag fields.

    Returns:
        Tuple of (tokens: list[str], tags: list[str]).

    Raises:
        ValueError: If neither token nor tag keys are found.
    """
    tokens: list[str] = item.get("tokens")
    if tokens is None:
        tokens = item.get("words")
    if tokens is None:
        tokens = item.get("syllables")

    tags = item.get("tags")
    if tags is None:
        tags: list[str] = item.get("ner_tags")

    if tokens is None or tags is None:
        raise ValueError(
            f"Cannot find key 'tokens'/'words'/'syllables' or 'tags'/'ner_tags'.\n"
            f"Available keys: {list(item.keys())}"
        )
    return tokens, tags
                        
class Vocab:
    """Vocabulary builder for NER datasets.

    Reads training data to build word-to-index and tag-to-index mappings.
    Special tokens: <pad> (index 0), <unk> (index 1).
    Tag padding uses index -100 (compatible with PyTorch ignore_index).

    Args:
        filepath: Path to the training JSONL file used to build vocabulary.
    """

    def __init__(
        self,
        filepath: str
    ):
        word_counter = Counter()
        tag_set = set()

        print(f"Building vocab from {filepath}")
        try:
            data = read_json_or_jsonl(filepath)
        except Exception as e:
            raise ValueError(f"Cannot read file {filepath}.\nError: {e}")

        if not data:
            raise ValueError("Data file is empty")

        for idx, item in enumerate(data):
            try:
                tokens, tags = extract_data(item)
            except KeyError as e:
                if idx == 0:
                    raise e
                continue

            for token in tokens:
                word_counter[token.lower()] += 1
            for tag in tags:
                tag_set.add(tag)

        # Special tokens
        self.pad = "<pad>"
        self.unk = "<unk>"
        self.pad_tag = "<pad_tag>"

        # Build word-to-index mapping
        self.word2idx = {
            self.pad: 0,
            self.unk: 1
        }

        for word, count in word_counter.items():
            if count >= 1:
                self.word2idx[word] = len(self.word2idx)
        self.idx2word = {
            idx: word for word, idx in self.word2idx.items()
        }

        # Build tag-to-index mapping
        self.tag2idx = {
            tag: idx for idx, tag in enumerate(sorted(list(tag_set)))
        }
        self.tag2idx[self.pad_tag] = -100
        self.idx2tag = {
            idx: tag for tag, idx in self.tag2idx.items()
        }

        print(f"Vocab size: {len(self.word2idx)}")
        print(f"Num tags: {len(self.tag2idx)-1}")  # Exclude pad_tag

    @property
    def num_tags(self) -> int:
        """Number of actual NER tags (excluding pad_tag)."""
        return len([i for i in self.tag2idx.values() if i != -100])

    @property
    def vocab_size(self) -> int:
        """Total vocabulary size including special tokens."""
        return len(self.word2idx)

    def encode_tokens(
        self,
        tokens: list[str]
    ) -> torch.Tensor:
        """Convert token strings to integer indices.

        Args:
            tokens: List of token strings.

        Returns:
            LongTensor of token indices.
        """
        ids = []
        for token in tokens:
            token = token.lower()
            ids.append(
                self.word2idx.get(token, self.word2idx[self.unk])
            )
        return torch.tensor(ids, dtype=torch.long)

    def encode_tags(
        self,
        tags: list[str]
    ) -> torch.Tensor:
        """Convert tag strings to integer indices.

        Args:
            tags: List of BIO tag strings.

        Returns:
            LongTensor of tag indices.
        """
        ids = [self.tag2idx.get(tag, -100) for tag in tags]
        return torch.tensor(ids, dtype=torch.long)

    def decode_tokens(
        self,
        ids: list[int]
    ) -> list[str]:
        """Convert token indices back to strings.

        Args:
            ids: List of token indices or a Tensor.

        Returns:
            List of token strings.
        """
        if isinstance(ids, torch.Tensor):
            ids = ids.tolist()
        return [self.idx2word.get(id, self.unk) for id in ids]

    def decode_tags(
        self,
        ids: list[int]
    ) -> list[str]:
        """Convert tag indices back to tag strings.

        Args:
            ids: List of tag indices or a Tensor.

        Returns:
            List of tag strings.
        """
        if isinstance(ids, torch.Tensor):
            ids = ids.tolist()
        return [self.idx2tag.get(id, "PAD") for id in ids]


class phoNERT(Dataset):
    """NER Dataset for BiLSTM-based models.

    Loads JSONL data and encodes tokens/tags using the provided Vocab.
    Each sample returns encoded input_ids and tags_ids tensors.

    Args:
        filepath: Path to the JSONL data file.
        vocab: Vocab instance for encoding tokens and tags.
        **kwargs: Additional keyword arguments (ignored).
    """

    def __init__(
        self,
        filepath: str,
        vocab: Vocab,
        **kwargs
    ) -> None:
        super().__init__()

        self.vocab = vocab
        print(f"Loading data from {filepath}")
        self.data = read_json_or_jsonl(filepath)

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, index: int) -> dict:
        """Get a single encoded sample.

        Args:
            index: Dataset index.

        Returns:
            Dictionary with "input_ids" and "tags_ids" tensors.
        """
        item = self.data[index]

        tokens, tags = extract_data(item)

        input_ids = self.vocab.encode_tokens(tokens)
        tags_ids = self.vocab.encode_tags(tags)

        return {
            "input_ids": input_ids,
            "tags_ids": tags_ids
        }