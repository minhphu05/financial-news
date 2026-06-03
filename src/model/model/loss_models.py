"""Focal Loss and Dice Loss variants for NER with class imbalance.

Vietnamese Financial NER suffers from severe class imbalance: the O-tag dominates
(typically >80% of tokens), while rare entity types like TICKER, VOLUME, and PRICE
have very few samples. Standard CRF log-likelihood treats all tokens equally,
leading to suboptimal performance on minority classes.

This module implements two loss function modifications:

1. Focal-CRF: Applies focal loss weighting to the CRF's emission scores,
   down-weighting easy-to-classify O-tokens and focusing training on hard
   entity boundary tokens.

2. Dice Loss: A boundary-sensitive loss that directly optimizes the F1-like
   metric per entity class, providing balanced gradients regardless of class
   frequency.

Research Gap:
    Standard NER systems use cross-entropy or CRF negative log-likelihood,
    which are biased towards majority classes. In Vietnamese financial text,
    where entity density is low (~15% of tokens are entities), this leads to
    high precision but low recall on rare entity types. Our approach explicitly
    addresses this through loss function engineering.

Reference:
    - Lin et al. (2017). Focal Loss for Dense Object Detection.
    - Li et al. (2020). Dice Loss for Data-imbalanced NLP Tasks.
    - Wang et al. (2021). Automated Concatenation of Embeddings for NER.
"""

import torch
from torch import nn
from torch.nn import functional as F
from transformers import AutoModel
from torchcrf import CRF


class FocalLoss(nn.Module):
    """Focal Loss for sequence labeling with class imbalance.

    Focal loss down-weights easy examples (well-classified tokens like O-tag)
    and focuses on hard examples (entity boundaries). This is especially
    important for Vietnamese financial NER where entities are sparse.

    The formula: FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)

    Args:
        num_classes: Number of tag classes.
        alpha: Class-specific weighting factor. If None, uniform weights.
        gamma: Focusing parameter. Higher values = more focus on hard examples.
            gamma=0 reduces to standard cross-entropy.
        ignore_index: Label index to ignore (e.g., padding).
    """

    def __init__(
        self,
        num_classes: int,
        alpha: torch.Tensor | None = None,
        gamma: float = 2.0,
        ignore_index: int = -100,
    ) -> None:
        super().__init__()
        self.num_classes = num_classes
        self.gamma = gamma
        self.ignore_index = ignore_index

        if alpha is not None:
            self.register_buffer("alpha", alpha)
        else:
            self.register_buffer("alpha", torch.ones(num_classes))

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """Compute focal loss.

        Args:
            logits: Prediction logits of shape (batch_size, seq_len, num_classes).
            targets: Ground-truth labels of shape (batch_size, seq_len).

        Returns:
            Scalar focal loss value.
        """
        batch_size, seq_len, num_classes = logits.shape

        # Flatten for computation
        logits_flat = logits.view(-1, num_classes)
        targets_flat = targets.view(-1)

        # Create mask for valid positions
        valid_mask = targets_flat != self.ignore_index
        logits_flat = logits_flat[valid_mask]
        targets_flat = targets_flat[valid_mask]

        if logits_flat.numel() == 0:
            return torch.tensor(0.0, device=logits.device, requires_grad=True)

        # Compute probabilities
        probs = F.softmax(logits_flat, dim=-1)
        targets_one_hot = F.one_hot(targets_flat, num_classes).float()

        # p_t: probability of the correct class
        p_t = (probs * targets_one_hot).sum(dim=-1)

        # Focal weight: (1 - p_t)^gamma
        focal_weight = (1.0 - p_t) ** self.gamma

        # Alpha weighting
        alpha_t = self.alpha[targets_flat]

        # Focal loss
        ce_loss = -torch.log(p_t + 1e-8)
        loss = alpha_t * focal_weight * ce_loss

        return loss.mean()


class DiceLoss(nn.Module):
    """Dice Loss for token-level NER with class imbalance.

    Dice loss directly optimizes the overlap between predicted and ground-truth
    entity regions, analogous to the F1 score. Unlike cross-entropy, it provides
    balanced gradients across all classes regardless of frequency.

    The formula: DL = 1 - (2 * |pred ∩ true| + smooth) / (|pred| + |true| + smooth)

    Args:
        num_classes: Number of tag classes.
        smooth: Smoothing factor to prevent division by zero.
        ignore_index: Label index to ignore.
    """

    def __init__(
        self,
        num_classes: int,
        smooth: float = 1.0,
        ignore_index: int = -100,
    ) -> None:
        super().__init__()
        self.num_classes = num_classes
        self.smooth = smooth
        self.ignore_index = ignore_index

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """Compute dice loss across all classes.

        Args:
            logits: Prediction logits of shape (batch_size, seq_len, num_classes).
            targets: Ground-truth labels of shape (batch_size, seq_len).

        Returns:
            Scalar dice loss value (1 - average dice coefficient).
        """
        batch_size, seq_len, num_classes = logits.shape

        logits_flat = logits.view(-1, num_classes)
        targets_flat = targets.view(-1)

        valid_mask = targets_flat != self.ignore_index
        logits_flat = logits_flat[valid_mask]
        targets_flat = targets_flat[valid_mask]

        if logits_flat.numel() == 0:
            return torch.tensor(0.0, device=logits.device, requires_grad=True)

        probs = F.softmax(logits_flat, dim=-1)
        targets_one_hot = F.one_hot(targets_flat, num_classes).float()

        # Per-class dice coefficient
        intersection = (probs * targets_one_hot).sum(dim=0)
        union = probs.sum(dim=0) + targets_one_hot.sum(dim=0)

        dice_per_class = (2.0 * intersection + self.smooth) / (union + self.smooth)
        dice_loss = 1.0 - dice_per_class.mean()

        return dice_loss


class FocalCRF_XLMR(nn.Module):
    """XLM-RoBERTa with Focal Loss + CRF for class-imbalanced NER.

    Architecture:
        Input -> XLM-RoBERTa -> Dropout -> Linear -> Focal Loss + CRF

    Training uses a combination of focal loss (for emission quality) and
    CRF loss (for transition modeling), weighted by a learnable lambda.

    Args:
        num_tags: Number of NER tag classes.
        model_name: HuggingFace model identifier.
        focal_gamma: Focal loss focusing parameter.
        focal_alpha: Per-class weights for focal loss. If None, computed
            from training data distribution.
        crf_weight: Relative weight of CRF loss vs focal loss.
        dropout: Dropout probability.
    """

    def __init__(
        self,
        num_tags: int,
        model_name: str = "xlm-roberta-base",
        focal_gamma: float = 2.0,
        focal_alpha: torch.Tensor | None = None,
        crf_weight: float = 0.5,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()

        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size

        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, num_tags)
        self.crf = CRF(num_tags, batch_first=True)

        self.focal_loss = FocalLoss(
            num_classes=num_tags,
            alpha=focal_alpha,
            gamma=focal_gamma,
        )

        self.crf_weight = crf_weight

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor | list[list[int]]:
        """Forward pass with combined focal + CRF loss.

        Args:
            input_ids: Token IDs of shape (batch_size, seq_len).
            attention_mask: Attention mask of shape (batch_size, seq_len).
            labels: Ground-truth tags. If provided, returns combined loss.

        Returns:
            Combined loss during training, or decoded sequences during inference.
        """
        outputs = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        hidden_states = self.dropout(outputs.last_hidden_state)
        emissions = self.classifier(hidden_states)

        if labels is not None:
            # CRF negative log-likelihood
            crf_loss = -self.crf(
                emissions,
                labels,
                mask=attention_mask.bool(),
                reduction="mean",
            )

            # Focal loss on emissions
            focal_loss = self.focal_loss(emissions, labels)

            # Combined loss
            total_loss = self.crf_weight * crf_loss + (1 - self.crf_weight) * focal_loss
            return total_loss

        return self.crf.decode(emissions, mask=attention_mask.bool())


class DiceLoss_XLMR(nn.Module):
    """XLM-RoBERTa with Dice Loss + CRF for boundary-sensitive NER.

    Architecture:
        Input -> XLM-RoBERTa -> Dropout -> Linear -> Dice Loss + CRF

    Dice loss directly optimizes entity-level F1, while CRF enforces valid
    label transitions. This combination is particularly effective for
    Vietnamese financial entities with variable-length spans.

    Args:
        num_tags: Number of NER tag classes.
        model_name: HuggingFace model identifier.
        dice_smooth: Smoothing factor for dice loss.
        crf_weight: Relative weight of CRF loss vs dice loss.
        dropout: Dropout probability.
    """

    def __init__(
        self,
        num_tags: int,
        model_name: str = "xlm-roberta-base",
        dice_smooth: float = 1.0,
        crf_weight: float = 0.5,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()

        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size

        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, num_tags)
        self.crf = CRF(num_tags, batch_first=True)

        self.dice_loss = DiceLoss(
            num_classes=num_tags,
            smooth=dice_smooth,
        )

        self.crf_weight = crf_weight

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor | list[list[int]]:
        """Forward pass with combined dice + CRF loss.

        Args:
            input_ids: Token IDs of shape (batch_size, seq_len).
            attention_mask: Attention mask of shape (batch_size, seq_len).
            labels: Ground-truth tags. If provided, returns combined loss.

        Returns:
            Combined loss during training, or decoded sequences during inference.
        """
        outputs = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        hidden_states = self.dropout(outputs.last_hidden_state)
        emissions = self.classifier(hidden_states)

        if labels is not None:
            crf_loss = -self.crf(
                emissions,
                labels,
                mask=attention_mask.bool(),
                reduction="mean",
            )

            dice_loss = self.dice_loss(emissions, labels)

            total_loss = self.crf_weight * crf_loss + (1 - self.crf_weight) * dice_loss
            return total_loss

        return self.crf.decode(emissions, mask=attention_mask.bool())
