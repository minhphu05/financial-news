"""XLM-RoBERTa + Multi-Head Attention + CRF for Vietnamese Financial NER.

This model introduces a task-specific multi-head self-attention layer between
the pre-trained encoder and the CRF decoder. Unlike the transformer's internal
attention (which is trained for general language modeling), this additional
attention layer is trained specifically for the NER objective, allowing it to
learn entity-boundary-aware attention patterns.

Research Gap:
    Standard fine-tuning applies a single linear projection on transformer
    outputs before CRF decoding. This ignores the potential for learning
    NER-specific inter-token relationships. Our multi-head attention module
    explicitly models which tokens should attend to each other for entity
    boundary detection — e.g., a B-ORG token attending to subsequent I-ORG
    tokens to reinforce entity continuity.

Key Innovation:
    - Relative position encoding in attention captures distance-based entity
      span patterns (entities rarely exceed 5-7 tokens in Vietnamese finance).
    - Gated residual connection allows the model to selectively blend
      transformer features with attention-refined features.

Reference:
    - Vaswani et al. (2017). Attention Is All You Need.
    - Yan et al. (2019). TENER: Adapting Transformer Encoder for NER.
    - Li et al. (2020). Unified Named Entity Recognition as Word-Word Relation.
"""

import math

import torch
from torch import nn
from transformers import AutoModel
from torchcrf import CRF


class RelativePositionEncoding(nn.Module):
    """Learnable relative position bias for attention scores.

    Encodes the relative distance between query and key positions, providing
    the attention mechanism with explicit positional information about token
    proximity — critical for entity span boundary detection.

    Args:
        max_relative_position: Maximum relative distance to encode.
        num_heads: Number of attention heads.
    """

    def __init__(self, max_relative_position: int = 64, num_heads: int = 8) -> None:
        super().__init__()
        self.max_relative_position = max_relative_position
        vocab_size = 2 * max_relative_position + 1
        self.embeddings = nn.Embedding(vocab_size, num_heads)

    def forward(self, seq_len: int) -> torch.Tensor:
        """Compute relative position bias matrix.

        Args:
            seq_len: Length of the input sequence.

        Returns:
            Position bias tensor of shape (1, num_heads, seq_len, seq_len).
        """
        positions = torch.arange(seq_len, dtype=torch.long, device=self.embeddings.weight.device)
        relative_positions = positions.unsqueeze(0) - positions.unsqueeze(1)
        relative_positions = relative_positions.clamp(
            -self.max_relative_position, self.max_relative_position
        )
        relative_positions = relative_positions + self.max_relative_position

        bias = self.embeddings(relative_positions)
        return bias.permute(2, 0, 1).unsqueeze(0)


class NERMultiHeadAttention(nn.Module):
    """Task-specific multi-head attention with relative position encoding.

    Unlike standard transformer self-attention, this module:
    1. Uses learnable relative position bias for entity-span modeling.
    2. Applies a gated residual connection for feature blending.

    Args:
        hidden_size: Input and output dimension.
        num_heads: Number of parallel attention heads.
        dropout: Attention dropout probability.
        max_relative_position: Maximum relative distance for position encoding.
    """

    def __init__(
        self,
        hidden_size: int = 768,
        num_heads: int = 8,
        dropout: float = 0.1,
        max_relative_position: int = 64,
    ) -> None:
        super().__init__()

        assert hidden_size % num_heads == 0, "hidden_size must be divisible by num_heads"

        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads
        self.scale = math.sqrt(self.head_dim)

        self.query = nn.Linear(hidden_size, hidden_size)
        self.key = nn.Linear(hidden_size, hidden_size)
        self.value = nn.Linear(hidden_size, hidden_size)
        self.output_proj = nn.Linear(hidden_size, hidden_size)

        self.relative_position = RelativePositionEncoding(
            max_relative_position=max_relative_position,
            num_heads=num_heads,
        )

        self.attn_dropout = nn.Dropout(dropout)
        self.layer_norm = nn.LayerNorm(hidden_size)

        # Gated residual connection
        self.gate = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.Sigmoid(),
        )

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Apply multi-head attention with relative position bias and gated residual.

        Args:
            hidden_states: Input tensor of shape (batch_size, seq_len, hidden_size).
            attention_mask: Mask of shape (batch_size, seq_len). 0 = masked position.

        Returns:
            Attention-refined tensor of shape (batch_size, seq_len, hidden_size).
        """
        batch_size, seq_len, _ = hidden_states.shape
        residual = hidden_states

        q = self.query(hidden_states).view(batch_size, seq_len, self.num_heads, self.head_dim)
        k = self.key(hidden_states).view(batch_size, seq_len, self.num_heads, self.head_dim)
        v = self.value(hidden_states).view(batch_size, seq_len, self.num_heads, self.head_dim)

        q = q.transpose(1, 2)  # (B, H, T, D)
        k = k.transpose(1, 2)
        v = v.transpose(1, 2)

        # Scaled dot-product attention
        attn_scores = torch.matmul(q, k.transpose(-2, -1)) / self.scale

        # Add relative position bias
        position_bias = self.relative_position(seq_len)
        attn_scores = attn_scores + position_bias

        # Apply attention mask
        if attention_mask is not None:
            extended_mask = attention_mask.unsqueeze(1).unsqueeze(2)
            attn_scores = attn_scores.masked_fill(extended_mask == 0, float("-inf"))

        attn_weights = torch.softmax(attn_scores, dim=-1)
        attn_weights = self.attn_dropout(attn_weights)

        context = torch.matmul(attn_weights, v)
        context = context.transpose(1, 2).contiguous().view(batch_size, seq_len, -1)
        context = self.output_proj(context)

        # Gated residual connection
        gate_input = torch.cat([residual, context], dim=-1)
        gate_value = self.gate(gate_input)
        output = gate_value * context + (1 - gate_value) * residual

        output = self.layer_norm(output)
        return output


class XLMR_MultiHead_Attn_CRF(nn.Module):
    """XLM-RoBERTa + NER-specific Multi-Head Attention + CRF.

    Architecture:
        Input -> XLM-RoBERTa -> NER Multi-Head Attention -> Dropout -> Linear -> CRF

    The task-specific attention layer learns entity-boundary-aware patterns
    that complement the pre-trained encoder's general language representations.

    Args:
        num_tags: Number of NER tag classes.
        model_name: HuggingFace model identifier.
        num_attn_heads: Number of attention heads in NER attention layer.
        attn_dropout: Dropout in the attention module.
        classifier_dropout: Dropout before the classifier.
        freeze_encoder: Whether to freeze XLM-RoBERTa weights.
    """

    def __init__(
        self,
        num_tags: int,
        model_name: str = "xlm-roberta-base",
        num_attn_heads: int = 8,
        attn_dropout: float = 0.1,
        classifier_dropout: float = 0.3,
        freeze_encoder: bool = False,
    ) -> None:
        super().__init__()

        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size

        if freeze_encoder:
            for param in self.encoder.parameters():
                param.requires_grad = False

        self.ner_attention = NERMultiHeadAttention(
            hidden_size=hidden_size,
            num_heads=num_attn_heads,
            dropout=attn_dropout,
        )

        self.dropout = nn.Dropout(classifier_dropout)
        self.classifier = nn.Linear(hidden_size, num_tags)
        self.crf = CRF(num_tags, batch_first=True)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor | list[list[int]]:
        """Forward pass with NER attention refinement and CRF decoding.

        Args:
            input_ids: Token IDs of shape (batch_size, seq_len).
            attention_mask: Attention mask of shape (batch_size, seq_len).
            labels: Ground-truth tags. If provided, returns loss.

        Returns:
            Loss tensor during training, or decoded tag sequences during inference.
        """
        encoder_output = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        hidden_states = encoder_output.last_hidden_state
        refined = self.ner_attention(hidden_states, attention_mask)
        refined = self.dropout(refined)
        emissions = self.classifier(refined)

        if labels is not None:
            loss = -self.crf(
                emissions,
                labels,
                mask=attention_mask.bool(),
                reduction="mean",
            )
            return loss

        return self.crf.decode(emissions, mask=attention_mask.bool())
