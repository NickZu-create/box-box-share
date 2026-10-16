# 免費部署：Render + Neon + Resend

這是不用買伺服器和域名的試用部署方式。原本的香港 VPS（Docker）方式見 [DEPLOYMENT.md](DEPLOYMENT.md)，兩者可以並存。

| 部分 | 服務 | 免費額度 |
|---|---|---|
| 網站 | Render 免費 Web Service（新加坡） | 每月 750 小時；15 分鐘沒人訪問會休眠，下次打開約等 1 分鐘 |
| 資料庫和照片 | Neon 免費 PostgreSQL（新加坡） | 1 GB；照片也存在資料庫裡（`MEDIA_STORAGE=db`） |
| 登入郵件 | Resend 免費 API | **沒有自己的域名時，只能寄到你註冊 Resend 用的郵箱** |

## 限制

- **只有你自己能登入。** 網站只接受 `@my.cityu.edu.hk` 郵箱，Resend 測試模式又只寄給帳號本人，所以要用你的 CityU 郵箱註冊 Resend。其他人可以瀏覽，但收不到登入郵件。
- **想讓其他人也能登入：** 買一個域名，在 Resend 驗證它，然後把 `DEFAULT_FROM_EMAIL` 改成該域名的地址，例如 `Box Box Share <login@你的域名>`。程式碼不用改。
- Render 免費版封鎖 SMTP 端口，所以郵件改用 Resend 的 HTTPS API（`RESEND_API_KEY`），不用 `EMAIL_HOST`。
- Render 免費版沒有永久硬碟，所以照片存在 Neon 資料庫，不會因為重啟消失。圖片仍然只透過網站的授權連結 `/media/...` 讀取。
- 免費版沒有遠端備份。Neon 有短期的時間點還原功能，正式營運前請另外安排備份。

## 步驟

### 1. 把程式碼放上 GitHub

建立一個 **Private** 倉庫，推送這個資料夾。`.gitignore` 已經排除了本機資料庫、`dev-mail/` 和 `.env`。

### 2. Neon 資料庫

1. 在 https://neon.com 註冊，建立 Project，Region 選 **AWS Asia Pacific (Singapore)**。
2. 在 **Connect** 裡複製連線字串，格式是 `postgresql://...neon.tech/neondb?sslmode=require...`。
3. 這串字含有資料庫密碼，**只貼到 Render 的環境變數裡**，不要貼到聊天或提交到 Git。

### 3. Resend

1. 用你的 **CityU 學校郵箱** 在 https://resend.com 註冊。
2. 到 **API Keys** 建立一個 key，權限選 Sending access。
3. 這個 key 同樣只貼到 Render。

### 4. Render

1. 在 https://render.com 用 GitHub 登入，授權它讀取這個倉庫。
2. 選 **New → Blueprint**，選這個倉庫。Render 會讀取 `render.yaml`，建立一個 Free 方案的 web service。
3. 它會要求你填兩個值：
   - `DATABASE_URL`：Neon 的連線字串。
   - `RESEND_API_KEY`：Resend 的 key。
4. `SECRET_KEY` 由 Render 自動隨機產生。
5. 部署完成後，網址是 `https://box-box-share.onrender.com`。如果名稱已被佔用，Render 會加上後綴，以頁面顯示為準。

**可選：管理員帳號。** 在 Render → Environment 加上以下三個變數，重新部署一次後就可以登入 `/admin/`：

- `DJANGO_SUPERUSER_USERNAME`
- `DJANGO_SUPERUSER_EMAIL`
- `DJANGO_SUPERUSER_PASSWORD`

建立好之後，可以把 `DJANGO_SUPERUSER_PASSWORD` 刪掉。

### 5. 檢查

- 打開網址，確認首頁、尋物廣場、減碳成效頁能正常顯示。
- 用你的 CityU 郵箱登入，確認收到郵件，連結可以登入。
- 發布一件物品並上傳照片。等 20 分鐘讓服務休眠，再打開網站，確認照片還在。

## 之後更新

推送到 GitHub 的 main 分支後，Render 會自動重新部署。資料庫結構的變更（migration）會在啟動時自動執行（見 `render-start.sh`）。
