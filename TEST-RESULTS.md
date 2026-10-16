# 測試結果

日期：2026-10-14，Asia/Hong_Kong。

**24 項自動化測試通過；本機 Django check 無問題；公網部署與真實學校郵件投遞未完成。**

## 實際環境

- macOS ARM64，下載至工作目錄的 CPython 3.12.15。
- Django 5.2.18、Pillow 11.3.0、SQLite 真實檔案資料庫。
- Django HTTP test clients、ORM、資料庫 migrations、暫存圖片檔案系統。
- 郵件測試：Django locmem 收件箱，**不是 CityUHK 郵箱**。
- 瀏覽器：Codex in-app browser，390×844 手機及 1280×900 桌面。
- PostgreSQL client／server 和 Docker 未安裝；相應部署測試未執行。

原始測試輸出：[TEST-OUTPUT.txt](TEST-OUTPUT.txt)。重現指令：

```sh
python manage.py test market --noinput --verbosity 2
python manage.py check
python manage.py makemigrations --check --dry-run
```

最後一輪 24 tests，OK；遷移檢查顯示 No changes detected。

## 核心驗收證據

| 驗收 | 實際測試方式 | 結果 |
|---|---|---|
| 兩個普通帳號驗證與登入 | alice/bob 由 HTTP 提交學校域名信箱，從獨立測試郵件取一次性連結，GET 不消耗、POST 驗證，不用 force_login 跳過此流程 | 通過（測試郵件 backend） |
| 發布物品與圖片 | 第一帳號 HTTP 提交免費 Tripod、押金、日期及真實 PNG；ORM 及圖片存檔存在 | 通過 |
| 費用預覽／申請／接受 | 第二帳號取得簽名報價並申請，第一帳號接受 | 通過 |
| 價格及條款快照 | 物主改日租／押金後既有訂單不變；延期使用原日租 | 通過 |
| 報價過期／變更保護 | 已顯示報價後更改價格，再申請時拒絕並要求重新確認 | 價格變更拒絕通過；15 分鐘期限由 signing max_age 實作 |
| 拒絕重疊 | 同一區間兩個 pending 申請，先接受一個，再接受另一個被拒絕 | 通過 |
| 並發保護 | 真實兩個執行緒、獨立資料庫連線、Barrier 同時接受相同區間；恰好一單 accepted、另一單 conflict | 通過（SQLite） |
| 資料庫直接寫入保護 | 繞過服務層直接 update 重疊訂單為 accepted，資料庫觸發器拒絕 | 通過（SQLite） |
| 相鄰預約 | 前單 end 等於後單 start，兩單都接受 | 通過 |
| 取消釋放 | 取消佔用訂單後，原被阻擋訂單可接受 | 通過 |
| 延期 | 未批准不改 end；有後續衝突時批准失敗，取消後續單後批准成功 | 通過 |
| 交接及歸還 | 雙方各自確認，只有兩邊確認才改為 active／completed；單邊歸還為 return_pending | 通過 |
| 實際時間及照片 | 完成時寫 actual_return；交接／歸還真實圖片寫入暫存儲存 | 通過 |
| 部分交接取消 | 任一方已確認交接後拒絕直接取消 | 通過 |
| 評價 | 完成後兩個帳號分別評價；未完成／重複評價拒絕 | 通過 |
| 訂單／聊天／照片隔離 | 額外第三普通帳號及匿名請求不能讀寫私有訂單、聊天或證據圖 | 通過 |
| 管理權限 | 普通帳號不能進後台；管理員可查看訂單／證據與舉報；非管理員不能結案糾紛 | 通過 |
| 糾紛 | 糾紛仍鎖定；雙方確認歸還後管理員才能標完成，保留 Audit | 通過 |
| 支付確認 | 僅物主點擊時只有物主旗標，借用人旗標不變 | 通過 |
| 域名／未驗證限制 | 假相似域名被拒，未驗證帳號不能發布或申請 | 通過 |
| Token | 一次性、過期、掃描器 GET 不消耗 | 通過 |
| 限流 | 重複同信箱要求連結被拒，僅生成一封測試郵件 | 通過 |
| 上傳保護 | SVG、偽裝圖片、超過 5MB 拒絕；有效 PNG 重編碼為 JPEG | 通過 |
| XSS／CSRF | 私訊 script 被跳脫；缺 CSRF 的發布及登入 POST 被拒 | 通過 |
| 帳號限制 | 已登入帳號被限制後立即失去受限頁面存取權，公開庫存隱藏 | 通過 |
| 搜尋／求借／回應／通知 | 依分類／價錢查詢、關聯自己的物品回應、私人對話及通知落庫 | 通過 |
| 雙語頁面 | 主要頁面在 zh/en 下實際 HTTP render；訂單各狀態 render | 通過 |

表中每行為驗收項目；部分由同一測試涵蓋，所以項目數不等於 24 個測試方法數。

## 瀏覽器與介面

實際開啟本機 `/`，取得 HTTP 200；檢查手機中文首頁、桌面英文首頁、點擊語言切換。390px 下 `document.documentElement.scrollWidth === innerWidth === 390`，沒有首頁橫向溢出。

- [手機中文全頁截圖](mobile-preview.jpg)
- [桌面英文全頁截圖](desktop-preview.jpg)

瀏覽器檢查覆蓋首頁視覺與語言切換；所有表單的功能驗收主要由服務端 HTTP clients 完成，未聲稱逐頁人工手機操作或真實手機設備測試。

## 生產設定檢查

在 DEBUG=0、測試用非預設 SECRET_KEY、SMTP host 及允許域名的環境執行 `check --deploy`。結果見 [DEPLOY-CHECK.txt](DEPLOY-CHECK.txt)：只有 `security.W021`（未開啟 HSTS preload）。已啟用 HTTPS 重導向、Secure cookies、HSTS 和 includeSubDomains；未選擇把尚未控制的域名提交 preload。此檢查不會實際連線 SMTP、申請憑證或驗證 Docker。

## 必須補測，未標為通過

- PostgreSQL migrations、GiST exclusion constraint 和 PostgreSQL 雙執行緒測試。
- Docker image build、volume 權限、Caddy config、公開 HTTPS 憑證、DNS 及重啟恢復。
- 真實兩個 CityUHK 郵箱收到登入郵件、延遲／垃圾郵件和寄件域名設定。
- 香港移動網絡及 CityUHK 校園網絡存取。
- 真實手機 Safari／Chrome 的表單、照片上傳及完成整個訂單。
- 加密異地備份、還原演練、監控和預算告警。

以上需要伺服器、域名、SMTP 配置及相應網絡／信箱；本次沒有這些條件，不以本機測試替代。
