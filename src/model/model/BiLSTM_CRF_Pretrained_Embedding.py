"""
BiLSTM + CRF with Pretrained Embeddings.

Extends the BiLSTM-CRF architecture with pretrained word embeddings (e.g., fastText)
for improved initialization. Supports optional embedding freezing.

Architecture:
    Pretrained Embedding -> Dropout -> BiLSTM (packed) -> Dropout -> Linear -> CRF

Reference:
    Huang et al. (2015). "Bidirectional LSTM-CRF Models for Sequence Tagging."
"""

import torch
from torch import nn
from torchcrf import CRF
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence


class BiLSTM_CRF(nn.Module):
    """BiLSTM-CRF model with optional pretrained embedding initialization.

    This model supports loading pretrained embeddings (e.g., Vietnamese fastText)
    to provide better initial word representations. The embeddings can optionally
    be frozen during training.

    Args:
        vocab_size: Size of the vocabulary.
        num_tags: Number of NER tag classes (BIO scheme).
        embedding_dim: Dimension of token embeddings.
        hidden_size: Hidden size of each LSTM direction.
        num_layers: Number of stacked BiLSTM layers.
        dropout: Dropout probability.
        padding_idx: Index of padding token in vocabulary.
        pretrained_embeddings: Optional pretrained embedding weight tensor
            of shape (vocab_size, embedding_dim).
        freeze_embedding: If True, embedding weights are not updated during training.
    """

    def __init__(
        self,
        vocab_size: int,
        num_tags: int,
        embedding_dim: int,
        hidden_size: int,
        num_layers: int = 2,
        dropout: float = 0.3,
        padding_idx: int = 0,
        pretrained_embeddings: torch.Tensor | None = None,
        freeze_embedding: bool = False
    ):
        super().__init__()

        # Embedding layer with optional pretrained initialization
        self.embedding = nn.Embedding(
            vocab_size,
            embedding_dim,
            padding_idx=padding_idx
        )

        if pretrained_embeddings is not None:
            self.embedding.weight.data.copy_(pretrained_embeddings)
            self.embedding.weight.requires_grad = not freeze_embedding

        self.dropout = nn.Dropout(dropout)

        # BiLSTM encoder
        self.bilstm = nn.LSTM(
            input_size=embedding_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0
        )

        # Linear projection to tag space
        self.fc = nn.Linear(hidden_size * 2, num_tags)

        # CRF decoder for structured prediction
        self.crf = CRF(num_tags, batch_first=True)

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
        mask = input_ids != 0  # padding_idx = 0

        # Embedding + Dropout
        x = self.embedding(input_ids)
        x = self.dropout(x)

        # Pack sequences for efficient LSTM computation
        packed = pack_padded_sequence(
            x,
            lengths.cpu(),
            batch_first=True,
            enforce_sorted=False
        )

        packed_out, _ = self.bilstm(packed)

        # Unpack back to padded tensor
        lstm_out, _ = pad_packed_sequence(
            packed_out,
            batch_first=True
        )

        lstm_out = self.dropout(lstm_out)

        # Compute emission scores
        emissions = self.fc(lstm_out)

        # Training: return CRF negative log-likelihood
        if tags is not None:
            loss = -self.crf(
                emissions,
                tags,
                mask=mask,
                reduction="mean"
            )
            return loss

        # Inference: Viterbi decoding
        else:
            preds = self.crf.decode(
                emissions,
                mask=mask
            )
            return preds
