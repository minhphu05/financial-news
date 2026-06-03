"""BiLSTM baseline for Vietnamese Financial NER.

A simple Bidirectional LSTM without CRF, using softmax classification at
each token position. This serves as the simplest neural baseline for
comparison with CRF-augmented and transformer-based models.

Reference:
    Hochreiter & Schmidhuber (1997). Long Short-Term Memory.
    Neural Computation, 9(8), 1735-1780.
"""

import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence


class BiLSTM(nn.Module):
    """Bidirectional LSTM for token-level NER without CRF.

    Architecture:
        Input -> Embedding -> Dropout -> BiLSTM -> Dropout -> Linear -> Softmax

    This model independently classifies each token without modeling label
    dependencies. It serves as a baseline to quantify the benefit of CRF.

    Args:
        vocab_size: Size of the token vocabulary.
        num_tags: Number of NER tag classes.
        embedding_dim: Dimension of token embeddings.
        num_layers: Number of stacked BiLSTM layers.
        hidden_size: Hidden dimension for each LSTM direction.
        padding_idx: Index of the padding token.
        dropout: Dropout probability.
    """

    def __init__(
        self,
        vocab_size: int,
        num_tags: int,
        embedding_dim: int,
        num_layers: int = 5,
        hidden_size: int = 256,
        padding_idx: int = 0,
        dropout: float = 0.3,
        **kwargs,
    ) -> None:
        super().__init__()

        self.embedding = nn.Embedding(
            num_embeddings=vocab_size,
            embedding_dim=embedding_dim,
            padding_idx=padding_idx,
        )

        self.dropout = nn.Dropout(dropout)

        self.bilstm = nn.LSTM(
            input_size=embedding_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            bias=True,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        self.classifier = nn.Linear(
            in_features=hidden_size * 2,
            out_features=num_tags,
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        lengths: torch.Tensor,
    ) -> torch.Tensor:
        """Forward pass producing token-level logits.

        Args:
            input_ids: Token indices of shape (batch_size, max_seq_len).
            lengths: Actual sequence lengths of shape (batch_size,).

        Returns:
            Logits tensor of shape (batch_size, max_seq_len, num_tags).
        """
        embedded = self.dropout(self.embedding(input_ids))

        packed_input = pack_padded_sequence(
            embedded,
            lengths.cpu(),
            batch_first=True,
            enforce_sorted=False,
        )

        packed_output, _ = self.bilstm(packed_input)

        output, _ = pad_packed_sequence(
            packed_output,
            batch_first=True,
        )

        logits = self.classifier(self.dropout(output))
        return logits

