"""
BiLSTM + CRF model (simplified variant).

A lightweight BiLSTM-CRF implementation for sequence labeling tasks.
Uses word-level embeddings with bidirectional LSTM encoder and CRF decoder.

Architecture:
    Embedding -> Dropout -> BiLSTM -> Linear -> CRF
"""

import torch
from torch import nn
from torchcrf import CRF


class LSTM(nn.Module):
    """Bidirectional LSTM with CRF decoder for NER.

    This is a simplified variant of BiLSTM_CRF with fewer configuration options.
    Suitable for quick experiments and baselines.

    Args:
        vocab_size: Size of the vocabulary.
        num_tags: Number of NER tag classes.
        embedding_dim: Dimension of token embeddings.
        num_layers: Number of stacked BiLSTM layers.
        hidden_size: Hidden size of each LSTM direction.
        padding_idx: Index of padding token.
        dropout: Dropout probability.
        **kwargs: Additional keyword arguments (ignored).
    """

    def __init__(
        self,
        vocab_size: int,
        num_tags: int,
        embedding_dim: int,
        num_layers: int = 2,
        hidden_size: int = 256,
        padding_idx: int = 0,
        dropout: float = 0.3,
        **kwargs
    ):
        super().__init__()

        self.embedding = nn.Embedding(
            num_embeddings=vocab_size,
            embedding_dim=embedding_dim,
            padding_idx=padding_idx
        )
        self.dropout = nn.Dropout(dropout)
        self.bilstm = nn.LSTM(
            input_size=embedding_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            bias=True,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0
        )
        self.fc = nn.Linear(
            in_features=hidden_size * 2,
            out_features=num_tags
        )
        self.crf = CRF(
            num_tags=num_tags,
            batch_first=True
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        lengths: torch.Tensor,
        tags: torch.Tensor | None = None
    ):
        """Forward pass with CRF loss (training) or Viterbi decode (inference).

        Args:
            input_ids: Token indices of shape (batch_size, seq_len).
            lengths: Actual sequence lengths of shape (batch_size,).
            tags: Ground truth tag indices of shape (batch_size, seq_len).
                  If provided, returns CRF negative log-likelihood loss.
                  If None, returns decoded tag sequences.

        Returns:
            If tags is provided: scalar loss tensor.
            If tags is None: list of predicted tag index lists.
        """
        mask = input_ids != 0

        # Embedding + Dropout
        x = self.embedding(input_ids)
        x = self.dropout(x)

        # BiLSTM encoding
        lstm_out, _ = self.bilstm(x)
        lstm_out = self.dropout(lstm_out)

        # Project to tag space
        emissions = self.fc(lstm_out)

        # CRF: compute loss or decode
        if tags is not None:
            loss = -self.crf(emissions, tags, mask=mask, reduction="mean")
            return loss
        else:
            preds = self.crf.decode(emissions, mask=mask)
            return preds