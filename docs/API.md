# API Contract

## `GET /api/health`

返回服务、数据库、OpenD 连接和 SQLite 加密准备状态。

## `POST /api/sync/manual`

触发一次手动全量同步。同步失败会记录失败原因，不会生成新的交易建议。

## `GET /api/sync/status`

返回最近一次同步任务状态、时间、失败原因和新增/更新数量。

## `GET /api/dashboard`

返回首页需要的组合摘要、今日行动清单和同步状态。

## `GET /api/positions`

返回最新持仓快照。可选 query 参数：

- `layer`：按仓位类型筛选。

## `GET /api/positions/{code}`

返回单个标的的持仓详情、关联决策卡和最近一次 AI 分析。

## `POST /api/positions/{code}/ai-analysis`

为单个标的生成 AI 辅助分析。配置 `DEEPSEEK_API_KEY` 时调用 DeepSeek；未配置或外部调用失败时，使用本地规则降级分析。

返回：

```json
{
  "ai_analysis": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "status": "success",
    "output": {
      "recommendation": "观察",
      "conclusion": "当前只适合复核和跟踪。",
      "reasons": [],
      "risks": [],
      "invalid_conditions": [],
      "missing_data": []
    }
  }
}
```

## `PATCH /api/positions/{code}/layer`

保存用户手动仓位类型修正。

请求：

```json
{
  "position_layer": "核心长期仓",
  "reason": "用户在工作台手动修正"
}
```

## `GET /api/review`

返回最近一次盘后复盘，包括组合摘要、建议回顾、用户行为摘要、后续表现评估和明日关注。

## `GET /api/profile`

返回最近一次用户交易画像，包括仓位分层比例、置信度和偏好标签。

## `GET /api/data/status`

返回同步任务和各数据源新鲜度状态。

## `POST /api/data/delete-local`

删除本地账户、持仓、成交、建议、提醒、复盘和同步记录。请求必须包含：

```json
{
  "confirmation": "DELETE_LOCAL_DATA"
}
```
