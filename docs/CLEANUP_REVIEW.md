# 项目文件清理清单

生成日期：2026-07-06

## 建议直接删除的本机临时文件

这些文件是系统、缓存或运行时产物，删除后不会影响源码；再次运行项目时可能会重新生成。

| 路径 | 类型 | 当前大小 | 建议 |
| --- | --- | ---: | --- |
| `.DS_Store` | macOS 系统文件 | 12K | 可删除 |
| `frontend/.DS_Store` | macOS 系统文件 | 8K | 可删除 |
| `backend/.DS_Store` | macOS 系统文件 | 8K | 可删除 |
| `backend/app/.DS_Store` | macOS 系统文件 | 8K | 可删除 |
| `.pytest_cache/` | 测试缓存 | 约 12K | 可删除 |
| `backend/app/__pycache__/` | Python 缓存 | 小 | 可删除 |
| `backend/app/services/__pycache__/` | Python 缓存 | 小 | 可删除 |
| `.runtime/` | 本地运行状态和日志 | 约 16M | 可删除，尤其是日志 |
| `frontend/dist/` | 前端构建产物 | 小 | 可删除，需要时重新构建 |

## 不建议提交到远程仓库，但本机可保留

这些内容对本机运行有用，但不适合同步到 GitHub/Gitee。

| 路径 | 类型 | 当前大小 | 建议 |
| --- | --- | ---: | --- |
| `.env` | 本地密钥与配置 | 4K | 保留本机，不要上传 |
| `data/ai_trader.db` | 本地数据库 | 5.1M | 保留本机，除非确认只是测试数据 |
| `backend/.venv/` | Python 虚拟环境 | 未完整统计 | 保留或重建，不要上传 |
| `frontend/node_modules/` | 前端依赖目录 | 未完整统计 | 保留或重装，不要上传 |

## 应该保留并提交的项目文件

这些是项目源码、文档、依赖声明或协作需要的配置。

| 路径 | 说明 |
| --- | --- |
| `.gitignore` | 控制哪些本地文件不进入版本库 |
| `.env.example` | 给第二台电脑参考的环境变量模板 |
| `pyproject.toml` | Python 项目配置 |
| `backend/requirements.txt` | 后端依赖清单 |
| `backend/app/` | 后端源码 |
| `backend/tests/` | 后端测试 |
| `frontend/package.json` | 前端依赖与脚本 |
| `frontend/package-lock.json` | 前端依赖锁定文件 |
| `frontend/index.html` | 前端入口 |
| `frontend/src/` | 前端源码 |
| `docs/` | 项目文档 |
| `scripts/` | 启停和健康检查脚本 |
| `AI炒股辅助决策Agent_PRD.md` | 产品需求文档 |
| `AI炒股辅助决策Agent_功能架构图.png` | 功能架构图 |

## 当前忽略规则检查

`.gitignore` 已经覆盖了主要本地生成物：

- `data/`
- `.runtime/`
- `.env`
- `.env.*`，但保留 `.env.example`
- `.pytest_cache/`
- `.venv/`
- `node_modules/`
- `frontend/dist/`
- `.DS_Store`

整体看，当前忽略规则是合理的。真正需要你决定的是：

1. `data/ai_trader.db` 是否只是测试数据。如果是，可以删除；如果包含你要保留的本地数据，就先留着。
2. `.runtime/logs/backend.log` 已经有约 16M，可以优先清理。
3. `AI炒股辅助决策Agent_PRD.md` 和架构图是否要作为项目正式文档保留在根目录，或者之后移动到 `docs/`。
