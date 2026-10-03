# Xử lý credential từng được commit

## Phạm vi phát hiện

Kiểm tra repository ngày 03/10/2026 xác định các tên biến sau từng có giá trị
có hình dạng credential trong lịch sử Git:

- `JWT_SECRET_KEY`;
- `API_TOKEN`;
- `VOYAGE_API_KEY`;
- `OPENROUTER_API_KEY`;
- `GEMINI_API_KEY`.

Giá trị không được ghi lại trong tài liệu, log hoặc artifact. Commit gốc có bốn
biến đầu là `9f564780c484`. `GEMINI_API_KEY` từng nằm trong
`src/model/llms_inference/gemini_models/config/.env` ở cùng commit. Commit đã
xóa file `.env` gốc là `8fefaec1c978`; việc xóa ở commit mới không loại bỏ
giá trị khỏi lịch sử.

## Việc đã thực hiện trong working tree

- file `.env` lồng trong module Gemini đã được bỏ khỏi Git index;
- `.gitignore` hiện bỏ qua mọi `.env` và `.env.*`, ngoại trừ `.env.example`;
- `.env.example` chỉ khai báo các API key ngoài với giá trị rỗng;
- hai script Gemini dùng environment hoặc `.env` ở repository, không còn trỏ
  tới đường dẫn tuyệt đối trên máy của developer cũ;
- release audit quét mọi blob có basename `.env` trong lịch sử và chỉ báo tên
  biến, không xuất giá trị;
- hai secret nội bộ trong `.env` local được tạo lại;
- ba API key ngoài trong local configuration được vô hiệu hóa cho tới khi có
  key thay thế.

## Việc chủ tài khoản phải thực hiện

Các key ngoài phải được xem là đã lộ vì bất kỳ người nào có lịch sử Git đều có
thể đọc chúng. Trong bảng điều khiển của từng nhà cung cấp:

1. revoke/xóa key Google Gemini cũ;
2. revoke/xóa key Voyage AI cũ;
3. revoke/xóa key OpenRouter cũ;
4. kiểm tra usage/billing bất thường từ thời điểm commit đầu tiên;
5. chỉ tạo key thay thế sau khi key cũ đã bị revoke;
6. lưu key mới trong `.env` bị ignore hoặc secret manager, không đưa vào Git.

Nếu `JWT_SECRET_KEY` hoặc `API_TOKEN` từng được dùng ngoài máy local, phải thay
giá trị trong môi trường đó và vô hiệu hóa token/session cũ.

## Làm sạch lịch sử Git

Rotation phải thực hiện trước khi rewrite vì lịch sử Git đã được clone có thể
không thu hồi được. Rewrite cần loại hai đường dẫn sau khỏi toàn bộ refs:

```text
.env
src/model/llms_inference/gemini_models/config/.env
```

Dùng `git filter-repo` trong một clone sạch, kiểm tra lại bằng secret scanner,
sau đó force-push có kiểm soát bằng `--force-with-lease`. Mọi collaborator phải
clone lại hoặc reset về lịch sử mới. Không chạy rewrite khi còn thay đổi chưa
commit và không push trước khi chủ repository xác nhận cửa sổ phối hợp.

Ví dụ trong clone bảo trì riêng:

```bash
git filter-repo --force \
  --path .env \
  --path src/model/llms_inference/gemini_models/config/.env \
  --invert-paths

git log --all -- .env src/model/llms_inference/gemini_models/config/.env
git push origin --force-with-lease --all
git push origin --force-with-lease --tags
```

Không coi repository an toàn chỉ vì lệnh `git log` không còn kết quả. Release
gate chỉ có thể chuyển sang sẵn sàng sau khi key đã được revoke/rotate, remote
đã được làm sạch, các clone cũ được xử lý và audit/acceptance chạy lại.

## Kết quả diễn tập

Quy trình xóa hai đường dẫn đã được chạy thử trên một mirror tạm, không kết nối
push tới remote. Kết quả kiểm tra sau rewrite và garbage collection:

```text
root_env_history=0
nested_env_history=0
reachable_sensitive_path_objects=0
fsck_unreachable_objects=0
```

Đây là bằng chứng kỹ thuật cho câu lệnh rewrite. GitHub vẫn chứa lịch sử cũ cho
tới khi chủ repository chọn thời gian phối hợp và thực hiện force-push.
