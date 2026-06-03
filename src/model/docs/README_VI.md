# Nhận dạng Thực thể có Tên trong Tin tức Tài chính Việt Nam (ViFinNER)

## Tài liệu Kiến trúc Mô hình

### Tổng quan

Dự án này triển khai bài toán Nhận dạng Thực thể có Tên (NER) cho văn bản tin tức tài chính tiếng Việt, nhắm tới **10 loại thực thể** được tổ chức theo lược đồ gán nhãn BIO (tổng cộng 15 nhãn):

| Loại Thực thể | Mô tả | Ví dụ |
|---------------|--------|-------|
| PERSON | Cá nhân có tên | Từ Tiến Phát |
| ORG | Tổ chức, ngân hàng, công ty | ACB, Ngân hàng TMCP Á Châu |
| ASSET | Công cụ tài chính | cổ phiếu, trái phiếu, CCTG |
| EVENT | Sự kiện tài chính | ACB ra mắt Chứng chỉ tiền gửi |
| MONEY | Giá trị tiền tệ | 6.621 đồng, 98 tỷ đồng |
| DATE | Biểu thức thời gian | tháng 10/2025, năm 2026 |
| RATE | Lãi suất/tỷ lệ phần trăm | 4,5%/năm, 50% |
| TICKER | Mã cổ phiếu | FPT, ACB |
| VOLUME | Khối lượng giao dịch | 30.000 cổ phiếu |
| PRICE | Giá cổ phiếu | 50.000 đồng/CP |

### Luồng Dữ liệu

```
Bài báo thô (CafeF) → Gán nhãn Span (hỗ trợ bởi LLM) → Chuyển đổi BIO → Tách âm tiết → Huấn luyện mô hình
```

#### Phân chia Dữ liệu
- **Train**: 70% mẫu đã gán nhãn
- **Dev**: 15% để tinh chỉnh siêu tham số
- **Test**: 15% để đánh giá cuối cùng

#### Chiến lược Tokenization
Văn bản tiếng Việt được tokenize ở cấp **âm tiết** (phân tách bằng dấu cách), phù hợp với PhoBERT và quy ước ViFinNER. Các từ đa âm tiết (ví dụ: "Ngân hàng" = bank) trải dài qua nhiều token.

---

## Kiến trúc Mô hình

### Mô hình Cơ sở (Baseline)

#### 1. BiLSTM (Không có CRF)
- **Kiến trúc**: Embedding → BiLSTM → Linear → Softmax
- **Mục đích**: Baseline đơn giản nhất; phân loại từng token độc lập
- **Hạn chế**: Không mô hình hóa phụ thuộc nhãn

#### 2. BiLSTM + CRF
- **Kiến trúc**: Embedding → BiLSTM → Linear → CRF
- **Cải tiến**: CRF decoder ràng buộc chuyển đổi nhãn hợp lệ (ví dụ: I-ORG chỉ có thể theo sau B-ORG hoặc I-ORG)
- **Cấu hình**: `config/bilstm_crf.yaml`

#### 3. BiLSTM + CRF + Pretrained Embeddings (fastText)
- **Kiến trúc**: fastText Embedding → BiLSTM → Linear → CRF
- **Cải tiến**: Embedding fastText tiếng Việt cung cấp biểu diễn ban đầu tốt hơn
- **Cấu hình**: `config/bilstm_crf_pretrained_embedding.yaml`

#### 4. TextCNN NER
- **Kiến trúc**: Embedding → Multi-kernel Conv1D → Linear
- **Mục đích**: Baseline CNN bắt mẫu n-gram cục bộ cho NER
- **Cấu hình**: `config/textcnn.yaml`

---

### Mô hình dựa trên Transformer

#### 5. XLM-RoBERTa Base + CRF
- **Kiến trúc**: XLM-RoBERTa (768-dim, 12 lớp) → Dropout → Linear → CRF
- **Điểm mạnh**: Embedding ngữ cảnh đa ngôn ngữ với khả năng chuyển giao liên ngôn ngữ
- **File**: `model/XLM_R.py`

#### 6. XLM-RoBERTa Large + CRF
- **Kiến trúc**: XLM-RoBERTa (1024-dim, 24 lớp) → Dropout → Linear → CRF
- **Điểm mạnh**: Dung lượng cao hơn cho các mẫu thực thể phức tạp
- **File**: `model/XLMR_Large.py`

#### 7. PhoBERT + CRF
- **Kiến trúc**: PhoBERT-v2 → Dropout → Linear → CRF
- **Điểm mạnh**: Huấn luyện trước đặc thù tiếng Việt; nắm bắt hình thái học tiếng Việt
- **File**: `model/PhoBERT_CRF.py`

---

### Mô hình Nâng cao (Đóng góp của Chúng tôi)

#### 8. XLM-RoBERTa + BiLSTM + CRF (Lai ghép)
- **Kiến trúc**: XLM-RoBERTa → BiLSTM → LayerNorm → Dropout → Linear → CRF
- **Đổi mới**: Lớp tinh chỉnh BiLSTM nắm bắt mẫu tuần tự đặc thù nhiệm vụ
- **Khoảng trống nghiên cứu**: Cầu nối giữa embedding ngữ cảnh và dự đoán có cấu trúc
- **File**: `model/XLMR_BiLSTM_CRF.py`

#### 9. XLM-RoBERTa + Multi-Head Attention + CRF
- **Kiến trúc**: XLM-RoBERTa → NER Multi-Head Attention đặc thù → Linear → CRF
- **Đặc điểm chính**:
  - Mã hóa vị trí tương đối cho nhận biết khoảng thực thể
  - Kết nối residual có cổng (gated) cho pha trộn đặc trưng
- **Khoảng trống nghiên cứu**: Attention đặc thù nhiệm vụ học các mẫu ranh giới thực thể mà attention transformer chung không nắm bắt được
- **File**: `model/XLMR_MultiHead_Attn_CRF.py`

#### 10. XLM-RoBERTa + Adaptive Layer Fusion + CRF
- **Kiến trúc**: XLM-RoBERTa (tất cả các lớp) → Hợp nhất có trọng số Thích ứng → Linear → CRF
- **Đổi mới**: Học tổ hợp tối ưu của TẤT CẢ các lớp transformer (không chỉ lớp cuối)
- **Khoảng trống nghiên cứu**: Các lớp thấp nắm bắt đặc trưng hình thái học quan trọng cho từ ghép tiếng Việt; hợp nhất thích ứng khai thác điều này
- **File**: `model/XLMR_Adaptive_Fusion_CRF.py`

#### 11. Focal-CRF + XLM-RoBERTa
- **Kiến trúc**: XLM-RoBERTa → Linear → Focal Loss + CRF Loss
- **Đổi mới**: Giải quyết sự thống trị nghiêm trọng của O-tag (>80% token) bằng focal loss
- **Khoảng trống nghiên cứu**: CRF log-likelihood chuẩn thiên lệch về lớp đa số; trọng số focal tập trung vào các token ranh giới thực thể khó
- **File**: `model/loss_models.py`

#### 12. Dice Loss + CRF + XLM-RoBERTa
- **Kiến trúc**: XLM-RoBERTa → Linear → Dice Loss + CRF Loss
- **Đổi mới**: Tối ưu hóa trực tiếp metric chồng lấn giống F1 cho mỗi lớp thực thể
- **Khoảng trống nghiên cứu**: Cung cấp gradient cân bằng bất kể tần suất lớp; đặc biệt hiệu quả cho thực thể hiếm (TICKER, PRICE)
- **File**: `model/loss_models.py`

#### 13. NER dựa trên Span (Biaffine)
- **Kiến trúc**: XLM-RoBERTa → Start/End FFN → Biaffine Scorer → Phân loại Span
- **Đổi mới**: Dự đoán trực tiếp khoảng thực thể thay vì nhãn BIO
- **Khoảng trống nghiên cứu**: Loại bỏ lan truyền lỗi BIO; mạnh mẽ cho tiếng Việt với ranh giới từ không rõ ràng
- **File**: `model/XLMR_Span_NER.py`

---

## Phân tích Khoảng trống Nghiên cứu

### Phát biểu Vấn đề
NER tài chính tiếng Việt đối mặt với ba thách thức chính:

1. **Mất cân bằng lớp**: O-tag thống trị (>80%); thực thể hiếm (TICKER, PRICE) có <2% tần suất
2. **Thực thể có độ dài biến thiên**: Tên tổ chức trải dài 2-8 âm tiết; biểu thức thời gian đa dạng
3. **Hình thái học tiếng Việt**: Hệ thống viết phân tách âm tiết tạo ranh giới từ không rõ ràng

### Khoảng trống trong Tài liệu Hiện có

| Khoảng trống | Phương pháp Hiện có | Đóng góp của Chúng tôi |
|--------------|---------------------|------------------------|
| Sử dụng đơn lớp | Chỉ dùng lớp transformer cuối | Hợp nhất thích ứng qua TẤT CẢ các lớp |
| Attention chung | Dựa vào self-attention đã huấn luyện trước | Attention NER đặc thù với vị trí tương đối |
| Loss đồng nhất | CRF log-likelihood chuẩn | Focal Loss + Dice Loss cho cân bằng lớp |
| Lan truyền lỗi BIO | Tất cả mô hình dùng gán nhãn BIO | Mô hình span loại bỏ lỗi tầng |
| Khoảng cách encoder-decoder | Linear trực tiếp → CRF | Tinh chỉnh BiLSTM cầu nối transformer và CRF |
| Đặc thù tiếng Việt | Chỉ mô hình đa ngôn ngữ | PhoBERT + so sánh đa ngôn ngữ |

### Tác động Dự kiến
- **Hợp nhất thích ứng**: +1-2% F1 nhờ khai thác đặc trưng hình thái ở lớp thấp
- **NER Attention**: +1-3% F1 trên thực thể dài (ORG, EVENT)
- **Focal/Dice Loss**: +3-5% recall trên loại thực thể hiếm (TICKER, PRICE)
- **Dựa trên Span**: +2-4% exact-match F1 nhờ tránh lỗi ranh giới

---

## Cấu trúc Dự án

```
src/model/
├── config/                     # File cấu hình YAML
│   ├── advanced_models.yaml    # Cấu hình mô hình nâng cao
│   ├── bilstm_crf.yaml
│   ├── bilstm_crf_pretrained_embedding.yaml
│   └── textcnn.yaml
├── DataUtils/                  # Tiện ích dataset và từ vựng
│   ├── NER_dataset.py          # Vocab, Dataset, collate_fn cho mô hình BiLSTM
│   ├── xlmr_dataset.py         # NERDataset cho mô hình transformer
│   ├── xlmr_large_dataset.py   # NERDataset cho XLM-R Large
│   └── embeddings.py           # Xây dựng ma trận embedding fastText
├── docs/                       # Tài liệu (EN + VI)
├── model/                      # Kiến trúc mạng nơ-ron
│   ├── BiLSTM.py               # Baseline BiLSTM
│   ├── BiLSTM_CRF.py           # BiLSTM + CRF
│   ├── BiLSTM_CRF_Pretrained_Embedding.py
│   ├── TextCNN.py              # Baseline CNN
│   ├── XLM_R.py                # XLM-RoBERTa Base + CRF
│   ├── XLMR_Large.py           # XLM-RoBERTa Large + CRF
│   ├── PhoBERT_CRF.py          # PhoBERT + CRF
│   ├── XLMR_BiLSTM_CRF.py     # Lai ghép: XLM-R + BiLSTM + CRF
│   ├── XLMR_MultiHead_Attn_CRF.py  # Attention đặc thù NER
│   ├── XLMR_Adaptive_Fusion_CRF.py # Hợp nhất lớp thích ứng
│   ├── XLMR_Span_NER.py        # NER dựa trên span biaffine
│   └── loss_models.py          # Mô hình Focal Loss + Dice Loss
├── training/                   # Script huấn luyện
│   ├── train_advanced.py       # Trainer thống nhất cho tất cả mô hình nâng cao
│   ├── train_bilstm_crf.py     # Trainer BiLSTM-CRF
│   ├── train_xlmr_crf.py       # Trainer XLM-R CRF
│   └── ...
└── preprocessing/              # Pipeline tiền xử lý dữ liệu
    ├── medallion/              # Pipeline dữ liệu Bronze-Silver-Gold
    └── ...
```

---

## Hướng dẫn Sử dụng

### Huấn luyện Mô hình Nâng cao

```bash
# XLM-RoBERTa + BiLSTM + CRF
python training/train_advanced.py --model xlmr_bilstm_crf --lr 3e-5 --epochs 30

# XLM-RoBERTa + Multi-Head Attention + CRF
python training/train_advanced.py --model xlmr_multihead_attn_crf --num_attn_heads 8

# XLM-RoBERTa + Adaptive Layer Fusion + CRF
python training/train_advanced.py --model xlmr_adaptive_fusion_crf

# Focal Loss + CRF (cho mất cân bằng lớp)
python training/train_advanced.py --model focal_crf_xlmr --focal_gamma 2.0

# Dice Loss + CRF (nhạy cảm với ranh giới)
python training/train_advanced.py --model dice_loss_xlmr --crf_weight 0.5

# PhoBERT + CRF (đặc thù tiếng Việt)
python training/train_advanced.py --model phobert_crf --lr 2e-5 --max_len 256
```

### Thư viện Phụ thuộc

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

## Tài liệu Tham khảo

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
