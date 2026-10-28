# Campus Connect 實施計劃

Box Box Share 在物品共享之外加入 **Team Up（組隊）**、**Meet（交友）**、**Dating（自願開啟的戀愛）** 三個模組。原則：一個帳戶、多種用途、隱私隔離、自願參與；物品共享仍是首頁和核心。

本文件先分析現有代碼，再列出設計、遷移、權限、GPA 安全方案、分階段順序與風險。**Phase 1 已在本分支實作**，對照見最後一節。

---

## 1. 現有代碼結構分析

| 項目 | 現況 |
|---|---|
| 技術棧 | Django 5.2 單體應用，伺服器渲染模板，無前端框架（僅 `ai.js` 等少量原生 JS，CSP `script-src 'self'`）。本機 SQLite（IMMEDIATE 交易）、生產 PostgreSQL（Neon／Compose）。Render 免費方案或香港 VPS + Caddy。 |
| 帳戶與學校郵箱認證 | Django `User` + `Profile`（暱稱、頭像、`verified`、`restricted`）。一次性郵件登入連結（雜湊、15 分鐘、單次 POST 消耗），無密碼。域名白名單原本只來自環境變數 `ALLOWED_EMAIL_DOMAINS`。`@member` 裝飾器每次請求重新檢查已驗證、未受限、域名仍被允許。 |
| 個人資料 | `Profile` 單表；上一版已加入交友欄位 `bio`、`interests`、`social`（開放交友）、`dating`（預設關閉）。 |
| 訊息 | `Thread`（兩人：`first`/`second`，可關聯物品、訂單、搭子帖或為好友直聊）+ `Message` + `Notification`。每用戶每分鐘 30 則限流。 |
| 交友前身（上一版） | `Buddy`/`BuddyJoin`（搭子活動，相當於 Meet 的活動邀約）、`Connection`（好友請求及秘密心動）、`Block`。好友與心動只限「透過借用或同一搭子活動認識」的人。 |
| 權限 | 視圖內明確檢查擁有者／參與者；`PermissionDenied`／404。Django admin 用自訂唯讀 ModelAdmin；`Report` 舉報表。 |
| 檔案儲存 | 私有：`FileSystemStorage`（`private-media/`）或 `DatabaseStorage`（`MEDIA_STORAGE=db`，Render 免費方案）。沒有公開 URL，只經 `/media/<kind>/<pk>/` 授權視圖輸出，`no-store` + CSP。圖片經 Pillow 解碼、限像素、重編碼 JPEG、移除 EXIF。 |
| 管理後台 | Django admin；訂單糾紛有 admin action 並寫入 `Audit`。 |
| 多大學支援 | **原本沒有**。學校只存在於環境變數及 UI 文案（「FOR THE CITYUHK COMMUNITY」）。 |
| 測試 | Django TestCase，含雙執行緒競爭測試；分支開始時 67 項全部通過。 |

**可直接重用**：登入與學校郵箱驗證、`Profile`、`Thread`/`Message`/`Notification`（含限流）、`Block`、`Report`、私有儲存與 `/media/` 授權模式、`clean_image()`、`throttle()`、admin action 與審計模式、整套 CSS 元件（panel、card-grid、tabs、list-row）。**不需要**另建帳戶、聊天或認證表。

---

## 2. 新增／修改的檔案（Phase 1）

新增：

- `market/teamup.py`：Team Up 與 GPA 服務層（申請、審核、成員、公告、解散、邀請；證明檔清理、提交、撤回、審核、保留期刪除）。
- `market/connect.py`：Connect 首頁、組隊、找隊友、學術主頁、分模組設定頁、GPA 頁的視圖。
- `market/migrations/0006_campus_connect.py`：結構遷移；`0007_seed_universities.py`：學校種子資料及既有用戶回填。
- `market/static/market/redact.js`：上傳成績單前在瀏覽器內遮蓋學號等資料。
- 模板：`connect.html`、`connect_tabs.html`、`teams.html`、`team.html`、`people.html`、`academic.html`、`settings.html`、`settings_tabs.html`、`gpa.html`、`gpa_submit.html`、`gpa_line.html`。

修改：

- `models.py`：`University`、`Profile.university`、`AcademicProfile`、`GpaVerification`、`GpaAudit`、`Team`、`TeamApplication`、`TeamMember`；`Thread` 支援小組聊天；`Report` 新增 `team` 類別。
- `services.py`：登入域名改為「環境變數 ∪ 已啟用學校」；登入時按郵箱域名指派學校；小組聊天存取規則；`notify_once`；封鎖同時拒絕雙方待審的組隊申請。
- `views.py`：訊息中心納入小組聊天；`/media/gpa/` 私有輸出及審計；基本資料頁拆分。
- `forms.py`：基本／交友／戀愛／學術資料分開的表單；組隊表單；GPA 表單。
- `admin.py`：學校管理、組隊帖管理、GPA 審核佇列（只限有 `review_gpa` 權限的職員）。
- `cleanup_auth` 指令與 `render-start.sh`：每日／每次啟動刪除過了保留期的 GPA 證明。
- 模板：導航「找搭子」改為「校園連結 Connect」；首頁只保留物品共享分頁；訊息、聊天、個人頁、朋友頁、社群守則（新增第 09 條）。

---

## 3. 資料庫遷移設計

需求中的表與實際實作的對應：

| 建議表 | 實作 | 說明 |
|---|---|---|
| Universities | `University` | `code`、`name`、`country`、`email_domains`（逗號分隔）、`grading_scale`、`verification_policy`、`enabled`。種子：CityUHK 啟用；HKU（connect.hku.hk）、CUHK（link.cuhk.edu.hk）、HKUST（connect.ust.hk）**預設停用**，啟用前請在 admin 核實域名及滿分制。 |
| （用戶關聯學校） | `Profile.university` FK | 登入時按郵箱域名指派；遷移時回填既有用戶。不讓用戶自選，避免冒認學校。 |
| AcademicProfiles | `AcademicProfile` | 主修、年級、興趣領域、技能、找隊友的課程、想參與的項目類型、項目經歷、作品連結、`public`（預設 **False**）、`cross_school`。 |
| GpaVerifications | `GpaVerification` + `GpaAudit` | 數值、滿分制、學校、學期、狀態 `draft/pending/verified/rejected`、公開方式 `hidden/band/exact`（預設 hidden）、私有檔案、提交／審核時間、審核員、備註、檔案刪除時間。約束：`0 ≤ value ≤ scale`、每人最多一份 `pending`。自訂權限 `review_gpa`。 |
| TeamPosts + Teams | `Team` | MVP 中每份招募帖就是一個小組，分兩表只會多一層 join；招募欄位（課程、類型、人數、技能、周期、截止、方式、跨校、狀態）與小組欄位（公告、解散）同表。日後若需要「一個小組多輪招募」再拆出 `TeamPost`。索引：`(status, university)`、`course_code`。 |
| TeamApplications | `TeamApplication` | 申請人、留言、`share_profile`（每份申請獨立的明確同意）、狀態、決定時間；`(team, user)` 唯一。 |
| TeamMembers | `TeamMember` | `leader`／`member`；`(team, user)` 唯一。 |
| （小組聊天） | `Thread.team`（OneToOne） | 重用現有訊息系統；小組聊天的 `first`/`second` 為空，存取權跟隨**現任**成員資格。 |
| SocialProfiles | `Profile.bio/interests/social`（已存在） | Phase 2 再決定是否拆表。 |
| DatingProfiles / Preferences / Likes / Matches | 現有 `Profile.dating` + `Connection(kind='crush')` | 上一版的最小實作；Phase 3 會遷移到獨立的戀愛資料表（見第 6 節）。 |
| UserBlocks / Reports | `Block`、`Report`（已存在） | 封鎖跨模組生效；`Report` 新增 `team` 類別。 |

遷移安全性：全部為新增表、新增可空欄位，以及把 `Thread.first/second` 改為可空（只放寬）。沒有刪除或改名欄位，既有資料不受影響。已在一個含真實資料的 0005 資料庫上實測遷移及回填。

---

## 4. 模組間權限隔離

| 資料 | 誰可見 |
|---|---|
| 組隊招募帖 | 公開（同物品、尋物帖），只顯示項目資料及隊長暱稱，不顯示聯絡方式。列表預設只顯示本校；學生選擇「跨校」時才加入**接受跨校**的他校小組。 |
| 小組成員名單、公告、小組聊天 | 只限現任成員；離開或被移出即失去存取權。解散後聊天唯讀。 |
| 組隊申請 | 申請人本人及該隊長。 |
| 學術資料 | 預設只有本人。`public=True` 時只限**已登入的已驗證學生**（匿名不可見）；或申請時勾選「讓這位隊長查看」，只對該隊長、且申請在待審／已接受時有效。公開個人頁（`/people/<id>/`）**不顯示**學術資料或 GPA，只有連結。 |
| 找隊友名錄 | 只列 `public=True` 的學術資料；不設 GPA 篩選或排序。 |
| 邀請 | 只能邀請公開學術資料的人；邀請只是一條通知，不會開私訊。 |
| GPA | 草稿和審核中只有本人可見；已審核仍預設隱藏，本人選擇「數值」或「區間」才顯示，只出現在學術主頁及（已分享的）申請卡片。 |
| GPA 證明檔 | 本人及有 `review_gpa` 權限的職員；其他職員、用戶、匿名一律 403。 |
| 交友資料 | 只在開啟「開放交友」時顯示自我介紹和興趣。 |
| Dating | 預設關閉；Connect 首頁在關閉時只顯示自願加入說明，不顯示任何人的資料。心動只對「透過借用或搭子活動認識」的人生效，**小組隊友不算認識**（`met_ids` 不讀取組隊資料），所以組隊不能被用來發出戀愛請求，也不會帶來戀愛推薦。 |
| 封鎖 | 跨模組：移除好友及心動、拒絕雙方的搭子報名和待審組隊申請、隱藏對方的搭子帖和組隊帖、阻止申請及邀請、關閉非訂單對話（訂單對話保留以完成歸還）。 |

設定頁按模組分開：基本資料、學術 · Team Up、GPA、交友 · Meet、戀愛 · Dating。學術資料不會被複製到交友或戀愛資料。

---

## 5. GPA 審核的檔案安全與私隱方案

1. **自願**：不填、存為私密草稿、提交審核、審核後公開數值／區間／隱藏，都由用戶決定，可隨時隱藏或刪除。
2. **記錄評分制度**：每份紀錄保存學校、滿分制（預設取該校 `grading_scale`，可修改）、學期與狀態；不假設各校同一標準。
3. **上傳前遮蓋**：圖片可在瀏覽器內拖曳黑框遮蓋學號／證件號碼（`redact.js`），只上傳遮蓋後的圖片；PDF 請先在其他工具遮蓋或改用截圖。
4. **檔案驗證**：圖片經 Pillow 解碼、限 5 MB 及像素、重編碼並移除 EXIF；PDF 限 10 MB、檢查檔頭，拒絕含 JavaScript、啟動動作、附件、XFA 等互動內容的 PDF（保護審核員）。
5. **私有儲存**：存於私有 storage（檔案系統或資料庫），無公開 URL；只經 `/media/gpa/<id>/` 輸出，`Cache-Control: private, no-store`、`Content-Security-Policy: default-src 'none'; sandbox`，PDF 以附件下載。
6. **審核權限**：只有 `is_staff` 且擁有 `market.review_gpa` 權限的帳號能看到審核佇列、開啟證明及作決定；不可審核自己的申請；數值欄位在後台唯讀。
7. **審計**：提交、撤回、刪除、**審核員每次開啟證明**、通過、拒絕、檔案到期刪除都寫入 `GpaAudit`。審計只記錄動作，不記錄 GPA 數值；紀錄刪除後審計仍保留。
8. **保留政策**：審核決定後 `GPA_PROOF_RETENTION_DAYS`（預設 14）天自動刪除證明檔，狀態保留；撤回或刪除紀錄即時刪檔；帳戶刪除（CASCADE）時亦由 `post_delete` 訊號刪檔。由 `cleanup_auth`（每日）及 Render 啟動時執行。
9. **人工審核**：不使用 AI 判斷真偽。
10. **用語**：一律寫「平台已審核」，並註明「並非大學官方認證」；除非日後獲學校正式授權。
11. **無排名**：不設 GPA 排行，名錄不按 GPA 篩選或排序，GPA 不出現在交友或戀愛頁面。

---

## 6. 分階段實施順序

**Phase 1（本分支已完成）**：多大學資料模型；學術資料；組隊招募帖、篩選（學校、課程、技能、類型）、申請、隊長審核、成員名單、公告、小組聊天、離開／移出／解散；找隊友名錄及邀請；GPA 資料結構、提交、遮蓋、審核後台、公開設定、審計、保留期刪除；分模組設定頁；Connect 入口。

**Phase 2：Meet**
- 把 `Profile` 的交友欄位拆成 `SocialProfile`（興趣標籤改為結構化標籤表，便於篩選）。
- 「瀏覽主動公開的交友資料」頁（只列 `social=True`，按興趣、學校篩選）。
- 活動邀約：沿用搭子活動，加入喝咖啡、看電影、羽毛球等快捷類型。
- 雙向社交連接：目前「必須先認識」才可加好友；Phase 2 允許對公開交友資料發出**需對方接受**的連接請求，並加每日上限。
- 借物完成後的「互相關注」：沿用現有訂單頁入口，確保需要雙方同意。

**Phase 3：Dating**
- 新表：`DatingProfile`（暱稱、介紹、照片、興趣、意向、可見狀態）、`DatingPreference`（希望認識的對象、學校範圍、是否跨校）、`DatingLike`、`DatingMatch`；把現有 `Connection(kind='crush')` 遷移為 `DatingLike`。
- 年齡資格：目前 18+ 為自行聲明。大學郵箱不能證明年齡，Phase 3 需加入出生日期聲明及可選的人工年齡核實（與 GPA 相同的私有檔案及審計流程），並在資料中區分「自行聲明」與「已核實」。
- 基礎推薦：只按學校、雙方明確偏好、興趣標籤；不使用 GPA、課程或組隊紀錄。
- 雙向喜歡才配對；配對後聊天；隨時取消配對、封鎖、舉報。

**Phase 4：優化**：更好的隊友推薦、每週校園配對、項目評價及信譽、跨大學協作、任務看板／文件協作。暫不做 AI 推薦、付費會員、公開 GPA 排名。

另需排期：**帳戶自助註銷及資料清理**。目前 GPA 檔案在帳戶刪除時會一併刪除，但訂單以 `PROTECT` 保護交易紀錄，需設計「匿名化而非刪除」流程，並按 PDPO（香港）及日後北美市場要求制定保留政策。

---

## 7. 對現有 Share 功能的風險

| 風險 | 處理 |
|---|---|
| `Thread.first/second` 改為可空 | 物品、訂單、搭子、好友對話仍一定有兩位參與者；存取改經 `in_thread()`，對兩人對話的判斷與以前相同。原有權限測試全部通過。 |
| 登入域名來源改變 | 環境變數 `ALLOWED_EMAIL_DOMAINS` 仍然有效（取聯集），既有部署不需改設定。`@member` 每次請求多一次學校查詢（小表）。 |
| 導航改動 | 首頁只剩物品共享兩個分頁；「找搭子」移到 Connect 內，舊連結 `/buddies/` 仍可用。 |
| Render 啟動多執行 `cleanup_auth` | 以 `|| true` 包住，失敗不阻止啟動。 |
| 部分生產用戶沒有學校 | 若部署使用不在 `University` 表內的域名，該用戶可借物但無法發起組隊（頁面會提示聯絡管理員）；在 admin 新增對應學校即可。 |
| PostgreSQL 未在本機實測 | 新約束（部分唯一索引、含 F() 的檢查約束）兩種資料庫都支援；上線前仍需在 staging 跑一次遷移。 |

---

## 8. 驗收標準對照（Phase 1）

| 驗收標準 | 狀態與測試 |
|---|---|
| 原有物品共享功能不受破壞 | 原有 67 項測試全部通過。 |
| 學生能夠創建小組並申請加入 | `TeamUp.test_create_apply_review_members_chat_and_disband` |
| 小組申請需要明確審核和授權 | 只有隊長可接受／拒絕；申請不帶來聊天權限；名額上限在交易鎖內檢查。 |
| GPA 未經審核不能顯示認證標記 | 草稿、審核中均不顯示（`GpaReview.test_review_flow_privacy_and_retention`）。 |
| GPA 未經用戶同意不能公開 | 審核通過後仍預設隱藏，需用戶選擇數值或區間。 |
| 未授權用戶無法讀取私密成績證明 | 匿名、其他學生、無權限職員均 403；開啟記錄於審計。 |
| Dating 默認關閉，且與學術合作資料隔離 | `Profile.dating` 預設 False；隊友不算「認識」，不能互送心動；戀愛頁面不讀取學術或 GPA。 |
| 數據結構支持後續接入其他大學 | `University` 表；`Universities` 測試：在 admin 啟用 HKU 後即可登入並指派學校，停用後立即失去存取。 |
| 主要流程具有必要的權限校驗和測試 | 共 75 項測試；另以變異測試確認關鍵權限檢查被移除時測試會失敗。 |
