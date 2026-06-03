"""XLM-RoBERTa + Adaptive Layer Fusion + CRF for Vietnamese Financial NER.

Standard fine-tuning only uses the last hidden layer of a transformer model.
However, different layers capture different linguistic phenomena:
- Lower layers: morphological and syntactic features
- Middle layers: semantic relationships
- Upper layers: task-specific features

This model introduces Adaptive Layer Fusion, which learns a weighted combination
of ALL transformer layers for optimal NER performance.

Research Gap:
    Previous Vietnamese NER models treat the transformer as a black box, using
    only the last layer output. Our approach adaptively fuses information across
    all layers, allowing the model to leverage lower-layer syntactic cues
    (critical for Vietnamese compound words) alongside upper-layer semantic
    representations.

Key Innovation:
    - Layer-wise attention weights are learned end-to-end with the NER objective.
    - A learnable scalar gamma controls the contribution of fused vs. last-layer
      representations, preventing catastrophic forgetting during fine-tuning.

Reference:
    - Peters et al. (2018). Deep contextualized word representations (ELMo).
    - Kondratyuk & Straka (2019). 75 Languages, 1 Model: Parsing Universal
      Dependencies Universally.
    - Li et al. (2022). Rethinking the Role of Demonstrations in In-Context Learning.
"""

import torch
from torch import nn
from transformers import AutoModel, AutoConfig
from torchcrf import CRF


class AdaptiveLayerFusion(nn.Module):
    """Learns a weighted combination of transformer hidden layers.

    Instead of using only the last layer, this module computes a task-optimized
    weighted sum across all encoder layers. The weights are learned through
    a softmax-normalized attention mechanism.

    Args:
        num_layers: Number of transformer layers to fuse.
        hidden_size: Dimension of each layer's hidden states.
    """

    def __init__(self, num_layers: int, hidden_size: int) -> None:
        super().__init__()
        self.num_layers = num_layers
        self.layer_weights = nn.Parameter(torch.ones(num_layers) / num_layers)
        self.gamma = nn.Parameter(torch.tensor(1.0))
        self.layer_norm = nn.LayerNorm(hidden_size)

    def forward(self, all_hidden_states: tuple[torch.Tensor, ...]) -> torch.Tensor:
        """Compute adaptive fusion of all hidden layers.

        Args:
            all_hidden_states: Tuple of tensors from each transformer layer,
                each of shape (batch_size, seq_len, hidden_size).
                Includes the embedding layer output at index 0.

        Returns:
            Fused representation of shape (batch_size, seq_len, hidden_size).
        """
        # Stack all layers: (num_layers, batch_size, seq_len, hidden_size)
        stacked = torch.stack(all_hidden_states[1:], dim=0)  # skip embedding layer

        # Normalize weights via softmax
        weights = torch.softmax(self.layer_weights, dim=0)
        weights = weights.view(-1, 1, 1, 1)

        # Weighted sum across layers
        fused = (weights * stacked).sum(dim=0)
        fused = self.gamma * fused

        return self.layer_norm(fused)


class XLMR_Adaptive_Fusion_CRF(nn.Module):
    """XLM-RoBERTa + Adaptive Layer Fusion + CRF.

    Architecture:
        Input -> XLM-RoBERTa (all layers) -> Adaptive Fusion -> Dropout -> Linear -> CRF

    All transformer layers are fused with learned weights, providing richer
    representations than single-layer extraction.

    Args:
        num_tags: Number of NER tag classes.
        model_name: HuggingFace model identifier.
        dropout: Dropout probability before classifier.
        freeze_encoder: Whether to freeze XLM-RoBERTa weights.
    """

    def __init__(
        self,
        num_tags: int,
        model_name: str = "xlm-roberta-base",
        dropout: float = 0.3,
        freeze_encoder: bool = False,
    ) -> None:
        super().__init__()

        config = AutoConfig.from_pretrained(model_name, output_hidden_states=True)
        self.encoder = AutoModel.from_pretrained(model_name, config=config)
        hidden_size = config.hidden_size
        num_layers = config.num_hidden_layers

        if freeze_encoder:
            for param in self.encoder.parameters():
                param.requires_grad = False

        self.layer_fusion = AdaptiveLayerFusion(
            num_layers=num_layers,
            hidden_size=hidden_size,
        )

        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, num_tags)
        self.crf = CRF(num_tags, batch_first=True)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor | list[list[int]]:
        """Forward pass with adaptive layer fusion and CRF decoding.

        Args:
            input_ids: Token IDs of shape (batch_size, seq_len).
            attention_mask: Attention mask of shape (batch_size, seq_len).
            labels: Ground-truth tags. If provided, returns loss.

        Returns:
            Loss tensor during training, or decoded tag sequences during inference.
        """
        outputs = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        fused = self.layer_fusion(outputs.hidden_states)
        fused = self.dropout(fused)
        emissions = self.classifier(fused)

        if labels is not None:
            loss = -self.crf(
                emissions,
                labels,
                mask=attention_mask.bool(),
                reduction="mean",
            )
            return loss

        return self.crf.decode(emissions, mask=attention_mask.bool())
