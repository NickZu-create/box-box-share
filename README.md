# Box Box Share

面向 CityUHK 社群、學生營運的物品租借／求借平台第一版。不是學校官方平台，不代表學校認可。學校郵箱驗證只確認郵箱存取權，不代表在讀學籍已核實。

**交付狀態：本機可運行，74 項自動化測試通過；未部署到公網，未接通真實 SMTP。** 香港移動網絡、校園網絡及真實學校郵箱投遞均待驗證。完整詳情見 [測試報告](TEST-RESULTS.md)、[功能清單](FEATURES.md) 和 [部署說明](DEPLOYMENT.md)。免費試用部署（Render + Neon + Resend）見 [DEPLOY-RENDER.md](DEPLOY-RENDER.md)。

## 快速運行

需要 Python 3.12（最低 3.10）；首次安裝需要網絡。無需 Node.js。

```sh
cd cityu-share
chmod +x run-local.sh
./run-local.sh
```

若 Python 不叫 python3.12：`PYTHON=/path/to/python3 ./run-local.sh`。

瀏覽 http://127.0.0.1:8000/ 。SQLite 真實資料庫寫入 `data.sqlite3`，圖片儲存在 `private-media/`。本機只綁定 loopback，不對外公開。第一次開啟為真實空狀態；不預置虛構庫存或可登入樣例帳號。

手動步驟：

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

本機沒有 EMAIL_HOST 時使用檔案郵件：登入頁提交 `名字@my.cityu.edu.hk` 後，管理開發機的人可從 `dev-mail/` 最新檔案取登入連結。此模式**沒有向學校郵箱發送郵件，也不能作為真實身份驗收**。登入連結具有帳號存取權，不應分享、加入版本控制或上傳。生產環境 DEBUG=0 強制要求 SMTP，不允許悄悄退回檔案郵件。

建立管理員：

```sh
.venv/bin/python manage.py createsuperuser
```

管理介面：`/admin/`。此命令設定的是**平台管理員**密碼，不是學校帳號密碼。普通用戶不需要密碼；郵箱驗證建立的用戶具有 unusable password。

## 測試

```sh
.venv/bin/python manage.py test market --noinput --verbosity 2
.venv/bin/python manage.py check
```

測試使用獨立 SQLite 檔案並自動刪除，不改動本機資料。測試用信箱由 Django locmem backend 接收；資料、上傳圖片、操作記錄均經真實 ORM／服務端 HTTP 處理，不靠 localStorage。

## 結構

- `campus/`：設定、URL、WSGI。
- `market/models.py`：資料、價格／條款快照、確認紀錄。
- `market/services.py`：驗證、限流、權限、預約鎖定、延期、狀態機、圖片重新編碼。
- `market/social.py`：Buddy 招募（申請、撤回、審批、名額、關閉）及好友（申請、接受、拒絕、移除、好友對話）。
- `market/i18n.py`：English／繁體中文／简体中文三選一；简体由繁體文字經 OpenCC 轉換，使用者內容不轉換。
- `market/views.py`：手機優先伺服器渲染介面。
- `market/templates/`、`market/static/`：三語 UI、CSS 和內嵌 SVG 插圖；無第三方前端資源依賴。
- `market/migrations/`：可重現資料結構，含資料庫預約衝突保護。
- `market/tests.py`：雙帳號完整流程、權限隔離及真實雙執行緒競爭。
- `compose.yaml`、`Dockerfile`、`Caddyfile`：香港 VPS 生產部署配置。

## Buddy、好友與介面語言

導航順序：Explore → Seeking → Impact → Buddy → My activity → Messages；個人資料經頭像進入。

- **Buddy**（`/buddy/`）分「找搭子」（學習、運動、吃飯、校園活動）與「找隊友」（課程項目、比賽、Hackathon、創業）。發布、編輯、關閉／重新開放；申請、撤回、退出；發起人接受、婉拒、移出。**所需人數一律不含發起人**，詳情、申請及審批頁面都這樣標示。狀態分招募中、已滿、已關閉（發起人關閉）、已結束（結束時間或開始時間已過）。接受申請時鎖定招募資料列，同時接受也不會超員。關閉時仍在等待的申請自動婉拒並通知。
- **對話**：申請獲接受後，在 `Thread.buddy` 建立發起人與成員的一對一對話；成員退出或被移出後對話保留但不能再發訊息。物品、訂單對話不變。
- **好友**：在成員頁面送出申請；對方接受才成為好友，可在 Messages 直接聊天；可拒絕、取消、移除。被拒絕後不能再次發送，除非對方主動申請。交易對象和活動成員不會自動成為好友。
- **My activity** 保留原有三部分，另加獨立 Buddy 區：我發布的招募、我的申請、我已加入。
- **個人資料**新增自我介紹、興趣、技能、交流語言，只向已登入成員顯示；郵箱從不公開。
- **語言**：English／繁體中文／简体中文，存於 session 及 cookie（登出後仍保留）；切換後回到同一頁面和篩選條件，未送出的表單內容和捲動位置由 `lang.js` 還原。

## 核心行為

預約區間為 `[開始, 結束)`；結束相同於下一單開始不構成衝突。申請 pending 不鎖定；接受、延期與取消按同一順序鎖定物品／訂單。SQLite 使用 IMMEDIATE 交易及觸發器；PostgreSQL 使用行鎖和 GiST exclusion constraint，資料庫層亦會拒絕直接寫入的重疊預約。已取消／完成不佔用時段；糾紛中仍佔用。

租金為 `ceil((end-start)/24h) × 申請時每日租金`；允許免費。延期需物主批准，沿用原日租快照，更新結束時間及總租金，並記錄舊／新日期及舊租金。物主後續編輯價格不修改現有訂單。

交接、歸還、租金支付、押金支付及押金退還分別記錄雙方確認。僅一方確認不表示付款真實完成。交接開始後不能直接取消；可提出糾紛。歸還雙方確認後記錄實際歸還確認時間。無自動收款、扣款、押金託管或保險。

所有日期輸入及展示使用 Asia/Hong_Kong；資料庫保存帶時區時間。介面主要文案可切換，表單標籤、分類及系統操作記錄採繁中／英文並列，方便跨語言交接。
