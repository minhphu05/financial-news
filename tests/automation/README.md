# Automation Testing — Selenium & Playwright

Bộ test tự động hoá kiểm thử giao diện web cho dự án Financial News,
sử dụng cả **Selenium** (sync) và **Playwright** (async) để đảm bảo
trang web hoạt động chính xác "mọi lúc mọi nơi".

## Cấu trúc thư mục

```
tests/automation/
├── config/
│   ├── __init__.py
│   └── settings.py          # Cấu hình từ environment variables
├── pages/
│   ├── __init__.py           # BasePage abstract class
│   ├── selenium_pages.py     # Page Objects cho Selenium
│   └── playwright_pages.py   # Page Objects cho Playwright
├── selenium/
│   ├── __init__.py
│   ├── test_homepage.py      # Tests trang chủ
│   ├── test_news.py          # Tests trang tin tức
│   ├── test_chat.py          # Tests chatbot RAG
│   └── test_navigation.py    # Tests điều hướng
├── playwright/
│   ├── __init__.py
│   ├── test_homepage.py      # Tests trang chủ (async)
│   ├── test_news.py          # Tests trang tin tức (async)
│   ├── test_chat.py          # Tests chatbot (async + API mocking)
│   └── test_navigation.py    # Tests điều hướng + accessibility
├── conftest.py               # Browser fixtures
├── pytest_plugins.py         # Custom markers
└── README.md                 # Tài liệu này
```

## Cài đặt

```bash
# Selenium
pip install selenium webdriver-manager

# Playwright
pip install playwright pytest-playwright pytest-asyncio
playwright install chromium firefox webkit
```

## Cấu hình

Tất cả cấu hình qua environment variables, **không hardcode**:

| Variable | Mặc định | Mô tả |
|----------|----------|--------|
| `TEST_BASE_URL` | `http://localhost:5173` | URL frontend |
| `TEST_API_BASE_URL` | `http://localhost:8000` | URL backend API |
| `TEST_HEADLESS` | `true` | Chạy browser ẩn |
| `TEST_SLOW_MO` | `0` | Delay giữa actions (ms) |
| `TEST_VIEWPORT_WIDTH` | `1280` | Chiều rộng viewport |
| `TEST_VIEWPORT_HEIGHT` | `720` | Chiều cao viewport |
| `TEST_TIMEOUT` | `30000` | Timeout mặc định (ms) |
| `TEST_NAV_TIMEOUT` | `60000` | Timeout navigation (ms) |
| `TEST_IMPLICIT_WAIT` | `10` | Selenium implicit wait (s) |
| `TEST_PAGE_LOAD_TIMEOUT` | `30` | Page load timeout (s) |
| `TEST_SCREENSHOT_DIR` | `tests/automation/screenshots` | Thư mục lưu screenshot |
| `TEST_VIDEO_DIR` | `tests/automation/videos` | Thư mục lưu video |
| `TEST_BROWSERS` | `chromium` | Browsers (phân cách bởi dấu phẩy) |
| `TEST_RETRY_COUNT` | `2` | Số lần retry test lỗi |
| `RECORD_VIDEO` | _(unset)_ | Ghi video khi test |

## Chạy tests

### Selenium tests
```bash
# Tất cả Selenium tests
pytest tests/automation/selenium/ -v -m selenium

# Chỉ test homepage
pytest tests/automation/selenium/test_homepage.py -v

# Với browser hiện (debug)
TEST_HEADLESS=false TEST_SLOW_MO=500 pytest tests/automation/selenium/ -v
```

### Playwright tests
```bash
# Tất cả Playwright tests
pytest tests/automation/playwright/ -v -m playwright

# Chỉ test chat
pytest tests/automation/playwright/test_chat.py -v

# Multi-browser
TEST_BROWSERS=chromium,firefox,webkit pytest tests/automation/playwright/ -v
```

### Chạy tất cả
```bash
pytest tests/automation/ -v --tb=short
```

## Design Patterns

### Page Object Model (POM)
- Mỗi trang web → 1 Page Object class
- Selectors tập trung tại class-level constants
- Sử dụng fallback selectors: `[data-testid='x'], .class, element`
- Tests viết against Page Object API, không trực tiếp dùng selectors

### Environment-Driven Configuration
- **Zero hardcoded values** — tất cả qua `AutomationSettings.from_env()`
- Hỗ trợ CI/CD với environment variables
- Default values cho local development

### Dual Framework Support
- **Selenium**: Mature, wide browser support, sync API
- **Playwright**: Modern, auto-wait, network mocking, async API
- Cùng test coverage, khác implementation

## CI/CD Integration

```yaml
# GitHub Actions example
- name: Run Selenium Tests
  env:
    TEST_BASE_URL: http://localhost:5173
    TEST_HEADLESS: true
  run: pytest tests/automation/selenium/ -v

- name: Run Playwright Tests
  env:
    TEST_BASE_URL: http://localhost:5173
    TEST_HEADLESS: true
  run: pytest tests/automation/playwright/ -v
```

## Troubleshooting

| Vấn đề | Giải pháp |
|--------|-----------|
| `TimeoutError` | Tăng `TEST_TIMEOUT`, kiểm tra app đang chạy |
| `ElementNotFound` | Kiểm tra selectors, dùng `TEST_HEADLESS=false` để debug |
| Screenshot trống | Đợi page load xong, kiểm tra viewport size |
| API tests fail | Đảm bảo backend đang chạy tại `TEST_API_BASE_URL` |
