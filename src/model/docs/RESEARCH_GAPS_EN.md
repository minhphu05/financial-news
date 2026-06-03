# Research Gap Analysis: Vietnamese Financial NER

## 1. Literature Review Summary

### 1.1 Existing Approaches for Vietnamese NER

| Paper | Model | Dataset | F1 Score | Limitations |
|-------|-------|---------|----------|-------------|
| Nguyen & Nguyen (2020) | PhoBERT + Softmax | VLSP 2018 | 93.5% | No CRF; general domain only |
| Truong et al. (2021) | XLM-R + CRF | PhoNER | 91.2% | Single last layer; no class balancing |
| Vu et al. (2022) | ViBERT + BiLSTM | VietNER | 89.7% | No attention refinement |
| Le et al. (2023) | mBERT + CRF | Financial NER | 87.3% | Standard loss; no domain adaptation |

### 1.2 International SOTA for NER

| Paper | Key Innovation | Impact |
|-------|---------------|--------|
| Yan et al. (2019) - TENER | Relative position in transformer attention | +1.2% F1 on CoNLL |
| Li et al. (2020) - Flat NER | Lattice transformer for Chinese NER | Handles word ambiguity |
| Yu et al. (2020) - Biaffine NER | Span-based with biaffine scoring | +2% on nested NER |
| Wang et al. (2021) - ACE | Automated concatenation of embeddings | +0.8% across datasets |
| Li et al. (2020) - Dice Loss | F1-optimizing loss for imbalanced NER | +3% recall on rare entities |

---

## 2. Identified Research Gaps

### Gap 1: Single-Layer Feature Extraction

**Problem**: All existing Vietnamese NER systems extract features from only the last transformer layer.

**Evidence**: BERT/XLM-R's different layers encode different linguistic information:
- Layers 1-4: Morphological features (word structure, affixes)
- Layers 5-8: Syntactic features (POS, dependency)
- Layers 9-12: Semantic features (entity types, relations)

**Our Solution**: Adaptive Layer Fusion with learned layer-wise attention weights.

**Why it matters for Vietnamese**: Vietnamese compound words (e.g., "Ngân hàng" = bank, "cổ phiếu" = stock) require morphological awareness from lower layers to correctly identify entity boundaries.

**Expected Improvement**: +1-2% F1, particularly on multi-syllable entities.

---

### Gap 2: Generic Transformer Self-Attention

**Problem**: Pre-trained self-attention learns general language patterns, not NER-specific entity boundary patterns.

**Evidence**: Analysis of attention heads in XLM-R shows that:
- Most heads attend to syntactically related tokens (subject-verb, noun-adjective)
- Very few heads naturally focus on entity-boundary-relevant tokens
- No heads encode entity-span-width information

**Our Solution**: Task-specific Multi-Head Attention with:
1. Relative position encoding (entity spans rarely exceed 5-7 tokens)
2. Gated residual connection to blend general and NER-specific features

**Why it matters for Vietnamese**: Vietnamese ORG names can be very long (e.g., "Ngân hàng Thương mại Cổ phần Á Châu" = 7 syllables). The relative position encoding helps the model learn that B-ORG tokens should attend to I-ORG tokens within typical span lengths.

**Expected Improvement**: +1-3% F1 on long-span entities (ORG, EVENT, ASSET).

---

### Gap 3: Uniform Loss Function

**Problem**: Standard CRF log-likelihood and cross-entropy treat all tokens equally, despite severe class imbalance.

**Evidence** (from our dataset analysis):
```
O:        ~82% of all tokens
B-ORG:    ~4%
I-ORG:    ~3%
B-DATE:   ~3%
I-DATE:   ~2%
B-RATE:   ~2%
B-MONEY:  ~1%
B-TICKER: ~0.5%
B-PRICE:  ~0.3%
B-VOLUME: ~0.3%
...
```

**Our Solution**: 
1. **Focal Loss**: Down-weights easy O-tokens (γ=2.0), focuses on hard entity boundaries
2. **Dice Loss**: Directly optimizes per-class F1 overlap metric

**Why it matters for Vietnamese finance**: Rare entities like TICKER (stock codes: FPT, VNM) and PRICE are critical for downstream financial applications but have extremely low frequency.

**Expected Improvement**: +3-5% recall on rare entities (TICKER, PRICE, VOLUME).

---

### Gap 4: BIO Tagging Error Propagation

**Problem**: A single boundary error in BIO tagging corrupts the entire entity extraction.

**Example**:
```
Prediction: B-ORG  I-ORG  O      I-ORG  I-ORG
Ground:     B-ORG  I-ORG  I-ORG  I-ORG  I-ORG
                          ↑ Single error → entity split into two partial entities
```

**Our Solution**: Span-based NER with biaffine scoring that directly predicts (start, end, type) triples.

**Why it matters for Vietnamese**: The syllable-separated writing system means that a single "word" entity like "Ngân hàng" occupies 2 tokens. A boundary error between syllables of the same word is common and devastating in BIO schemes.

**Expected Improvement**: +2-4% exact-match F1 on entity extraction.

---

### Gap 5: Missing Encoder-Decoder Bridge

**Problem**: Direct projection from transformer output to CRF emissions may lose structural information about sequence patterns.

**Evidence**: Transformer outputs are contextual but not explicitly sequential — the self-attention mechanism has no inherent bias toward left-to-right processing. CRF benefits from explicitly sequential input.

**Our Solution**: BiLSTM refinement layer between transformer and CRF that:
1. Adds explicit left-right sequential bias
2. Provides task-specific feature refinement
3. Reduces the dimensionality gap between 768-dim transformer and CRF

**Expected Improvement**: +0.5-1.5% F1 from better emission quality.

---

## 3. Methodology Comparison

### 3.1 Model Complexity Analysis

| Model | Parameters | Training Time (est.) | Inference Speed |
|-------|-----------|---------------------|-----------------|
| BiLSTM + CRF | ~5M | Fast (minutes) | Very Fast |
| XLM-R Base + CRF | ~278M | Moderate (hours) | Moderate |
| XLM-R + BiLSTM + CRF | ~280M | Moderate | Moderate |
| XLM-R + Attention + CRF | ~285M | Moderate-High | Moderate |
| XLM-R + Adaptive Fusion + CRF | ~278M + 12 params | Moderate | Moderate |
| Focal-CRF + XLM-R | ~278M | Moderate | Moderate |
| XLM-R + Span (Biaffine) | ~290M | High | Slower |

### 3.2 Theoretical Advantages

| Model | Class Balance | Long Spans | Vietnamese Morphology | Label Dependencies |
|-------|:---:|:---:|:---:|:---:|
| BiLSTM + CRF | ✗ | ✗ | ✗ | ✓ |
| XLM-R + CRF | ✗ | ○ | ○ | ✓ |
| XLM-R + BiLSTM + CRF | ✗ | ○ | ○ | ✓✓ |
| XLM-R + Attention + CRF | ✗ | ✓ | ○ | ✓ |
| XLM-R + Adaptive Fusion | ✗ | ○ | ✓ | ✓ |
| Focal-CRF + XLM-R | ✓ | ○ | ○ | ✓ |
| Dice Loss + XLM-R | ✓ | ○ | ○ | ✓ |
| XLM-R + Span | ○ | ✓ | ✓ | N/A |

Legend: ✓ = strong, ○ = moderate, ✗ = weak, ✓✓ = very strong

---

## 4. Experimental Design

### 4.1 Evaluation Metrics
- **Token-level F1**: Standard micro/macro/weighted F1 on BIO tags
- **Entity-level F1**: Strict match (both boundary AND type must be correct)
- **Per-class F1**: Individual performance on each entity type
- **Recall on rare entities**: Specifically measure TICKER, PRICE, VOLUME recall

### 4.2 Ablation Studies

1. **Layer Fusion Ablation**: Compare last-layer vs. first-4 vs. all-layers fusion
2. **Attention Head Ablation**: 2, 4, 8, 16 attention heads
3. **Loss Weight Ablation**: CRF weight λ ∈ {0.3, 0.5, 0.7}
4. **Focal Gamma Ablation**: γ ∈ {0.5, 1.0, 2.0, 3.0}
5. **BiLSTM Depth Ablation**: 1, 2, 3 BiLSTM layers

### 4.3 Statistical Significance
- Run each model 5 times with different random seeds
- Report mean ± std of F1 scores
- Conduct paired t-test between baseline and each advanced model

---

## 5. Summary of Contributions

1. **First comprehensive study** of advanced NER architectures for Vietnamese financial text
2. **Adaptive Layer Fusion** for exploiting morphological features in lower transformer layers
3. **NER-specific attention** with relative position encoding for entity span awareness
4. **Loss function engineering** (Focal + Dice) addressing >80% O-tag dominance
5. **Span-based approach** eliminating BIO error propagation for Vietnamese syllable-separated text
6. **Hybrid BiLSTM-Transformer** bridging contextual embeddings and structured prediction
7. **Complete benchmark** comparing 13 models on Vietnamese financial NER
