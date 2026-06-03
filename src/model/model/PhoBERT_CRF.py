"""PhoBERT + CRF model for Vietnamese Financial NER.

PhoBERT is a pre-trained language model specifically designed for Vietnamese,
trained on a large Vietnamese corpus. It captures Vietnamese linguistic features
better than multilingual models for Vietnamese-specific tasks.

Reference:
    Nguyen, D. Q., & Nguyen, A. T. (2020). PhoBERT: Pre-trained language models
    for Vietnamese. Findings of EMNLP 2020.
"""

import torch
from torch import nn
from transformers import AutoModel
from torchcrf import CRF


class PhoBERT_CRF(nn.Module):
    """PhoBERT encoder with a Conditional Random Field (CRF) decoder.

    Architecture:
        Input -> PhoBERT Encoder -> Dropout -> Linear Projection -> CRF Decoder

    This model leverages PhoBERT's Vietnamese-specific pre-training to produce
    contextual token representations, followed by a CRF layer to model
    label dependencies (e.g., B-ORG must precede I-ORG).

    Args:
        num_tags: Number of NER tag classes.
        model_name: HuggingFace model identifier for PhoBERT.
        dropout: Dropout probability applied after encoder output.
        freeze_encoder: Whether to freeze the PhoBERT encoder weights.
    """

    def __init__(
        self,
        num_tags: int,
        model_name: str = "vinai/phobert-base-v2",
        dropout: float = 0.1,
        freeze_encoder: bool = False,
    ) -> None:
        super().__init__()

        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size

        if freeze_encoder:
            for param in self.encoder.parameters():
                param.requires_grad = False

        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, num_tags)
        self.crf = CRF(num_tags, batch_first=True)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor | list[list[int]]:
        """Forward pass with optional CRF loss computation.

        Args:
            input_ids: Token IDs of shape (batch_size, seq_len).
            attention_mask: Attention mask of shape (batch_size, seq_len).
            labels: Ground-truth tag IDs of shape (batch_size, seq_len).
                    If provided, returns CRF negative log-likelihood loss.
                    If None, returns decoded tag sequences.

        Returns:
            Loss tensor during training, or list of predicted tag sequences
            during inference.
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
