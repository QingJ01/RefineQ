# RefineQ（砺问）

RefineQ 是面向高中生、大学生和高级学习者的个人学习 Agent。用户只需说明想学什么，系统会识别学习方向，自动建立或切换学习空间，并持续关联资料、计划、练习和进度。

它不会把“聊过了”当成“学会了”。掌握度由诊断、作答、复习和资料引用共同支撑。

## 主要能力

- 从自然语言中识别学习意图，自动建立、复用或切换个人学习空间。
- 上传 PDF、DOCX、TXT 和 Markdown；文本类资料本地解析，扫描 PDF 可启用 OCR。
- 使用 PostgreSQL 保存账号、学习状态与配置，使用 pgvector 做语义检索，并与关键词检索混合排序。
- 根据个人资料生成题目，使用结构化评分标准智能判分，记录薄弱点和错因。
- 根据截止日期、掌握度和遗忘情况生成今日学习计划。
- 在 Agent 对话中自动带入当前目标、薄弱点、计划和资料引用。
- 管理员统一配置模型推理、Embedding、OCR 和 S3 兼容对象存储；密钥加密后保存在服务端。
- 外部 AI 暂不可用时，保留确定性的空间路由、出题与评分降级流程。

## 技术栈

- 后端：Python 3.11–3.13、FastAPI、SQLAlchemy、PostgreSQL、pgvector
- 前端：Next.js 16、React 19、TypeScript
- 文件：本地解析 PyMuPDF/python-docx；本地或 S3 兼容对象存储
- 部署：Docker Compose、Caddy、PostgreSQL 17 + pgvector 0.8.2
- 质量：pytest、Vitest、ESLint、Playwright、GitHub Actions

## 本地开发

未设置 `REFINEQ_DATABASE_URL` 时，开发和测试会使用 `data/system/refineq.sqlite3`。生产环境使用 Compose 中的 PostgreSQL + pgvector。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-build.lock
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e .

Set-Location apps/web
npm ci
Set-Location ../..
```

启动后端：

```powershell
python -m uvicorn refineq.api.app:app --host 127.0.0.1 --port 8000 --reload
```

另开终端启动前端：

```powershell
Set-Location apps/web
$env:REFINEQ_API_ORIGIN = "http://127.0.0.1:8000"
npm run dev
```

打开 `http://127.0.0.1:3000`。

## 创建管理员

密码不会写入仓库或配置文件：

```powershell
$env:REFINEQ_ADMIN_PASSWORD = "使用至少 12 字节的强密码"
refineq-admin --email qingj1314@163.com --display-name QingJ01
Remove-Item Env:REFINEQ_ADMIN_PASSWORD
```

管理员登录后，可从学习空间页面进入“系统管理”，统一配置：

- 模型推理：OpenAI 兼容 endpoint、模型名、API Key
- 语义检索：Embedding endpoint、模型名、API Key
- 扫描识别：支持视觉输入的 OCR 模型
- 文件存储：本地存储或 S3/MinIO/R2 等 S3 兼容服务

PDF、DOCX、TXT、Markdown 的基础文字提取不需要 API；只有扫描 PDF 才需要 OCR。所有配置均支持服务端连通性测试，密钥只返回掩码提示。

## 生产部署

```powershell
Copy-Item .env.example .env
# 修改 .env 中的数据库密码、数据库 URL 和 Fernet 加密密钥
docker compose --env-file .env -f infra/compose.yml up -d --build
```

详细步骤见 [部署指南](docs/deployment.md) 和 [运维指南](docs/operations.md)。

## 验证

```powershell
python -m pytest -q
python -m ruff check src tests scripts
python scripts/scan_secrets.py

Set-Location apps/web
npm test
npm run lint
npm run build
```

## License

本项目使用 [Apache License 2.0](LICENSE)。依赖组件许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
