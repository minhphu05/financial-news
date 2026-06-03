"""
NER Dataset for XLM-RoBERTa Large models.

Identical to xlmr_dataset.py but uses the "xlm-roberta-large" tokenizer,
which has the same vocabulary but produces slightly different subword splits
due to the larger model's training configuration.
"""

import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer


class NERDataset(Dataset):
    """NER Dataset with XLM-RoBERTa Large tokenization and subword alignment.

    Each sample tokenizes pre-split words using the XLM-RoBERTa Large tokenizer
    with `is_split_into_words=True`, then aligns word-level tags to the
    resulting subword tokens.

    Args:
        data: List of dicts, each with "tokens": [...] and "tags": [...].
        label2id: Dictionary mapping tag strings to integer IDs.
        max_len: Maximum sequence length (including special tokens).
    """

    def __init__(self, data: list[dict], label2id: dict, max_len: int = 128):
        self.data = data
        self.label2id = label2id
        self.max_len = max_len
        self.tokenizer = AutoTokenizer.from_pretrained("xlm-roberta-large")

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> dict:
        """Get a tokenized and aligned sample.

        Args:
            idx: Dataset index.

        Returns:
            Dictionary with:
                - "input_ids": Token IDs tensor (max_len,).
                - "attention_mask": Attention mask tensor (max_len,).
                - "labels": Aligned tag IDs tensor (max_len,).
        """
        tokens = self.data[idx]["tokens"]
        tags = self.data[idx]["tags"]

        # Tokenize pre-split words (preserves word boundaries)
        encoding = self.tokenizer(
            tokens,
            is_split_into_words=True,
            return_offsets_mapping=False,
            padding='max_length',
            truncation=True,
            max_length=self.max_len,
            return_tensors="pt"
        )

        input_ids = encoding["input_ids"].squeeze()
        attention_mask = encoding["attention_mask"].squeeze()

        # Align tags to subword tokens using word_ids mapping
        word_ids = encoding.word_ids(batch_index=0)

        labels = []
        for word_idx in word_ids:
            if word_idx is None:
                # Special tokens (CLS, SEP, PAD) get "O" label
                labels.append(self.label2id["O"])
            else:
                label = tags[word_idx]
                labels.append(self.label2id[label])

        # Ensure label length matches max_len
        if len(labels) < self.max_len:
            labels.extend([-100] * (self.max_len - len(labels)))
        else:
            labels = labels[:self.max_len]

        labels = torch.tensor(labels)

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels
        }