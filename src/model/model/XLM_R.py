"""XLM-RoBERTa Base + CRF for Vietnamese Financial NER.

XLM-RoBERTa is a multilingual transformer model trained on 100 languages
including Vietnamese. Combined with a CRF decoder, it provides strong
baseline performance for sequence labeling tasks.

Reference:
    Conneau et al. (2020). Unsupervised Cross-lingual Representation Learning
    at Scale. ACL 2020.
"""

import torch
from torch import nn
from transformers import AutoModel
from torchcrf import CRF


class XLMR_CRF(nn.Module):
    """XLM-RoBERTa Base encoder with CRF decoder for NER.

    Architecture:
        Input -> XLM-RoBERTa Base (768-dim) -> Dropout -> Linear -> CRF

    Args:
        num_tags: Number of NER tag classes.
        model_name: HuggingFace model identifier. Defaults to xlm-roberta-base.
        dropout: Dropout probability after encoder output.
    """

    def __init__(
        self,
        num_tags: int,
        model_name: str = "xlm-roberta-base",
        dropout: float = 0.1,
    ) -> None:
        super().__init__()

        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size

        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, num_tags)
        self.crf = CRF(num_tags, batch_first=True)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor | list[list[int]]:
        """Forward pass with CRF loss computation or decoding.

        Args:
            input_ids: Token IDs of shape (batch_size, seq_len).
            attention_mask: Attention mask of shape (batch_size, seq_len).
            labels: Ground-truth tag IDs. If provided, returns loss.

        Returns:
            Negative log-likelihood loss during training, or list of decoded
            tag sequences during inference.
        """
        outputs = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        sequence_output = self.dropout(outputs.last_hidden_state)
        emissions = self.classifier(sequence_output)

        if labels is not None:
            loss = -self.crf(
                emissions,
                labels,
                mask=attention_mask.bool(),
                reduction="mean",
            )
            return loss

        return self.crf.decode(emissions, mask=attention_mask.bool())
