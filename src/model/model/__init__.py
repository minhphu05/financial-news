"""Model architectures for Vietnamese Financial Named Entity Recognition.

This package contains all neural network architectures for the ViFinNER task,
ranging from baseline models (BiLSTM, TextCNN) to advanced transformer-based
architectures with custom attention mechanisms and CRF decoders.

Models:
    - BiLSTM: Bidirectional LSTM baseline
    - BiLSTM_CRF: BiLSTM with Conditional Random Field decoder
    - BiLSTM_CRF_Pretrained: BiLSTM-CRF with pretrained embeddings (fastText)
    - TextCNN_NER: Token-level CNN for NER
    - XLMR_CRF: XLM-RoBERTa base + CRF
    - XLMR_Large_CRF: XLM-RoBERTa large + CRF
    - PhoBERT_CRF: PhoBERT + CRF (Vietnamese-specific)
    - XLMR_BiLSTM_CRF: XLM-RoBERTa + BiLSTM + CRF
    - XLMR_MultiHead_Attn_CRF: XLM-RoBERTa + Multi-Head Attention + CRF
    - XLMR_Adaptive_Fusion_CRF: XLM-RoBERTa + Adaptive Layer Fusion + CRF
    - FocalCRF_XLMR: XLM-RoBERTa + Focal Loss + CRF (class imbalance)
    - DiceLoss_XLMR: XLM-RoBERTa + Dice Loss (boundary-sensitive)
"""

try:
    from src.model.model.BiLSTM import BiLSTM
    from src.model.model.BiLSTM_CRF import BiLSTM_CRF
    from src.model.model.TextCNN import TextCNN_NER
    from src.model.model.XLM_R import XLMR_CRF
except ModuleNotFoundError:
    from model.BiLSTM import BiLSTM
    from model.BiLSTM_CRF import BiLSTM_CRF
    from model.TextCNN import TextCNN_NER
    from model.XLM_R import XLMR_CRF

__all__ = [
    "BiLSTM",
    "BiLSTM_CRF",
    "TextCNN_NER",
    "XLMR_CRF",
]
