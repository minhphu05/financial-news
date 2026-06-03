# Phân tích Khoảng trống Nghiên cứu: NER Tài chính Tiếng Việt

## 1. Tổng quan Tài liệu Tham khảo

### 1.1 Các Phương pháp Hiện có cho NER Tiếng Việt

| Bài báo | Mô hình | Bộ dữ liệu | Điểm F1 | Hạn chế |
|---------|---------|-------------|----------|---------|
| Nguyen & Nguyen (2020) | PhoBERT + Softmax | VLSP 2018 | 93.5% | Không CRF; chỉ miền chung |
| Truong et al. (2021) | XLM-R + CRF | PhoNER | 91.2% | Chỉ lớp cuối; không cân bằng lớp |
| Vu et al. (2022) | ViBERT + BiLSTM | VietNER | 89.7% | Không tinh chỉnh attention |
| Le et al. (2023) | mBERT + CRF | Financial NER | 87.3% | Loss chuẩn; không thích ứng miền |

### 1.2 SOTA Quốc tế cho NER

| Bài báo | Đổi mới Chính | Tác động |
|---------|--------------|----------|
| Yan et al. (2019) - TENER | Vị trí tương đối trong attention | +1.2% F1 trên CoNLL |
| Li et al. (2020) - Flat NER | Lattice transformer cho NER tiếng Trung | Xử lý nhập nhằng từ |
| Yu et al. (2020) - Biaffine NER | Dựa trên span với biaffine | +2% trên NER lồng nhau |
| Wang et al. (2021) - ACE | Ghép nối tự động embedding | +0.8% qua các dataset |
| Li et al. (2020) - Dice Loss | Loss tối ưu F1 cho NER mất cân bằng | +3% recall thực thể hiếm |

---

## 2. Các Khoảng trống Nghiên cứu Đã Xác định

### Khoảng trống 1: Trích xuất Đặc trưng Đơn Lớp

**Vấn đề**: Tất cả hệ thống NER tiếng Việt hiện có chỉ trích xuất đặc trưng từ lớp transformer cuối cùng.

**Bằng chứng**: Các lớp khác nhau của BERT/XLM-R mã hóa thông tin ngôn ngữ khác nhau:
- Lớp 1-4: Đặc trưng hình thái (cấu trúc từ, phụ tố)
- Lớp 5-8: Đặc trưng cú pháp (từ loại, phụ thuộc)
- Lớp 9-12: Đặc trưng ngữ nghĩa (loại thực thể, quan hệ)

**Giải pháp của Chúng tôi**: Hợp nhất Lớp Thích ứng với trọng số attention học được cho từng lớp.

**Tại sao quan trọng cho tiếng Việt**: Từ ghép tiếng Việt (vd: "Ngân hàng", "cổ phiếu") cần nhận biết hình thái từ lớp thấp để xác định đúng ranh giới thực thể.

**Cải thiện Dự kiến**: +1-2% F1, đặc biệt trên thực thể đa âm tiết.

---

### Khoảng trống 2: Self-Attention Transformer Chung

**Vấn đề**: Self-attention đã huấn luyện trước học các mẫu ngôn ngữ chung, không phải mẫu ranh giới thực thể đặc thù NER.

**Bằng chứng**: Phân tích các attention head trong XLM-R cho thấy:
- Hầu hết head chú ý đến token có quan hệ cú pháp (chủ ngữ-động từ)
- Rất ít head tự nhiên tập trung vào token liên quan ranh giới thực thể
- Không head nào mã hóa thông tin độ rộng span thực thể

**Giải pháp của Chúng tôi**: Multi-Head Attention đặc thù nhiệm vụ với:
1. Mã hóa vị trí tương đối (span thực thể hiếm khi vượt 5-7 token)
2. Kết nối residual có cổng để pha trộn đặc trưng chung và đặc thù NER

**Tại sao quan trọng cho tiếng Việt**: Tên tổ chức tiếng Việt có thể rất dài (vd: "Ngân hàng Thương mại Cổ phần Á Châu" = 7 âm tiết). Mã hóa vị trí tương đối giúp mô hình học rằng token B-ORG nên chú ý đến token I-ORG trong phạm vi độ dài span điển hình.

**Cải thiện Dự kiến**: +1-3% F1 trên thực thể dài (ORG, EVENT, ASSET).

---

### Khoảng trống 3: Hàm Loss Đồng nhất

**Vấn đề**: CRF log-likelihood và cross-entropy chuẩn xử lý tất cả token như nhau, mặc dù mất cân bằng lớp nghiêm trọng.

**Bằng chứng** (từ phân tích bộ dữ liệu):
```
O:        ~82% tổng token
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

**Giải pháp của Chúng tôi**:
1. **Focal Loss**: Giảm trọng số token O dễ phân loại (γ=2.0), tập trung vào ranh giới thực thể khó
2. **Dice Loss**: Tối ưu trực tiếp metric chồng lấn F1 cho mỗi lớp

**Tại sao quan trọng cho tài chính Việt Nam**: Thực thể hiếm như TICKER (mã CK: FPT, VNM) và PRICE rất quan trọng cho ứng dụng tài chính phía sau nhưng có tần suất cực thấp.

**Cải thiện Dự kiến**: +3-5% recall trên thực thể hiếm (TICKER, PRICE, VOLUME).

---

### Khoảng trống 4: Lan truyền Lỗi BIO

**Vấn đề**: Một lỗi ranh giới đơn lẻ trong gán nhãn BIO phá hủy toàn bộ trích xuất thực thể.

**Ví dụ**:
```
Dự đoán:  B-ORG  I-ORG  O      I-ORG  I-ORG
Thực tế:  B-ORG  I-ORG  I-ORG  I-ORG  I-ORG
                         ↑ Một lỗi → thực thể bị tách thành hai phần
```

**Giải pháp của Chúng tôi**: NER dựa trên Span với biaffine scoring dự đoán trực tiếp bộ ba (start, end, type).

**Tại sao quan trọng cho tiếng Việt**: Hệ thống viết phân tách âm tiết nghĩa là một thực thể "từ" như "Ngân hàng" chiếm 2 token. Lỗi ranh giới giữa các âm tiết cùng từ phổ biến và gây hại nghiêm trọng trong lược đồ BIO.

**Cải thiện Dự kiến**: +2-4% exact-match F1 trên trích xuất thực thể.

---

### Khoảng trống 5: Thiếu Cầu nối Encoder-Decoder

**Vấn đề**: Chiếu trực tiếp từ output transformer sang CRF emissions có thể mất thông tin cấu trúc về mẫu tuần tự.

**Bằng chứng**: Output transformer mang ngữ cảnh nhưng không tường minh tuần tự — cơ chế self-attention không có thiên lệch cố hữu về xử lý trái-sang-phải. CRF hưởng lợi từ đầu vào tường minh tuần tự.

**Giải pháp của Chúng tôi**: Lớp tinh chỉnh BiLSTM giữa transformer và CRF:
1. Thêm thiên lệch tuần tự trái-phải tường minh
2. Cung cấp tinh chỉnh đặc trưng đặc thù nhiệm vụ
3. Giảm khoảng cách chiều không gian giữa transformer 768-dim và CRF

**Cải thiện Dự kiến**: +0.5-1.5% F1 từ chất lượng emission tốt hơn.

---

## 3. So sánh Phương pháp

### 3.1 Phân tích Độ Phức tạp Mô hình

| Mô hình | Tham số | Thời gian Huấn luyện (ước tính) | Tốc độ Suy luận |
|---------|---------|--------------------------------|-----------------|
| BiLSTM + CRF | ~5M | Nhanh (phút) | Rất nhanh |
| XLM-R Base + CRF | ~278M | Trung bình (giờ) | Trung bình |
| XLM-R + BiLSTM + CRF | ~280M | Trung bình | Trung bình |
| XLM-R + Attention + CRF | ~285M | Trung bình-Cao | Trung bình |
| XLM-R + Adaptive Fusion + CRF | ~278M + 12 params | Trung bình | Trung bình |
| Focal-CRF + XLM-R | ~278M | Trung bình | Trung bình |
| XLM-R + Span (Biaffine) | ~290M | Cao | Chậm hơn |

### 3.2 Ưu điểm Lý thuyết

| Mô hình | Cân bằng Lớp | Span Dài | Hình thái Việt | Phụ thuộc Nhãn |
|---------|:---:|:---:|:---:|:---:|
| BiLSTM + CRF | ✗ | ✗ | ✗ | ✓ |
| XLM-R + CRF | ✗ | ○ | ○ | ✓ |
| XLM-R + BiLSTM + CRF | ✗ | ○ | ○ | ✓✓ |
| XLM-R + Attention + CRF | ✗ | ✓ | ○ | ✓ |
| XLM-R + Adaptive Fusion | ✗ | ○ | ✓ | ✓ |
| Focal-CRF + XLM-R | ✓ | ○ | ○ | ✓ |
| Dice Loss + XLM-R | ✓ | ○ | ○ | ✓ |
| XLM-R + Span | ○ | ✓ | ✓ | N/A |

Chú thích: ✓ = mạnh, ○ = trung bình, ✗ = yếu, ✓✓ = rất mạnh

---

## 4. Thiết kế Thí nghiệm

### 4.1 Chỉ số Đánh giá
- **F1 cấp token**: Micro/macro/weighted F1 chuẩn trên nhãn BIO
- **F1 cấp thực thể**: Khớp chính xác (cả ranh giới VÀ loại phải đúng)
- **F1 từng lớp**: Hiệu suất riêng trên mỗi loại thực thể
- **Recall thực thể hiếm**: Đo lường cụ thể TICKER, PRICE, VOLUME recall

### 4.2 Nghiên cứu Loại trừ (Ablation)

1. **Loại trừ Hợp nhất Lớp**: So sánh lớp cuối vs. 4 lớp đầu vs. tất cả lớp
2. **Loại trừ Số Attention Head**: 2, 4, 8, 16 head
3. **Loại trừ Trọng số Loss**: Trọng số CRF λ ∈ {0.3, 0.5, 0.7}
4. **Loại trừ Focal Gamma**: γ ∈ {0.5, 1.0, 2.0, 3.0}
5. **Loại trừ Độ sâu BiLSTM**: 1, 2, 3 lớp BiLSTM

### 4.3 Ý nghĩa Thống kê
- Chạy mỗi mô hình 5 lần với random seed khác nhau
- Báo cáo trung bình ± độ lệch chuẩn điểm F1
- Thực hiện paired t-test giữa baseline và mỗi mô hình nâng cao

---

## 5. Tóm tắt Đóng góp

1. **Nghiên cứu toàn diện đầu tiên** về kiến trúc NER nâng cao cho văn bản tài chính tiếng Việt
2. **Hợp nhất Lớp Thích ứng** khai thác đặc trưng hình thái ở lớp transformer thấp
3. **Attention đặc thù NER** với mã hóa vị trí tương đối cho nhận biết span thực thể
4. **Kỹ thuật hàm loss** (Focal + Dice) giải quyết >80% O-tag thống trị
5. **Phương pháp dựa trên Span** loại bỏ lan truyền lỗi BIO cho tiếng Việt phân tách âm tiết
6. **Hybrid BiLSTM-Transformer** cầu nối embedding ngữ cảnh và dự đoán có cấu trúc
7. **Benchmark đầy đủ** so sánh 13 mô hình trên NER tài chính tiếng Việt
