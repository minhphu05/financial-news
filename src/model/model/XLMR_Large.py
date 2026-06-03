"""XLM-RoBERTa Large + CRF for Vietnamese Financial NER.

The Large variant of XLM-RoBERTa (1024-dim, 24 layers) provides higher
capacity for capturing complex multilingual patterns at the cost of
increased computational requirements.

Reference:
    Conneau et al. (2020). Unsupervised Cross-lingual Representation Learning
    at Scale. ACL 2020.
"""

import torch
from torch import nn
from transformers import AutoModel
from torchcrf import CRF


class XLMR_Large_CRF(nn.Module):
    """XLM-RoBERTa Large encoder with CRF decoder for NER.

    Architecture:
        Input -> XLM-RoBERTa Large (1024-dim) -> Dropout -> Linear -> CRF

    Note:
        The hidden size is 1024 for xlm-roberta-large.

    Args:
        num_tags: Number of NER tag classes.
        model_name: HuggingFace model identifier. Defaults to xlm-roberta-large.
        dropout: Dropout probability after encoder output.
    """

    def __init__(
        self,
        num_tags: int,
        model_name: str = "xlm-roberta-large",
        dropout: float = 0.3,
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
