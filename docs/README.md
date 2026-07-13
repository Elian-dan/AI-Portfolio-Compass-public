# AI 炒股辅助决策 Agent 本地工程

本工程是本地 Web 工作台：前端运行在浏览器，后端运行在本机。账户、持仓、成交保持只读同步或本地导入；行情和新闻采用可配置 provider 架构，只展示 API 联通状态、最近同步时间和错误原因。

## 目录

- `backend/`：FastAPI 服务、富途只读适配器、同步任务、仓位分类、决策卡、提醒、复盘、画像规则。
- `frontend/`：React + Vite 工作台，覆盖首页、持仓、机会、提醒、复盘、我的画像、设置。
- `data/`：本地 SQLite 数据目录，不提交真实账户数据。
- `docs/`：启动、OpenD、数据安全说明。

## 一键启动

推荐使用本地服务控制脚本。它会在后台启动前端和后端，并持续做健康检查；如果某个服务异常退出，会自动重启。

```bash
./scripts/start.sh
```

默认访问：

```bash
http://127.0.0.1:4400/
```

查看状态：

```bash
./scripts/health.sh
```

重启服务：

```bash
./scripts/restart.sh
```

停止服务：

```bash
./scripts/stop.sh
```

运行日志保存在 `.runtime/logs/`，该目录不会提交到 Git。

## 手动后端启动

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

## 手动前端启动

```bash
cd frontend
npm install
npm run dev
```

默认访问 `http://127.0.0.1:4400`。

## 行情与新闻数据源

开源版本默认不内置任何商业 API Key。用户按自己的券商账户、市场权限和 API 订阅配置数据源；未配置时页面显示 `not_configured`，不作为系统错误。

| 市场 | 行情优先级 | 新闻/公告优先级 | 说明 |
| --- | --- | --- | --- |
| 美股 US | Alpaca、Polygon/Massive、FMP、Alpha Vantage、Futu | Marketaux、Alpha Vantage、FMP、SEC EDGAR | Alpaca 免费层覆盖有限；SEC EDGAR 只缓存标题、链接、发布时间和标的。 |
| 港股 HK | Futu、Tushare、FMP、Alpha Vantage | Futu、HKEXnews | Futu 优先使用本地 OpenD 授权；HKEXnews 只缓存公告元数据。 |
| A股 CN | Futu、Tushare Pro、AKShare | 巨潮资讯 CNINFO | Tushare Pro 适合生产配置；AKShare 仅作为社区/本地可选源。 |

可选环境变量：

```bash
MARKET_DATA_PROVIDER_PRIORITY=alpaca,polygon,fmp,alpha_vantage
NEWS_PROVIDER_PRIORITY=marketaux,alpha_vantage,fmp
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPHA_VANTAGE_API_KEY=
FMP_API_KEY=
POLYGON_API_KEY=
MARKETAUX_API_TOKEN=
TUSHARE_TOKEN=
```

行情表会记录 `provider`、`market`、`exchange`、`is_delayed`、`license_note`；新闻表会记录 `provider`、`market`、`news_type`，并区分市场新闻、公告和 filing。公告源默认只保存元数据与原始链接，不全文缓存，降低版权和再分发风险。

## 富途 OpenD

富途 / moomoo OpenD 仍是券商型数据源优先项，只使用只读能力：

- 账户列表
- 资金
- 持仓
- 历史成交
- 自选股
- 行情快照

不会实现或调用：

- 下单
- 撤单
- 改单
- 交易解锁

默认环境变量见根目录 `.env.example`。如需分析真实账户，保持：

```bash
FUTU_TRD_ENV=REAL
```

OpenD 未连接时，工作台会展示同步失败和最近一次数据状态，不生成新的交易建议。

## DeepSeek AI 分析

标的详情页提供“生成 AI 分析”。默认配置为 DeepSeek：

```bash
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

后端只发送单个标的分析需要的最小上下文：持仓摘要、仓位分类、决策卡、画像摘要和数据新鲜度。不会发送本地数据库文件、交易密码，也不会调用任何下单接口。

未配置 `DEEPSEEK_API_KEY` 时，系统会自动使用本地结构化规则生成降级分析，并在页面上标明“本地规则”。

## 本地 OCR

图片和扫描 PDF 导入默认关闭 OCR，因此页面出现“本地 OCR 未启用”是正常保护行为。启用前需要安装本地 OCR 依赖，并在根目录 `.env` 中打开：

```bash
cd backend
pip install -r requirements-ocr.txt
```

```bash
OCR_PROVIDER=paddleocr
OCR_LANG=ch
```

改完后重启后端或执行 `./scripts/restart.sh`。注意：当前 OCR 只负责识别图片文字；识别结果还没有完整规则自动转换为账户/持仓/成交结构，正式导入仍优先使用 Excel 模板或文字型 PDF。

## 本地数据

开发环境默认使用普通 SQLite：

```bash
DATABASE_URL=sqlite:////Users/ddg/Documents/AI Portfolio Compass/data/ai_trader.db
```

正式使用前应接入 SQLCipher 或同等 SQLite 加密方案，并配置：

```bash
DB_ENCRYPTION_KEY=your-local-secret
```

根目录 `.gitignore` 已忽略 `data/`、`.env` 和数据库文件，避免提交真实资产数据。

## 测试

```bash
pytest
```

当前无需安装 FastAPI/SQLAlchemy 也能运行核心规则测试；API 合约测试会在依赖未安装时自动跳过。
