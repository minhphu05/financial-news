# Vietnamese Financial Named Entity Recognition (ViFinNER)

## Model Architecture Documentation

### Overview

This project implements Named Entity Recognition (NER) for Vietnamese financial news text, targeting **10 entity types** organized in a BIO tagging scheme (15 tags total):

| Entity Type | Description | Example |
|-------------|-------------|---------|
| PERSON | Named individuals | Từ Tiến Phát |
| ORG | Organizations, banks, companies | ACB, Ngân hàng TMCP Á Châu |
| ASSET | Financial instruments | cổ phiếu, trái phiếu, CCTG |
| EVENT | Financial events | ACB ra mắt Chứng chỉ tiền gửi |
| MONEY | Monetary values | 6.621 đồng, 98 tỷ đồng |
| DATE | Temporal expressions | tháng 10/2025, năm 2026 |
| RATE | Interest/percentage rates | 4,5%/năm, 50% |
| TICKER | Stock ticker symbols | FPT, ACB |
| VOLUME | Trading volumes | 30.000 cổ phiếu |
| PRICE | Stock prices | 50.000 đồng/CP |

### Data Pipeline

```
Raw News Articles (CafeF) → Span Annotation (LLM-assisted) → BIO Conversion → Syllable Tokenization → Model Training
```

#### Data Splits
- **Train**: 70% of annotated samples
- **Dev**: 15% for hyperparameter tuning
- **Test**: 15% for final evaluation

#### Tokenization Strategy
Vietnamese text is tokenized at the **syllable level** (space-separated), consistent with PhoBERT and ViFinNER conventions. Multi-syllable words (e.g., "Ngân hàng" = bank) span multiple tokens.

---

## Model Architectures

### Baseline Models

#### 1. BiLSTM (No CRF)
- **Architecture**: Embedding → BiLSTM → Linear → Softmax
- **Purpose**: Simplest neural baseline; token-independent classification
- **Limitation**: No label dependency modeling

#### 2. BiLSTM + CRF
- **Architecture**: Embedding → BiLSTM → Linear → CRF
- **Improvement**: CRF decoder enforces valid label transitions (e.g., I-ORG can only follow B-ORG or I-ORG)
- **Config**: `config/bilstm_crf.yaml`

#### 3. BiLSTM + CRF + Pretrained Embeddings (fastText)
- **Architecture**: fastText Embedding → BiLSTM → Linear → CRF
- **Improvement**: Pretrained Vietnamese fastText embeddings provide better initial representations
- **Config**: `config/bilstm_crf_pretrained_embedding.yaml`

#### 4. TextCNN NER
- **Architecture**: Embedding → Multi-kernel Conv1D → Linear
- **Purpose**: CNN baseline capturing local n-gram patterns for NER
- **Config**: `config/textcnn.yaml`

---

### Transformer-Based Models

#### 5. XLM-RoBERTa Base + CRF
- **Architecture**: XLM-RoBERTa (768-dim, 12 layers) → Dropout → Linear → CRF
- **Strength**: Multilingual contextual embeddings with cross-lingual transfer
- **File**: `model/XLM_R.py`

#### 6. XLM-RoBERTa Large + CRF
- **Architecture**: XLM-RoBERTa (1024-dim, 24 layers) → Dropout → Linear → CRF
- **Strength**: Higher capacity for complex entity patterns
- **File**: `model/XLMR_Large.py`

#### 7. PhoBERT + CRF
- **Architecture**: PhoBERT-v2 → Dropout → Linear → CRF
- **Strength**: Vietnamese-specific pre-training; captures Vietnamese morphology
- **File**: `model/PhoBERT_CRF.py`

---

### Advanced Models (Our Contributions)

#### 8. XLM-RoBERTa + BiLSTM + CRF (Hybrid)
- **Architecture**: XLM-RoBERTa → BiLSTM → LayerNorm → Dropout → Linear → CRF
- **Innovation**: BiLSTM refinement layer captures task-specific sequential patterns
- **Research Gap**: Bridges the gap between contextual embeddings and structured prediction
- **File**: `model/XLMR_BiLSTM_CRF.py`

#### 9. XLM-RoBERTa + Multi-Head Attention + CRF
- **Architecture**: XLM-RoBERTa → NER-specific Multi-Head Attention → Linear → CRF
- **Key Features**:
  - Relative position encoding for entity span awareness
  - Gated residual connection for feature blending
- **Research Gap**: Task-specific attention learns entity-boundary patterns that generic transformer attention doesn't capture
- **File**: `model/XLMR_MultiHead_Attn_CRF.py`

#### 10. XLM-RoBERTa + Adaptive Layer Fusion + CRF
- **Architecture**: XLM-RoBERTa (all layers) → Adaptive Weighted Fusion → Linear → CRF
- **Innovation**: Learns optimal combination of ALL transformer layers (not just the last)
- **Research Gap**: Lower layers capture morphological features critical for Vietnamese compound word entities; adaptive fusion exploits this
- **File**: `model/XLMR_Adaptive_Fusion_CRF.py`

#### 11. Focal-CRF + XLM-RoBERTa
- **Architecture**: XLM-RoBERTa → Linear → Focal Loss + CRF Loss
- **Innovation**: Addresses severe O-tag dominance (>80% of tokens) with focal loss
- **Research Gap**: Standard CRF log-likelihood is biased towards majority class; focal weighting focuses on hard entity-boundary tokens
- **File**: `model/loss_models.py`

#### 12. Dice Loss + CRF + XLM-RoBERTa
- **Architecture**: XLM-RoBERTa → Linear → Dice Loss + CRF Loss
- **Innovation**: Directly optimizes F1-like overlap metric per entity class
- **Research Gap**: Provides balanced gradients regardless of class frequency; especially effective for rare entities (TICKER, PRICE)
- **File**: `model/loss_models.py`

#### 13. Span-Based NER (Biaffine)
- **Architecture**: XLM-RoBERTa → Start/End FFN → Biaffine Scorer → Span Classification
- **Innovation**: Directly predicts entity spans instead of BIO tags
- **Research Gap**: Eliminates BIO error propagation; robust for Vietnamese text with ambiguous word boundaries
- **File**: `model/XLMR_Span_NER.py`

---

## Research Gap Analysis

### Problem Statement
Vietnamese financial NER faces three key challenges:

1. **Class Imbalance**: O-tag dominates (>80%); rare entities (TICKER, PRICE) have <2% occurrence
2. **Variable-length Entities**: ORG names span 2-8 syllables; DATE expressions vary widely
3. **Vietnamese Morphology**: Syllable-separated writing system creates ambiguous word boundaries

### Gaps in Existing Literature

| Gap | Existing Approach | Our Contribution |
|-----|-------------------|------------------|
| Single-layer usage | Use only last transformer layer | Adaptive Layer Fusion across ALL layers |
| Generic attention | Rely on pre-trained self-attention | Task-specific NER attention with relative position |
| Uniform loss | Standard CRF log-likelihood | Focal Loss + Dice Loss for class balance |
| BIO error propagation | All models use BIO tagging | Span-based model eliminates cascading errors |
| Encoder-decoder gap | Direct linear → CRF | BiLSTM refinement bridges transformer and CRF |
| Vietnamese-specific | Multilingual models only | PhoBERT + multilingual comparison |

### Expected Impact
- **Adaptive Fusion**: +1-2% F1 by leveraging lower-layer morphological features
- **NER Attention**: +1-3% F1 on long-span entities (ORG, EVENT)
- **Focal/Dice Loss**: +3-5% recall on rare entity types (TICKER, PRICE)
- **Span-based**: +2-4% exact-match F1 by avoiding boundary errors

---

## Project Structure

```
src/model/
├── config/                     # YAML configuration files
│   ├── advanced_models.yaml    # Advanced model configs
│   ├── bilstm_crf.yaml
│   ├── bilstm_crf_pretrained_embedding.yaml
│   └── textcnn.yaml
├── DataUtils/                  # Dataset and vocabulary utilities
│   ├── NER_dataset.py          # Vocab, Dataset, collate_fn for BiLSTM models
│   ├── xlmr_dataset.py         # NERDataset for transformer models
│   ├── xlmr_large_dataset.py   # NERDataset for XLM-R Large
│   └── embeddings.py           # fastText embedding matrix builder
├── docs/                       # Documentation (EN + VI)
├── model/                      # Neural network architectures
│   ├── BiLSTM.py               # Baseline BiLSTM
│   ├── BiLSTM_CRF.py           # BiLSTM + CRF
│   ├── BiLSTM_CRF_Pretrained_Embedding.py
│   ├── TextCNN.py              # CNN baseline
│   ├── XLM_R.py                # XLM-RoBERTa Base + CRF
│   ├── XLMR_Large.py           # XLM-RoBERTa Large + CRF
│   ├── PhoBERT_CRF.py          # PhoBERT + CRF
│   ├── XLMR_BiLSTM_CRF.py     # Hybrid: XLM-R + BiLSTM + CRF
│   ├── XLMR_MultiHead_Attn_CRF.py  # NER-specific attention
│   ├── XLMR_Adaptive_Fusion_CRF.py # Adaptive layer fusion
│   ├── XLMR_Span_NER.py        # Span-based biaffine NER
│   └── loss_models.py          # Focal Loss + Dice Loss models
├── training/                   # Training scripts
│   ├── train_advanced.py       # Unified trainer for all advanced models
│   ├── train_bilstm_crf.py     # BiLSTM-CRF trainer
│   ├── train_xlmr_crf.py       # XLM-R CRF trainer
│   └── ...
└── preprocessing/              # Data preprocessing pipelines
    ├── medallion/              # Bronze-Silver-Gold data pipeline
    └── ...
```

---

## Usage

### Training Advanced Models

```bash
# XLM-RoBERTa + BiLSTM + CRF
python training/train_advanced.py --model xlmr_bilstm_crf --lr 3e-5 --epochs 30

# XLM-RoBERTa + Multi-Head Attention + CRF
python training/train_advanced.py --model xlmr_multihead_attn_crf --num_attn_heads 8

# XLM-RoBERTa + Adaptive Layer Fusion + CRF
python training/train_advanced.py --model xlmr_adaptive_fusion_crf

# Focal Loss + CRF (for class imbalance)
python training/train_advanced.py --model focal_crf_xlmr --focal_gamma 2.0

# Dice Loss + CRF (boundary-sensitive)
python training/train_advanced.py --model dice_loss_xlmr --crf_weight 0.5

# PhoBERT + CRF (Vietnamese-specific)
python training/train_advanced.py --model phobert_crf --lr 2e-5 --max_len 256
```

### Dependencies

```
torch>=2.0
transformers>=4.30
pytorch-crf>=0.7.2
scikit-learn>=1.0
numpy
tqdm
pyyaml
```

---

## References

1. Conneau et al. (2020). "Unsupervised Cross-lingual Representation Learning at Scale." ACL.
2. Nguyen & Nguyen (2020). "PhoBERT: Pre-trained language models for Vietnamese." EMNLP Findings.
3. Huang et al. (2015). "Bidirectional LSTM-CRF Models for Sequence Tagging." arXiv.
4. Vaswani et al. (2017). "Attention Is All You Need." NeurIPS.
5. Lin et al. (2017). "Focal Loss for Dense Object Detection." ICCV.
6. Li et al. (2020). "Dice Loss for Data-imbalanced NLP Tasks." ACL.
7. Yan et al. (2019). "TENER: Adapting Transformer Encoder for NER." arXiv.
8. Yu et al. (2020). "Named Entity Recognition as Dependency Parsing." ACL.
9. Zhong & Chen (2021). "A Frustratingly Easy Approach for Entity and Relation Extraction." NAACL.
10. Peters et al. (2018). "Deep contextualized word representations (ELMo)." NAACL.
