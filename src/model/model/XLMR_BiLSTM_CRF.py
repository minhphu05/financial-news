"""XLM-RoBERTa + BiLSTM + CRF hybrid model for Vietnamese Financial NER.

This architecture combines the strengths of:
1. XLM-RoBERTa: Multilingual contextual embeddings with cross-lingual transfer
2. BiLSTM: Sequential modeling to capture local token dependencies
3. CRF: Structured prediction to enforce valid label transitions

The BiLSTM layer between the transformer and CRF acts as a refinement module,
capturing task-specific sequential patterns that the pre-trained encoder may
not have learned during generic pre-training.

Research Gap:
    Most Vietnamese NER systems use either pure transformer or pure BiLSTM-CRF.
    The hybrid approach addresses the gap where transformer outputs, while
    contextually rich, lack explicit sequential bias for structured prediction.
    The BiLSTM refinement layer bridges this gap.

Reference:
    - Devlin et al. (2019). BERT: Pre-training of Deep Bidirectional Transformers.
    - Conneau et al. (2020). Unsupervised Cross-lingual Representation Learning.
    - Huang et al. (2015). Bidirectional LSTM-CRF Models for Sequence Tagging.
"""

import torch
from torch import nn
from transformers import AutoModel
from torchcrf import CRF


class XLMR_BiLSTM_CRF(nn.Module):
    """XLM-RoBERTa encoder + BiLSTM refinement + CRF decoder.

    Architecture:
        Input -> XLM-RoBERTa -> BiLSTM -> LayerNorm -> Dropout -> Linear -> CRF

    The BiLSTM layer refines transformer representations by explicitly modeling
    left-to-right and right-to-left token dependencies in a task-specific manner.

    Args:
        num_tags: Number of NER tag classes.
        model_name: HuggingFace model identifier for XLM-RoBERTa.
        lstm_hidden_size: Hidden dimension for each LSTM direction.
        lstm_num_layers: Number of stacked BiLSTM layers.
        dropout: Dropout probability.
        freeze_encoder: Whether to freeze XLM-RoBERTa weights.
    """

    def __init__(
        self,
        num_tags: int,
        model_name: str = "xlm-roberta-base",
        lstm_hidden_size: int = 256,
        lstm_num_layers: int = 1,
        dropout: float = 0.3,
        freeze_encoder: bool = False,
    ) -> None:
        super().__init__()

        self.encoder = AutoModel.from_pretrained(model_name)
        encoder_hidden = self.encoder.config.hidden_size

        if freeze_encoder:
            for param in self.encoder.parameters():
                param.requires_grad = False

        self.bilstm = nn.LSTM(
            input_size=encoder_hidden,
            hidden_size=lstm_hidden_size,
            num_layers=lstm_num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if lstm_num_layers > 1 else 0.0,
        )

        self.layer_norm = nn.LayerNorm(lstm_hidden_size * 2)
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(lstm_hidden_size * 2, num_tags)
        self.crf = CRF(num_tags, batch_first=True)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor | list[list[int]]:
        """Forward pass through encoder, BiLSTM refinement, and CRF.

        Args:
            input_ids: Token IDs of shape (batch_size, seq_len).
            attention_mask: Attention mask of shape (batch_size, seq_len).
            labels: Ground-truth tag IDs. If provided, returns loss.

        Returns:
            Negative log-likelihood loss during training, or decoded tag
            sequences during inference.
        """
        encoder_output = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        hidden_states = encoder_output.last_hidden_state
        lstm_output, _ = self.bilstm(hidden_states)
        lstm_output = self.layer_norm(lstm_output)
        lstm_output = self.dropout(lstm_output)
        emissions = self.classifier(lstm_output)

        if labels is not None:
            loss = -self.crf(
                emissions,
                labels,
                mask=attention_mask.bool(),
                reduction="mean",
            )
            return loss

        return self.crf.decode(emissions, mask=attention_mask.bool())
