"""
TextCNN for Token-level NER.

Uses multiple Conv1D kernels with same-padding to capture local n-gram patterns
while preserving sequence length for token-level classification.

Architecture:
    Embedding -> Multi-kernel Conv1D (same-padding) -> ReLU -> Concat -> Dropout -> Linear

Reference:
    Kim (2014). "Convolutional Neural Networks for Sentence Classification." EMNLP.
    Adapted for token-level (sequence labeling) NER instead of sentence classification.
"""

import torch
from torch import nn
from torch.nn import functional as F


class TextCNN_NER(nn.Module):
    """TextCNN model adapted for token-level Named Entity Recognition.

    Unlike sentence-classification TextCNN (which uses max-pooling over time),
    this version uses same-padding convolutions to preserve sequence length,
    producing per-token logits for NER tagging.

    Args:
        vocab_size: Size of the vocabulary.
        embedding_dim: Dimension of token embeddings.
        filter_size: List of kernel sizes for Conv1D layers (e.g., [2, 3, 4, 5]).
        num_tags: Number of NER tag classes (BIO scheme).
        padding_idx: Index of padding token in vocabulary.
        n_filters: Number of output channels per Conv1D kernel.
        dropout: Dropout probability applied after concatenation.
    """

    def __init__(
        self,
        vocab_size: int,
        embedding_dim: int,
        filter_size: list,
        num_tags: int,
        padding_idx: int = 0,
        n_filters: int = 128,
        dropout: float = 0.3
    ):
        super().__init__()

        self.embedding = nn.Embedding(
            vocab_size,
            embedding_dim,
            padding_idx=padding_idx
        )

        # Conv1D with same-padding to preserve sequence length
        self.convs = nn.ModuleList([
            nn.Conv1d(
                in_channels=embedding_dim,
                out_channels=n_filters,
                kernel_size=fs,
                padding=fs // 2
            )
            for fs in filter_size
        ])

        self.dropout = nn.Dropout(dropout)

        # Token-level classification head
        self.fc = nn.Linear(
            in_features=n_filters * len(filter_size),
            out_features=num_tags
        )

    def forward(self, input_ids: torch.Tensor, lengths=None) -> torch.Tensor:
        """Forward pass producing per-token logits.

        Args:
            input_ids: Token indices of shape (batch_size, seq_len).
            lengths: Original sequence lengths (unused, kept for API compatibility).

        Returns:
            Logits tensor of shape (batch_size, seq_len, num_tags).
        """
        # Embed tokens: (N, L) -> (N, L, E)
        x = self.embedding(input_ids)
        seq_len = x.size(1)

        # Transpose for Conv1d: (N, L, E) -> (N, E, L)
        x = x.transpose(1, 2)

        # Apply each Conv1D kernel + ReLU activation, trim to original seq_len
        conv_outs = [F.relu(conv(x))[:, :, :seq_len] for conv in self.convs]

        # Concatenate all kernel outputs: (N, n_filters * num_kernels, L)
        x = torch.cat(conv_outs, dim=1)

        x = self.dropout(x)

        # Transpose back to token-level: (N, L, C_total)
        x = x.transpose(1, 2)

        # Project to tag space: (N, L, num_tags)
        logits = self.fc(x)

        return logits