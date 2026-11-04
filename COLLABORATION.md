# Box Box Share 协作开发

最新完整代码在 `main` 分支，它已包含此前的协作快照、付款页和演示版界面。`main` 连接 Render 自动部署：推送到 `main` 就会上线，所以请从 `main` 新建自己的分支，通过 Pull Request 合并；演示版和生成脚本也在这个分支里。

## 先看最新界面（无需安装项目依赖）

安装 Python 3.12，然后：

```sh
git clone https://github.com/NickZu-create/box-box-share.git
cd box-box-share
python -m http.server 8012 --bind 127.0.0.1 --directory output/design-preview
```

Windows 下也可双击根目录的 `start-preview.cmd`，它会在后台启动并打开预览。关闭终端不会停止该后台服务；电脑重启后需再次运行。也可运行 `python tools/preview_server.py`，仅启动而不打开浏览器。地址只在运行服务的本机可用，朋友需各自在自己的电脑启动。

macOS/Linux 的 Python 命令可能是 `python3`。打开：

- 简体中文：http://127.0.0.1:8012/hans/
- English：http://127.0.0.1:8012/en/
- 繁體中文：http://127.0.0.1:8012/zh/
- Buddy 接受后自愿入群示例：http://127.0.0.1:8012/hans/buddy/2/
- Messages：http://127.0.0.1:8012/hans/messages/
- Profile：http://127.0.0.1:8012/hans/profile/

必须通过本地服务器打开，不能双击 HTML。演示登录、订单、联系人和消息为合成数据；修改只存当前标签页，不发送给真实用户。

## 运行真实 Django 功能

使用未配置线上数据库或邮件凭证的本地终端。项目直接读取进程环境变量，不会自动加载 `.env`；不要把生产凭证复制到开发环境。默认使用本地 SQLite 和文件邮件。

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r requirements-showcase.txt
& ./.venv/Scripts/python.exe manage.py migrate
& ./.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
```

macOS/Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-showcase.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

真实功能在 http://127.0.0.1:8000/ ，新克隆默认是空数据库。迁移包含 0006 失物招领与拉黑、0007 可选学生资料与推荐、0008 Buddy 群聊、0009 物主收款码和 0010 出售、求购与联系方式。不要复制别人的 `data.sqlite3`、`private-media/` 或登录邮件来初始化账号。开发文件邮件里的链接可以登录对应账号，不能提交或转发。

## 修改预览与重新生成

布局生成器为 `output/build_preview_v3.py`，其余五个 helper 分别处理通用交互、交易演示、学生资料、群聊和本轮细节优化。`output/showcase-baseline/` 是冻结的合成基线，不从线上数据库读取。`output/design-preview/` 同时保存手工维护的 CSS/JS/图标和生成的 HTML，**不要清空这个目录**。

安装 `requirements-showcase.txt` 后，在项目根目录运行：

```powershell
& ./.venv/Scripts/python.exe output/build_preview_v3.py
```

macOS/Linux 使用 `.venv/bin/python`。构建更新 HTML 与资源版本号；重新加载本地预览查看。`public-demo/` 是本机另一个发布仓库，不属于这份协作快照，也不是构建依赖。更多说明见 [PREVIEW.md](output/design-preview/PREVIEW.md)。

## 当前功能边界

| 内容 | Django 项目 | 静态演示 |
| --- | --- | --- |
| 原有租借、申请审批、消息与好友 | 真实服务端流程 | 合成流程 |
| 失物招领、举报与拉黑 | 已实现 | 合成流程 |
| 付款页：物主收款码、微信/Alipay/FPS 按钮、HKD 换算（[PAYMENT.md](PAYMENT.md)） | 已实现，未做真机付款测试 | 示例订单入口、占位图和固定示例汇率 |
| 可选学生资料、专业/课程搜索、权重推荐 | 已实现 | 合成流程 |
| Buddy 群聊、接受后自愿入群、入群后历史边界 | 已实现 | 合成流程 |
| 出售/求购、直接购买、四条消息解锁联系方式（[MARKETPLACE.md](MARKETPLACE.md)） | 已实现并上线；迁移已在 PostgreSQL 成功运行，“两人同时购买”尚未在 PostgreSQL 上测试 | 已演示 |
| 学校 SSO 与课表 | 仅接口预留，未连接学校 | 不模拟学校登录 |
| 实时消息 | 需要手动刷新 | 需要手动刷新 |

请保持上述边界，不能把演示状态当成后台权限校验或已上线证据。手机和桌面已通过浏览器尺寸检查，尚未验证真机软键盘或完整辅助技术兼容性。

## 检查与分工

Windows：

```powershell
$env:SQLITE_TEST_PATH='collaboration-test.sqlite3'
& ./.venv/Scripts/python.exe manage.py test market --noinput
& ./.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
node output/test_demo_core.cjs
```

macOS/Linux：

```sh
SQLITE_TEST_PATH=collaboration-test.sqlite3 .venv/bin/python manage.py test market --noinput
.venv/bin/python manage.py makemigrations --check --dry-run
node output/test_demo_core.cjs
```

Node.js 仅用于演示规则测试，运行网站和构建预览无需 Node。当前 `main` 已通过 190 项 Django 测试；[最新检查与截图](output/payment-review/design-qa.md)。较早检查记录的测试数和截图反映当时版本。

每人从快照新建自己的分支，例如 `git switch -c feature/profile-edit`，通过 Pull Request 合并。当前仓库公开，朋友可直接克隆或 Fork；直接推送到本仓库需要仓库拥有者在 GitHub 添加其协作者账号。这次上传没有修改权限或邀请任何人。

`.env`、数据库、用户图片、登录邮件、构建日志、备份和本机发布信息不会进入代码快照。不要执行生产启动脚本来测试本地改动，也不要在开发步骤里部署 Render。
