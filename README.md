# grass-render — Grass Lite Node trên Render Free

Node Grass (extension) chạy trong Docker trên Render free tier (750h/tháng, 512MB RAM).

## Kiến trúc
- `Dockerfile`: python-slim + Chrome for Testing 131 (tải lúc build) + deps
- `app.py`:
  - Flask-style `/health` server (bind `$PORT`, trả JSON trạng thái) — Render health check
  - **Self-ping** `RENDER_EXTERNAL_URL/health` mỗi 10 phút — chống sleep 15 phút
  - Tải extension Grass Lite Node từ Chrome Web Store (CRX → unpacked)
  - Chrome `--headless=new` + `--load-extension` (không cần Xvfb/VNC)
  - Nạp cookie + localStorage từ link Drive (`COOKIES_URL` / `STORAGE_URL`) qua CDP
  - Vòng lặp: giữ phiên + refresh + tự lưu session lại `/app/data`
- Không có EMAIL/PASSWORD trong repo — chỉ dùng cookie session

## Env vars
| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `COOKIES_URL` | (rỗng) | Link file cookie JSON (Drive/GitHub/Pastebin) |
| `STORAGE_URL` | (rỗng) | Link file localStorage JSON |
| `GRASS_URL` | https://app.grass.io | Domain phải khớp cookie đã export |
| `SLEEP_SECONDS` | 300 | Chu kỳ refresh giữ phiên |
| `PING_SECONDS` | 600 | Chu kỳ self-ping |

## Cập nhật cookie khi hết hạn
1. Export cookie mới bằng extension Cookie-Editor (format JSON) → upload lên Drive (Anyone with link)
2. Render Dashboard → Environment → đổi `COOKIES_URL` → service tự restart
