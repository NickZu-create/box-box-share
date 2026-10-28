# Box Box Share

面向 CityUHK 社群、學生營運的物品租借／求借平台第一版，並提供 Campus Connect：組隊合作（Team Up）、搭子交友（Meet）及自願開啟的心動配對（Dating）。實施計劃、權限隔離及 GPA 審核私隱方案見 [CONNECT-PLAN.md](CONNECT-PLAN.md)。不是學校官方平台，不代表學校認可。學校郵箱驗證只確認郵箱存取權，不代表在讀學籍已核實。

**交付狀態：本機可運行，24 項自動化測試通過；未部署到公網，未接通真實 SMTP。** 香港移動網絡、校園網絡及真實學校郵箱投遞均待驗證。完整詳情見 [測試報告](TEST-RESULTS.md)、[功能清單](FEATURES.md) 和 [部署說明](DEPLOYMENT.md)。免費試用部署（Render + Neon + Resend）見 [DEPLOY-RENDER.md](DEPLOY-RENDER.md)。

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
- `market/teamup.py`、`market/connect.py`：Team Up、學術資料、GPA 審核的服務層與視圖。
- `market/services.py`：驗證、限流、權限、預約鎖定、延期、狀態機、圖片重新編碼。
- `market/views.py`：手機優先伺服器渲染介面。
- `market/templates/`、`market/static/`：繁中／英文 UI、CSS 和內嵌 SVG 插圖；無第三方前端資源依賴。
- `market/migrations/`：可重現資料結構，含資料庫預約衝突保護。
- `market/tests.py`：雙帳號完整流程、權限隔離及真實雙執行緒競爭。
- `compose.yaml`、`Dockerfile`、`Caddyfile`：香港 VPS 生產部署配置。

## 核心行為

預約區間為 `[開始, 結束)`；結束相同於下一單開始不構成衝突。申請 pending 不鎖定；接受、延期與取消按同一順序鎖定物品／訂單。SQLite 使用 IMMEDIATE 交易及觸發器；PostgreSQL 使用行鎖和 GiST exclusion constraint，資料庫層亦會拒絕直接寫入的重疊預約。已取消／完成不佔用時段；糾紛中仍佔用。

租金為 `ceil((end-start)/24h) × 申請時每日租金`；允許免費。延期需物主批准，沿用原日租快照，更新結束時間及總租金，並記錄舊／新日期及舊租金。物主後續編輯價格不修改現有訂單。

交接、歸還、租金支付、押金支付及押金退還分別記錄雙方確認。僅一方確認不表示付款真實完成。交接開始後不能直接取消；可提出糾紛。歸還雙方確認後記錄實際歸還確認時間。無自動收款、扣款、押金託管或保險。

搭子與交友均為自願開啟。報名搭子後與發起人開啟一對一對話，發起人接受後雙方即算「認識」；一起借用（申請已接受）亦算認識。只有認識的人可以互加好友；好友請求對方可見，心動則保密，只有互相心動才通知雙方。心動配對須自行確認年滿 18 歲。封鎖會移除好友與心動、婉拒彼此報名並關閉非訂單對話，但保留借用訂單對話以便歸還。

所有日期輸入及展示使用 Asia/Hong_Kong；資料庫保存帶時區時間。介面主要文案可切換，表單標籤、分類及系統操作記錄採繁中／英文並列，方便跨語言交接。
