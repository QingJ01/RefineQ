# RefineQ（砺问）

RefineQ 是面向高中生、大学生和高级学习者的个人学习 Agent。用户只需说出“今天
想学什么”，系统会自动识别学习方向、建立或切换学习空间，并恢复该方向下的资料、
计划、练习与进度。用户也可以上传自己的教材、讲义、试卷和笔记。

它不会把“聊过了”当成“学会了”。掌握度必须由作答、复习和引用证据共同支撑。

## 主要能力

- 根据自然语言意图自动建立、复用或切换个人学习空间，并在刷新后恢复现场。
- 上传 PDF、DOCX、Markdown 和纯文本资料，建立按用户与学习空间隔离的知识索引。
- 使用 BKT 更新掌握度，用诊断结果和截止日期生成可解释的今日计划。
- 基于个人资料生成题目，使用结构化评分量表判分并解释优点、缺口和误区。
- 保存作答、错因、难度变化与间隔复习状态，形成连续学习证据。
- 在 Agent 对话中自动带入当前目标、薄弱点、计划和资料引用。
- 模型未配置或暂时不可用时，自动使用确定性路由、出题和判分降级流程。
- 提供中英文界面、每位学习者独立的模型设置、本地备份恢复和容器化部署。

## 技术栈

- 后端：Python 3.11–3.13、FastAPI、Pydantic、SQLite/JSON
- 前端：Next.js 16、React 19、TypeScript
- 质量：Pytest、Vitest、ESLint、Playwright、GitHub Actions
- 部署：Docker Compose、Caddy

## 本地开发

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

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

## 验证

```powershell
python -m pytest -q
python -m ruff check src tests scripts

Set-Location apps/web
npm test
npm run lint
npm run build
```

运维脚本和容器部署方式见 `docs/`。运行时学习数据保存在 `REFINEQ_DATA_ROOT`，不会
进入源码仓库。

常用运维命令：

```powershell
python scripts/seed_demo.py --data-root .\data-demo
python scripts/backup.py .\backups\refineq.zip --data-root .\data
python scripts/restore.py .\backups\refineq.zip .\restored-data
python scripts/migrate_workspaces.py .\data .\backups\before-workspaces.zip
```

完整的校验规则与迁移方式见 [运维指南](docs/operations.md)。

## License

本项目使用 [Apache License 2.0](LICENSE)。依赖组件的许可说明见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
