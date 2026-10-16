# 香港部署與營運

## 尚需你們提供

1. **香港 VPS／雲帳號及可部署權限**：建議至少 2 GB RAM 的 Linux 主機；香港區域可考慮 AWS Lightsail Asia Pacific (Hong Kong)，或已有香港 VPS。當前沒有連接這類帳號，尚無公網 HTTPS 地址。
2. **域名和 DNS 修改權限**：例如 `share.your-domain.hk`；不要使用未獲授權的 CityUHK 官方域名。
3. **SMTP 服務帳號／密鑰及已驗證的寄件域名**：Resend SMTP、Amazon SES SMTP 或現有 SMTP。不得用學生的學校帳號密碼作為 SMTP 密碼。
4. **平台隨機 SECRET_KEY、PostgreSQL 密碼和管理員帳號**：透過主機上的私密 `.env` 或機密管理服務設定。勿貼到聊天或提交 Git。

不需要學校官方 SSO 配置；本版沒有接入 SSO。日後須先取得學校授權及正式配置。

## 首次部署

在香港主機安裝官方 Docker Engine 和 Compose plugin。SSH 只對管理員 IP 開放；對訪客只開 80/443。設定 DNS A record 指向公網 IP；僅在 IPv6 正常配置時增加 AAAA。確認 TCP 80/443 可從公網抵達，以便 Caddy 自動申請及續期憑證。

上傳不含本機資料、郵件和密鑰的程式碼後：

```sh
cp .env.example .env
chmod 600 .env
# 使用主機編輯器設定所有 REPLACE 值、真實 SMTP、域名及來源
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
# 把輸出安全地填入 SECRET_KEY，勿保留於公開日誌

docker compose config --quiet
docker compose up -d --build
docker compose exec app python manage.py check --deploy
docker compose exec app python manage.py createsuperuser
```

容器啟動時先執行 migration，再收集靜態檔案並啟動 Gunicorn。資料庫的 `btree_gist` extension 需要 migration 使用者有安裝權限；Compose 的 PostgreSQL 資料庫擁有者可執行。若改用託管 PostgreSQL，請先由有權限的管理員啟用該 extension。

完成後地址是 `https://<你設定的 DOMAIN>/`，只有憑證、migration 和健康檢查實際成功後才能列為「已部署」。本次未能執行 Docker：開發機沒有 Docker／PostgreSQL；設定已提供，尚待香港主機實測。

`ALLOWED_HOSTS` 必須只列實際域名；`CSRF_TRUSTED_ORIGINS` 使用 `https://` 完整來源。`.env` 由 Compose 載入，本機直接執行 Python 時不會自動載入 `.env`，需自行 export。

Caddy 是唯一公開入口。app/db 都沒有 host port；不要新增公開 app/db port。只有在這種受控反向代理架構才設 `TRUST_PROXY_IP=1`，Caddy 強制覆寫 X-Real-IP，避免客戶端偽造限流來源。若再加 CDN／代理，必須重新配置可信來源和真實客戶端 IP；否則保持直連 Caddy。

## 環境變數

| 變數 | 用途 |
|---|---|
| `DOMAIN`、`ACME_EMAIL` | Caddy 主機名及憑證聯絡信箱 |
| `SECRET_KEY` | 隨機且至少 40 字元；生產拒絕預設值及 REPLACE 佔位值 |
| `DEBUG` | 生產固定為 `0`；Compose 已強制設定 |
| `ALLOWED_HOSTS` | 逗號分隔的精確域名 |
| `CSRF_TRUSTED_ORIGINS` | 逗號分隔的可信 HTTPS origins |
| `ALLOWED_EMAIL_DOMAINS` | 預設 `my.cityu.edu.hk`；服務端精確比對域名 |
| `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | PostgreSQL 連線；Compose 主機為 db、port 預設 5432 |
| `MEDIA_ROOT` | 私有儲存根目錄；Compose 為 `/data/media` |
| `EMAIL_HOST`、`EMAIL_PORT`、`EMAIL_HOST_USER`、`EMAIL_HOST_PASSWORD` | SMTP 連線 |
| `EMAIL_USE_TLS` | 預設 `1`，使用 STARTTLS；本版配置為 port 587 |
| `DEFAULT_FROM_EMAIL` | 已驗證寄件域名的地址 |
| `TRUST_PROXY_IP` | 僅受控私有 app 入口可設 `1` |

## 圖片與私隱

本版使用**真實持久檔案儲存**，非 browser storage。`private_media` named volume 不掛載至 Caddy；圖片透過 Django endpoint 授權存取。訂單證據圖只有雙方或 staff 可看，設 `private, no-store`。上架物品圖與公開頭像可公開；暫停／下架物品圖僅物主及管理員可看。

單圖上限 5 MB，只接受 JPEG/PNG/WebP；實際解碼、像素上限 20M、重編碼 JPEG、最長邊 1800、移除 EXIF。反向代理總 request body 上限 8 MB。儲存沒有預設公開 bucket；若擴展至 S3 香港 ap-east-1，需新增私有 storage backend／短效簽名下載，**不能只把證據圖改成公開 URL**。S3 整合不是本版已接通功能。

## 郵件投遞

配置 SPF、DKIM 及 DMARC；完成寄件域名驗證。SMTP 必須允許向 `@my.cityu.edu.hk` 發送，若供應商仍在 sandbox，先解除收件人限制。實際提交兩個學校信箱，各自確認收件箱／垃圾郵件與單次登入；記錄發送時間、延遲和 message ID，不記錄完整登入 token。

登入連結 15 分鐘有效、雜湊保存且只能用一次，GET 不消耗，POST 才登入。每信箱 1 次／分鐘、5 次／小時；每來源 IP 20 次／小時。管理員登入 10 次／5 分鐘。共享校園 NAT 可能碰到 IP 上限，根據實測調整 `services.py`，仍須保留信箱限流。未經郵件成功驗證不能發布或申請。

生產預設不開存取日誌，減少登入 token 進入 URL 日誌。仍需檢查前置代理／主機的錯誤日誌，並過濾驗證 URL、完整信箱、私訊與照片內容；日後增加錯誤監控時同樣處理。

## 備份與日常管理

每天執行：

```sh
docker compose exec -T app python manage.py cleanup_auth
docker compose exec -T app python manage.py clearsessions
```

備份應包括 PostgreSQL、私有圖片及營運配置，並加密放至不同故障域。以下是在主機上產生一致的停機備份；備份前確認磁碟空間：

```sh
mkdir -p backups
chmod 700 backups
docker compose stop app
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/database.dump
docker compose run --rm --no-deps --entrypoint tar app -C /data/media -czf - . > backups/media.tar.gz
docker compose start app
```

不要把私有圖片直接傳到公開儲存。另行啟用加密遠端備份、保留週期和容量告警；本版不包含已啟用的遠端備份服務。每次變更 schema 前備份；定期在隔離主機演練 `pg_restore` 與圖片還原。刪除 volume 的指令會永久移除資料，因此不要對生產執行 `docker compose down -v`。

管理員可在 `/admin/` 處理 Report 的 resolution/resolved、下架 Item、關閉 Wanted 或限制 Profile。Order 與 Audit 不允許直接編輯；糾紛訂單用明確 admin actions 結案：雙方確認歸還後完成，或尚未開始交接時取消；保留審計紀錄。管理員不具自動扣押或退款權。

## 預計持續成本

2026-10-14 查閱的公開價格；以下是規劃估算，不是報價，沒有購買任何資源。HKD 換算以 USD×7.8 的預算假設，未計稅、超額流量或匯差。

| 項目 | 初期預算 |
|---|---|
| 香港 Lightsail 2GB／60GB、IPv4 Linux 主機 | USD 12／月，約 HK$94；資料庫及圖片卷共用該主機 |
| 較充裕的 4GB 主機 | USD 24／月，約 HK$187 |
| 郵件 | Resend 免費額度內 USD 0；若需要付費方案預留約 HK$156／月（USD 20），以實際方案為準 |
| 域名 | 規劃 HK$100–300／年，約 HK$8–25／月；取決於 TLD／註冊商，非特定供應商報價 |
| 加密異地備份 | 小規模規劃 HK$10–50／月，依資料量與供應商報價 |
| HTTPS 憑證 | Caddy 自動 ACME 憑證，無額外憑證購買預算 |

小規模共用主機與免費郵件時約 **HK$112–169／月**；4GB 或付費郵件會提高成本。持續監察容量、備份及郵件限額。香港區域流量額度可能與其他地區不同。

來源：[AWS Lightsail bundles](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html)、[AWS Lightsail pricing（地區差異）](https://aws.amazon.com/lightsail/pricing/)、[Resend pricing](https://resend.com/pricing)。

## 上線驗收（尚待執行）

| 項目 | 做法 | 本次狀態 |
|---|---|---|
| PostgreSQL migration／競爭接受 | 在 staging app 執行 `python manage.py test market --noinput`；使用可建立 test database 的獨立資料庫角色，不要用生產庫做測試 | 待驗證 |
| HTTPS／DNS／重導向 | 確認公網 https 正確憑證、http 重導向、CSRF、Secure cookie、私有圖片拒絕匿名 | 待驗證 |
| 香港移動網絡 | 關閉 Wi-Fi，兩個普通帳號實走發布→接受→交接→歸還→評價，記錄電訊商、時間和錯誤 | 無法從該網絡測試，待驗證 |
| CityUHK 校園網絡 | 校內 Wi-Fi／有線獨立重試；檢查 DNS、圖片及登入連結 | 無法從校園網絡測試，待驗證 |
| 真實學校郵箱 | 兩個 `@my.cityu.edu.hk` 分別收到並使用郵件，拒絕其他域名 | 未有 SMTP 與真實測試信箱，待驗證 |
| Docker build／Caddy config | 香港 staging 執行 compose build、Caddy validate、check --deploy | 本機無 Docker，待驗證 |

測試必須記錄實際日期、環境與結果；沒有測到不得標記通過。
