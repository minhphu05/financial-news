"""BiLSTM + CRF for Vietnamese Financial NER.

Bidirectional LSTM with CRF decoder is a classic architecture for sequence
labeling. The BiLSTM captures contextual information from both directions,
while the CRF layer models label transition dependencies.

Reference:
    Huang et al. (2015). Bidirectional LSTM-CRF Models for Sequence Tagging.
    arXiv:1508.01991.
"""

import torch
from torch import nn
from torchcrf import CRF
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence


class BiLSTM_CRF(nn.Module):
    """Bidirectional LSTM with CRF decoder for token-level NER.

    Architecture:
        Input -> Embedding -> Dropout -> BiLSTM -> Dropout -> Linear -> CRF

    Args:
        vocab_size: Size of the token vocabulary.
        num_tags: Number of NER tag classes.
        embedding_dim: Dimension of token embeddings.
        num_layers: Number of stacked BiLSTM layers.
        hidden_size: Hidden dimension for each LSTM direction.
        padding_idx: Index of the padding token in vocabulary.
        dropout: Dropout probability.
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
    ) -> None:
        super().__init__()

        self.embedding = nn.Embedding(
            vocab_size, embedding_dim, padding_idx=padding_idx
        )
        self.dropout = nn.Dropout(dropout)

        self.bilstm = nn.LSTM(
            input_size=embedding_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        self.classifier = nn.Linear(hidden_size * 2, num_tags)
        self.crf = CRF(num_tags, batch_first=True)

    def forward(
        self,
        input_ids: torch.Tensor,
        lengths: torch.Tensor,
        tags: torch.Tensor | None = None,
    ) -> torch.Tensor | list[list[int]]:
        """Forward pass with packed sequences for variable-length inputs.

        Args:
            input_ids: Token indices of shape (batch_size, max_seq_len).
            lengths: Actual sequence lengths of shape (batch_size,).
            tags: Ground-truth tag indices of shape (batch_size, max_seq_len).
                  If provided, returns CRF negative log-likelihood loss.

        Returns:
            Loss tensor during training, or list of decoded tag sequences
            during inference.
        """
        mask = input_ids != 0  # padding_idx = 0

        embedded = self.dropout(self.embedding(input_ids))

        packed = pack_padded_sequence(
            embedded,
            lengths.cpu(),
            batch_first=True,
            enforce_sorted=False,
        )

        packed_output, _ = self.bilstm(packed)

        lstm_output, _ = pad_packed_sequence(
            packed_output,
            batch_first=True,
        )

        emissions = self.classifier(self.dropout(lstm_output))

        if tags is not None:
            loss = -self.crf(emissions, tags, mask=mask, reduction="mean")
            return loss

        return self.crf.decode(emissions, mask=mask)
