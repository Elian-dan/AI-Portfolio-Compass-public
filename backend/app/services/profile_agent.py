from __future__ import annotations

from datetime import datetime, timezone
import json
import time
from typing import Any, Iterable
from urllib import request

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AIWorkflowRun
from app.services.ai_engine import call_llm_payload
from app.services.ai_runtime import active_ai_runtime, runtime_can_call_external
from app.services.profile_agent_tools import annotate_model_derived_percentages, default_tool_registry, now_iso, validate_report
from app.services.profile_workflows import (
    WORKFLOW_LABELS,
    build_artifacts,
    build_calculation_audit_pack,
    build_home_summary_cards,
    build_workflow_context,
    workflow_run_to_dict,
)


MAX_AGENT_TURNS = 12

AGENT_SYSTEM_PROMPT = """你是一个受控自主 AI 投顾 Agent。
你必须自主决定下一步调用哪个工具，但只能调用工具列表中的只读工具。
你不能下单、改单、撤单或输出强交易指令。
每次只输出一个严格 JSON 对象，不要 Markdown，不要隐藏推理链。
JSON schema:
{
  "thought_summary": "展示给用户的简短思考，不超过80字",
  "tool_name": "工具名",
  "tool_args": {},
  "why": "为什么调用该工具，不超过80字",
  "expected_observation": "期望得到什么，不超过80字"
}
当数据足够生成报告时，调用 finalize_report。
如果 workflow_type 是 portfolio_diagnosis，调用 finalize_report 时必须在 tool_args.home_summary_cards 中给出首页诊断摘要卡：本次体检结论、优先复核；必须使用 overall_verdict、priority_review 两个 key。内容要告诉用户当前结论、先看哪里、为什么看，不要字段名、裸指标或工具调试文本。
"""

REPORT_SYSTEM_PROMPT = """你是一个只做辅助决策的投资组合分析 Agent。
请基于 calculation_audit_pack、已调用工具的 observation 和章节模板输出中文 Markdown 报告。
要求:
1. 必须说明权重口径。
2. 关键财务数字只能引用 calculation_audit_pack，不得自行计算或发明数字。
3. 如 K线、行情或新闻缺失，必须说明数据不足。
4. 不得输出立即买入、立即卖出、必涨、必跌、稳赚、满仓等强指令。
5. 必须区分事实数据、Agent 判断和风险提示。
6. 每个关键数字必须写成“事实来源 + Agent 判断 + 建议关注”。
7. Markdown 版式必须层级清晰：
   - 全篇不输出 `#` 一级标题。
   - 每个主章节只使用一个 `## 一、...` 标题。
   - 章节内固定使用 `### 事实数据`、`### Agent 判断`、`### 建议关注` 等三级标题组织内容。
   - 三级标题下如需再拆分，使用 `####` 四级标题，不要用加粗文本伪装标题。
   - 章节之间使用 `---` 分隔。
   - 关键结论可用 `>` 引用块突出，但不要把整章都放进引用块。
   - 表格前后必须留空行，列表使用短句，避免连续长段落堆叠。
"""

CHAPTERS = [
    ("一、组合总览", "总资产、基础货币、现金比例、数据时间、权重口径、第一大合并标的和 Top5 权重。"),
    ("二、持仓明细表", "按 skill 固定字段输出 Top10-15 合并持仓明细。"),
    ("三、集中度与重叠风险", "单一标的、Top5、行业/主题、货币和跨账户重复持有风险。"),
    ("四、收益贡献归因", "收益贡献榜，必须使用 return_contribution = weight × profit_loss_ratio。"),
    ("五、行情与 K线诊断", "本地行情、K线状态、缺失数据和降级说明。"),
    ("六、事件与新闻风险", "近期新闻和事件风险；缺失时必须明确降级。"),
    ("七、风险雷达", "集中度、波动、流动性、货币、主题和数据缺失六类风险。"),
    ("八、可执行关注清单", "只使用复核、观察、再平衡、补充数据、设置提醒。"),
]

ASSET_ALLOCATION_CHAPTERS = [
    ("一、配置目标确认", "风险承受能力、投资期限、流动性需求、目标收益和数据状态。"),
    ("二、当前组合偏离诊断", "当前资产、货币、主题、现金和集中度相对目标配置的偏离。"),
    ("三、建议目标配置", "目标比例、当前比例、偏离、估算金额、参考标的和理由。"),
    ("四、再平衡路径", "先集中度、再现金防御、再低相关资产、最后主题暴露。"),
    ("五、触发条件与监控机制", "偏离、现金比例、集中度、风险偏好和市场变化的复核条件。"),
    ("六、情景分析", "乐观、中性、压力三种情景及缓冲机制。"),
]

CUSTOMER_PROFILE_CHAPTERS = [
    ("一、客户摘要", "账户口径、KYC 完整度和画像置信度。"),
    ("二、KYC 与适当性画像", "年龄、就业、资产、目标、经验、产品熟悉度、风险和期限等字段。"),
    ("三、真实持仓反推画像", "Top5 权重、资产/货币/主题分布和 revealed risk。"),
    ("四、交易行为画像", "成交摘要、交易频率和风格；缺失时明确不判断。"),
    ("五、画像冲突与适配度", "匹配、偏激进、偏保守或数据不足。"),
    ("六、建议关注与画像缺口", "后续补充字段和监控建议。"),
]


def stream_agent_workflow(run_id: str) -> Iterable[str]:
    with SessionLocal() as db:
        run = db.get(AIWorkflowRun, run_id)
        if not run:
            yield _sse("run_failed", {"run_id": run_id, "error": "Workflow run not found"})
            return
        if run.status == "completed":
            yield _sse("run_started", workflow_run_to_dict(run))
            for step in run.steps or []:
                yield _sse("tool_completed", step)
            for artifact in run.artifacts or []:
                yield _sse("artifact_created", artifact)
            markdown = str((run.output or {}).get("markdown") or "")
            if markdown:
                yield _sse("content_delta", {"run_id": run_id, "delta": markdown})
            yield _sse("run_completed", workflow_run_to_dict(run))
            return
        if run.status == "failed":
            yield _sse("run_started", workflow_run_to_dict(run))
            for step in run.steps or []:
                yield _sse("tool_completed", step)
            for artifact in run.artifacts or []:
                yield _sse("artifact_created", artifact)
            yield _sse("run_failed", {"run_id": run_id, "error": run.error_message or "Workflow run failed"})
            return
        if run.status == "cancelled":
            yield _sse("run_started", workflow_run_to_dict(run))
            for step in run.steps or []:
                yield _sse("tool_completed", step)
            for artifact in run.artifacts or []:
                yield _sse("artifact_created", artifact)
            markdown = str((run.output or {}).get("markdown") or (run.output or {}).get("partial_markdown") or "")
            if markdown:
                yield _sse("content_delta", {"run_id": run_id, "delta": markdown})
            yield _sse("run_failed", {"run_id": run_id, "error": run.error_message or "用户已终止生成"})
            return

        registry = default_tool_registry()
        settings = get_settings()
        runtime = active_ai_runtime(db)
        use_deepseek = run.provider != "local" and runtime_can_call_external(runtime)
        existing_output = run.output or {}
        state: dict[str, Any] = {
            "workflow_type": run.workflow_type,
            "question": run.question,
            "tool_trace": existing_output.get("tool_trace") if isinstance(existing_output.get("tool_trace"), list) else [],
            "artifacts": run.artifacts or [],
            "use_deepseek": use_deepseek,
            "skill_doc": existing_output.get("skill_doc", ""),
            "calculation_audit_pack": existing_output.get("calculation_audit_pack"),
            "calculation_audit_result": existing_output.get("calculation_audit_result"),
            "warnings": existing_output.get("warnings") if isinstance(existing_output.get("warnings"), list) else [],
            "ai_runtime": runtime,
        }

        try:
            resuming = run.status == "running"
            run.status = "running"
            if not resuming:
                run.steps = []
                state["tool_trace"] = []
                state["artifacts"] = []
            run.output = {**(run.output or {}), "agent_mode": "tool_loop", "tool_trace": state["tool_trace"], "cancel_requested": False}
            run.updated_at = datetime.now(timezone.utc)
            _save(db, run)
            yield _sse("run_started", workflow_run_to_dict(run))

            if not use_deepseek:
                error = "未配置可用外部大模型或本次未授权外部模型，已停止生成；没有大模型参与时不生成投顾报告。"
                _fail_run(db, run, state, error)
                yield _sse("agent_warning", {"run_id": run.run_id, "message": error})
                yield _sse("run_failed", {"run_id": run.run_id, "error": error})
                return

            if any(item.get("tool_name") == "finalize_report" for item in state.get("tool_trace", [])):
                state["ready_to_report"] = True

            next_turn = max([int(item.get("turn") or 0) for item in state.get("tool_trace", [])] + [0]) + 1
            if not state.get("ready_to_report"):
                for turn in range(next_turn, MAX_AGENT_TURNS + 1):
                    if _cancel_requested(db, run.run_id):
                        yield _sse("run_failed", {"run_id": run.run_id, "error": "用户已终止生成"})
                        return
                    try:
                        action = _next_action(settings, run, registry, state, use_deepseek, turn)
                    except Exception as exc:
                        error = f"外部大模型思考超时或不可用，已停止生成；没有大模型参与时不生成投顾报告：{str(exc)[:160]}"
                        _fail_run(db, run, state, error)
                        yield _sse("agent_warning", {"run_id": run.run_id, "message": error})
                        yield _sse("run_failed", {"run_id": run.run_id, "error": error})
                        return
                    thought = {
                        "run_id": run.run_id,
                        "turn": turn,
                        "thought_summary": action.get("thought_summary", ""),
                        "why": action.get("why", ""),
                        "expected_observation": action.get("expected_observation", ""),
                    }
                    yield _sse("agent_thought", thought)

                    tool_name = str(action.get("tool_name") or "")
                    tool_args = action.get("tool_args") if isinstance(action.get("tool_args"), dict) else {}
                    step = _tool_step(turn, tool_name, tool_args, action, "running")
                    _append_or_replace_step(run, step)
                    _save(db, run)
                    yield _sse("tool_started", step)
                    yield _sse("step_started", step)

                    observation = registry.run(db, run.account_id, tool_name, tool_args, state)
                    trace_item = {
                        "turn": turn,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "observation": _compact_observation(observation),
                        "at": now_iso(),
                    }
                    state["tool_trace"].append(trace_item)
                    completed = {**step, "status": "completed", "observation": trace_item["observation"]}
                    _append_or_replace_step(run, completed)
                    run.output = {**(run.output or {}), "tool_trace": state["tool_trace"], "skill_doc": state.get("skill_doc", "")}
                    _save(db, run)
                    yield _sse("tool_completed", completed)
                    yield _sse("step_completed", completed)

                    artifacts = observation.get("artifacts") if isinstance(observation, dict) else None
                    if isinstance(artifacts, list):
                        state["artifacts"] = artifacts
                        run.artifacts = artifacts
                        _save(db, run)
                        for artifact in artifacts:
                            yield _sse("artifact_created", artifact)

                    if tool_name == "finalize_report" or state.get("ready_to_report"):
                        break
                else:
                    error = "云端 Agent 达到最大工具调用轮数但未进入报告阶段，已停止生成；不使用本地模板兜底。"
                    _fail_run(db, run, state, error)
                    yield _sse("agent_warning", {"run_id": run.run_id, "message": error})
                    yield _sse("run_failed", {"run_id": run.run_id, "error": error})
                    return

            context = state.get("context") or build_workflow_context(db, run.account_id)
            artifacts = state.get("artifacts") or build_artifacts(run.workflow_type, context)
            run.artifacts = artifacts
            yield from _ensure_calculation_pipeline(db, run, registry, state)
            context = state.get("context") or context
            artifacts = state.get("artifacts") or artifacts
            run.artifacts = artifacts
            for artifact in artifacts:
                yield _sse("artifact_created", artifact)
            markdown = ""
            try:
                for event in _stream_chaptered_deepseek_report(settings, run, state, context, artifacts):
                    if _cancel_requested(db, run.run_id):
                        yield _sse("run_failed", {"run_id": run.run_id, "error": "用户已终止生成"})
                        return
                    if event["event"] == "content_delta":
                        markdown += str(event["payload"].get("delta") or "")
                        run.output = {**(run.output or {}), "partial_markdown": markdown}
                        run.updated_at = datetime.now(timezone.utc)
                        _save(db, run)
                    elif event["event"] == "agent_warning":
                        state.setdefault("warnings", []).append(str(event["payload"].get("message") or "章节生成降级"))
                    yield _sse(event["event"], event["payload"])
            except Exception as exc:
                error = f"外部大模型生成报告超时或不可用，已停止生成；不使用本地模板兜底：{str(exc)[:160]}"
                _fail_run(db, run, state, error, partial_markdown=markdown)
                yield _sse("agent_warning", {"run_id": run.run_id, "message": error})
                yield _sse("run_failed", {"run_id": run.run_id, "error": error})
                return
            if not markdown:
                error = "外部大模型未返回报告正文，已停止生成；不使用本地模板兜底。"
                _fail_run(db, run, state, error)
                yield _sse("agent_warning", {"run_id": run.run_id, "message": error})
                yield _sse("run_failed", {"run_id": run.run_id, "error": error})
                return

            markdown = annotate_model_derived_percentages(markdown, {**state, "context": context, "artifacts": artifacts, "markdown": markdown})
            validation = validate_report(markdown, {**state, "context": context, "artifacts": artifacts, "markdown": markdown})
            if validation["status"] != "ok" and use_deepseek:
                yield _sse("agent_warning", {"run_id": run.run_id, "message": "报告校验发现质量问题，正在请求 Agent 自我修正。", "issues": validation["issues"]})
                fixed = _fix_report(settings, run, state, context, artifacts, markdown, validation)
                if fixed:
                    markdown = annotate_model_derived_percentages(fixed, {**state, "context": context, "artifacts": artifacts, "markdown": fixed})
                    validation = validate_report(markdown, {**state, "context": context, "artifacts": artifacts, "markdown": markdown})
                    yield _sse("content_delta", {"run_id": run.run_id, "delta": "\n\n---\n\n" + markdown})

            quality_result = _quality_result(validation)
            if quality_result["status"] != "ok":
                yield _sse("report_quality_issues", {"run_id": run.run_id, **quality_result})
            home_summary_cards = state.get("home_summary_cards")
            if not isinstance(home_summary_cards, list) or len(home_summary_cards) != 2:
                home_summary_cards = build_home_summary_cards(run.workflow_type, context, artifacts)
            run.status = "completed"
            run.error_message = ""
            run.artifacts = artifacts
            run.input_context = _input_context(context)
            run.output = {
                **(run.output or {}),
                "agent_mode": "tool_loop",
                "title": f"{WORKFLOW_LABELS.get(run.workflow_type, run.workflow_type)}报告",
                "markdown": markdown,
                "summary": _summary(run.workflow_type, context),
                "home_summary_cards": home_summary_cards,
                "tool_trace": state["tool_trace"],
                "planning_model": state.get("planning_model"),
                "calculation_audit_pack": state.get("calculation_audit_pack"),
                "calculation_audit_result": state.get("calculation_audit_result"),
                "chapter_statuses": state.get("chapter_statuses", []),
                "validation_result": validation,
                "quality_status": quality_result["status"],
                "quality_issues": quality_result["issues"],
                "skill_doc": state.get("skill_doc", ""),
                "warnings": state.get("warnings", []),
            }
            run.data_version = context.get("data_version", "")
            run.updated_at = datetime.now(timezone.utc)
            _save(db, run)
            yield _sse("run_completed", workflow_run_to_dict(run))
        except Exception as exc:  # pragma: no cover - stream boundary
            db.rollback()
            failed = db.get(AIWorkflowRun, run_id)
            if failed:
                failed.status = "failed"
                failed.error_message = str(exc)[:1000]
                failed.updated_at = datetime.now(timezone.utc)
                _save(db, failed)
            yield _sse("run_failed", {"run_id": run_id, "error": str(exc)[:1000]})


def _next_action(settings, run: AIWorkflowRun, registry, state: dict[str, Any], use_deepseek: bool, turn: int) -> dict[str, Any]:
    if run.workflow_type in {"asset_allocation", "portfolio_diagnosis", "customer_profile"}:
        return _planned_action(turn, run.workflow_type, state)
    if not use_deepseek:
        raise RuntimeError("External LLM is required for report generation")
    planning_model = _planning_model(settings, run)
    state["planning_model"] = planning_model
    payload = {
        "model": planning_model,
        "messages": [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "workflow_type": run.workflow_type,
                        "question": run.question,
                        "available_tools": registry.list_for_prompt(),
                        "tool_trace": state.get("tool_trace", [])[-8:],
                        "known_context_summary": _known_context_summary(state),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    runtime = state.get("ai_runtime") or {}
    output = call_llm_payload(payload, str(runtime.get("api_key") or ""), str(runtime.get("base_url") or ""), timeout=30)
    action = {
        "thought_summary": output.get("thought_summary") or output.get("conclusion") or "Agent 正在决定下一步。",
        "tool_name": output.get("tool_name"),
        "tool_args": output.get("tool_args") if isinstance(output.get("tool_args"), dict) else {},
        "why": output.get("why") or "",
        "expected_observation": output.get("expected_observation") or "",
    }
    if not action["tool_name"]:
        action["tool_name"] = "finalize_report"
    if action["tool_name"] not in registry.names():
        action["tool_name"] = "finalize_report"
        action["why"] = "模型请求了未注册工具，改为进入报告生成。"
    return action


def _planning_model(settings, run: AIWorkflowRun) -> str:
    selected = str((run.output or {}).get("planning_model") or run.model or settings.deepseek_model or "").strip()
    return selected or "deepseek-v4-flash"


def _chapters_for_workflow(workflow_type: str) -> list[tuple[str, str]]:
    if workflow_type == "asset_allocation":
        return ASSET_ALLOCATION_CHAPTERS
    if workflow_type == "customer_profile":
        return CUSTOMER_PROFILE_CHAPTERS
    return CHAPTERS


def _cancel_requested(db: Session, run_id: str) -> bool:
    current = db.get(AIWorkflowRun, run_id)
    if not current:
        return True
    output = current.output or {}
    return current.status == "cancelled" or output.get("cancel_requested") is True


def _planned_action(turn: int, workflow_type: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state or {}
    if workflow_type == "asset_allocation":
        sequence = [
            ("read_skill_doc", {"workflow_type": workflow_type}, "读取资产配置技能文档。"),
            ("get_investor_preferences", {}, "读取风险承受能力、投资期限、流动性和目标收益。"),
            ("get_portfolio_context", {}, "读取本地快照，建立组合事实基础。"),
            ("get_position_exposures", {"limit": 15}, "读取跨账户合并持仓暴露。"),
            ("calculate_allocation_distribution", {}, "计算当前资产、货币和主题分布。"),
            ("calculate_audit_pack", {}, "整理可审计计算包，作为报告唯一数字来源。"),
            ("audit_calculation_pack", {}, "审计排序、合计和收益贡献公式。"),
            ("create_chart_artifact", {"workflow_type": workflow_type}, "生成资产配置图表。"),
            ("finalize_report", {}, "数据与图表已准备，进入资产配置报告生成。"),
        ]
    elif workflow_type == "customer_profile":
        planned_context = state.get("context")
        if not isinstance(planned_context, dict) or not planned_context:
            planned_context = {}
        planned_artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), list) else []
        sequence = [
            ("read_skill_doc", {"workflow_type": workflow_type}, "读取客户画像技能文档，确认画像边界。"),
            ("get_portfolio_context", {}, "读取账户、持仓、成交和偏好概览。"),
            ("get_investor_preferences", {}, "读取 KYC 与投资偏好，建立 stated risk 基础。"),
            ("get_position_exposures", {"limit": 15}, "读取跨账户合并持仓暴露，反推 revealed risk。"),
            ("calculate_allocation_distribution", {}, "计算资产、货币、主题分布和收益贡献。"),
            ("get_deals_summary", {}, "读取成交摘要，用于判断交易行为画像。"),
            ("calculate_audit_pack", {}, "整理可审计计算包，作为报告唯一数字来源。"),
            ("audit_calculation_pack", {}, "审计排序、合计和收益贡献公式。"),
            ("create_chart_artifact", {"workflow_type": workflow_type}, "生成客户画像图表 artifact。"),
            ("finalize_report", {"home_summary_cards": build_home_summary_cards(workflow_type, planned_context, planned_artifacts)}, "数据与审计已准备，进入客户画像报告生成。"),
        ]
    else:
        planned_context = state.get("context")
        if not isinstance(planned_context, dict) or not planned_context:
            planned_context = {}
        planned_artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), list) else []
        sequence = [
            ("read_skill_doc", {"workflow_type": workflow_type}, "先读取技能文档，确认分析框架。"),
            ("get_portfolio_context", {}, "读取本地快照，建立组合事实基础。"),
            ("calculate_portfolio_metrics", {}, "计算最大持仓、现金比例和权重口径。"),
            ("calculate_allocation_distribution", {}, "计算资产、货币、主题和收益贡献。"),
            ("get_kline_summary", {}, "尝试补查核心持仓 K 线；失败时写入缺失。"),
            ("calculate_audit_pack", {}, "整理可审计计算包，作为报告唯一数字来源。"),
            ("audit_calculation_pack", {}, "审计排序、合计和收益贡献公式。"),
            ("create_chart_artifact", {"workflow_type": workflow_type}, "生成前端图表 artifact。"),
            ("finalize_report", {"home_summary_cards": build_home_summary_cards(workflow_type, planned_context, planned_artifacts)}, "数据与图表已准备，进入报告生成。"),
        ]
    tool_name, args, why = sequence[min(turn - 1, len(sequence) - 1)]
    return {
        "thought_summary": f"Agent 选择调用 {tool_name}。",
        "tool_name": tool_name,
        "tool_args": args,
        "why": why,
        "expected_observation": "返回结构化 observation，用于下一步分析。",
    }


def _stream_chaptered_deepseek_report(settings, run: AIWorkflowRun, state: dict[str, Any], context: dict[str, Any], artifacts: list[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    chapter_statuses = []
    for index, (title, brief) in enumerate(_chapters_for_workflow(run.workflow_type), start=1):
        started = _tool_step(100 + index, f"generate_chapter_{index}", {"chapter": title}, {"why": f"生成第 {index} 章：{title}"}, "running")
        yield {"event": "tool_started", "payload": started}
        try:
            text = ""
            for part in _stream_deepseek_chapter(settings, run, state, context, artifacts, index, title, brief):
                text += part
            text = _normalize_chapter_markdown(text, title)
            yield {"event": "content_delta", "payload": {"run_id": run.run_id, "delta": text}}
            chapter_statuses.append({"chapter": title, "status": "completed", "source": run.provider or "external_llm"})
            yield {"event": "tool_completed", "payload": {**started, "status": "completed", "observation": {"status": "ok", "chapter": title}}}
        except Exception as exc:
            chapter_statuses.append({"chapter": title, "status": "failed", "source": run.provider or "external_llm", "error": str(exc)[:160]})
            state["chapter_statuses"] = chapter_statuses
            yield {
                "event": "tool_completed",
                "payload": {**started, "status": "failed", "observation": {"status": "failed", "chapter": title, "error": str(exc)[:160]}},
            }
            raise RuntimeError(f"第 {index} 章「{title}」云端生成超时或失败：{str(exc)[:160]}") from exc
        state["chapter_statuses"] = chapter_statuses


def _stream_deepseek_chapter(settings, run: AIWorkflowRun, state: dict[str, Any], context: dict[str, Any], artifacts: list[dict[str, Any]], index: int, title: str, brief: str) -> Iterable[str]:
    runtime = state.get("ai_runtime") or {}
    endpoint = str(runtime.get("base_url") or settings.deepseek_base_url).rstrip("/") + "/chat/completions"
    audit_pack = state.get("calculation_audit_pack") or build_calculation_audit_pack(context, artifacts)
    payload = {
        "model": run.model or runtime.get("model") or settings.deepseek_model,
        "messages": [
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "workflow_type": run.workflow_type,
                        "question": run.question,
                        "chapter": {"index": index, "title": title, "brief": brief},
                        "chapter_instruction": (
                            f"只输出本章 Markdown，标题必须且只能使用 ## {title}。"
                            "必须逐条覆盖 skill_section_template 中该章的字段、表格和缺失数据写法。"
                            "章内小节使用 ### 事实数据、### Agent 判断、### 建议关注；更细分内容使用 ####。"
                            "不要使用加粗文本充当小标题。章节末尾输出 --- 分隔线。"
                            "不要改名、不要合并章节、不要新增未要求的大章节。"
                            f"{_workflow_report_contract(run.workflow_type)}"
                        ),
                        "skill_section_template": _skill_template_summary(state.get("skill_doc", ""), title),
                        "calculation_audit_pack": _audit_pack_for_chapter(audit_pack, title),
                        "tool_trace": _compact_tool_trace(state.get("tool_trace", [])),
                        "context_summary": _input_context(context),
                        "artifacts": artifacts,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
        "temperature": 0.2,
        "stream": True,
    }
    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {runtime.get('api_key') or settings.deepseek_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=45) as resp:  # nosec - user configured endpoint
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                break
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = payload.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if delta:
                yield _sanitize_text(str(delta))


def _fix_report(settings, run: AIWorkflowRun, state: dict[str, Any], context: dict[str, Any], artifacts: list[dict[str, Any]], markdown: str, validation: dict[str, Any]) -> str:
    runtime = state.get("ai_runtime") or {}
    payload = {
        "model": run.model or runtime.get("model") or settings.deepseek_model,
        "messages": [
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "修正报告，使其通过 validation_result。只输出完整 Markdown。",
                        "validation_result": validation,
                        "markdown": markdown,
                        "context": _input_context(context),
                        "artifacts": artifacts,
                        "tool_trace": state.get("tool_trace", []),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
        "temperature": 0.1,
    }
    try:
        endpoint = str(runtime.get("base_url") or settings.deepseek_base_url).rstrip("/") + "/chat/completions"
        req = request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {runtime.get('api_key') or settings.deepseek_api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=40) as resp:  # nosec - user configured endpoint
            data = json.loads(resp.read().decode("utf-8"))
        return _sanitize_text(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
    except Exception:
        return ""


def _ensure_calculation_pipeline(db: Session, run: AIWorkflowRun, registry, state: dict[str, Any]) -> Iterable[str]:
    required = [
        ("get_latest_quotes", {}, "补充实时行情"),
        ("get_kline_summary", {}, "补充 K 线摘要"),
        ("calculate_audit_pack", {}, "整理计算包"),
        ("audit_calculation_pack", {}, "AI 审计中"),
        ("create_chart_artifact", {"workflow_type": run.workflow_type}, "生成图表"),
    ]
    seen = {item.get("tool_name") for item in state.get("tool_trace", [])}
    next_step = max([int(item.get("step_no") or 0) for item in run.steps or []] + [0]) + 1
    for tool_name, tool_args, label in required:
        if tool_name in seen and (tool_name != "create_chart_artifact" or state.get("artifacts")):
            continue
        action = {
            "thought_summary": label,
            "why": label,
            "expected_observation": "返回报告写作所需的结构化事实。",
        }
        step = _tool_step(next_step, tool_name, tool_args, action, "running")
        next_step += 1
        _append_or_replace_step(run, step)
        _save(db, run)
        yield _sse("tool_started", step)
        yield _sse("step_started", step)
        observation = registry.run(db, run.account_id, tool_name, tool_args, state)
        trace_item = {
            "turn": step["step_no"],
            "tool_name": tool_name,
            "tool_args": tool_args,
            "observation": _compact_observation(observation),
            "at": now_iso(),
        }
        state["tool_trace"].append(trace_item)
        completed = {**step, "status": "completed", "observation": trace_item["observation"]}
        _append_or_replace_step(run, completed)
        run.output = {
            **(run.output or {}),
            "tool_trace": state["tool_trace"],
            "calculation_audit_pack": state.get("calculation_audit_pack"),
            "calculation_audit_result": state.get("calculation_audit_result"),
        }
        if state.get("artifacts"):
            run.artifacts = state["artifacts"]
        _save(db, run)
        yield _sse("tool_completed", completed)
        yield _sse("step_completed", completed)
        if tool_name == "audit_calculation_pack":
            audit = state.get("calculation_audit_result") or {}
            if audit.get("status") not in ("ok", None):
                yield _sse("agent_warning", {"run_id": run.run_id, "message": "AI 审计未完全通过或未完成，报告会标注审计状态。", "audit_result": audit})


def _tool_step(turn: int, tool_name: str, tool_args: dict[str, Any], action: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "step_no": turn,
        "title": f"调用工具：{tool_name}",
        "detail": str(action.get("why") or action.get("thought_summary") or ""),
        "action_type": "tool",
        "action_label": tool_name,
        "status": status,
        "artifact_ids": [],
        "tool_name": tool_name,
        "tool_args": tool_args,
        "agent_note": str(action.get("thought_summary") or ""),
        "expected_observation": str(action.get("expected_observation") or ""),
    }


def _append_or_replace_step(run: AIWorkflowRun, step: dict[str, Any]) -> None:
    steps = [item for item in (run.steps or []) if item.get("step_no") != step.get("step_no")]
    steps.append(step)
    run.steps = sorted(steps, key=lambda item: int(item.get("step_no") or 0))
    run.updated_at = datetime.now(timezone.utc)


def _compact_observation(observation: Any) -> Any:
    if isinstance(observation, dict):
        result = {}
        for key, value in observation.items():
            if key == "content" and isinstance(value, str):
                result[key] = value[:2000]
            elif key == "items" and isinstance(value, list):
                result[key] = value[:12]
                result["item_count"] = len(value)
            elif key == "artifacts" and isinstance(value, list):
                result[key] = value
            else:
                result[key] = _compact_observation(value)
        return result
    if isinstance(observation, list):
        return [_compact_observation(item) for item in observation[:12]]
    return observation


def _known_context_summary(state: dict[str, Any]) -> dict[str, Any]:
    context = state.get("context") or {}
    return {
        "has_skill_doc": bool(state.get("skill_doc")),
        "portfolio": context.get("portfolio"),
        "top_exposures": (context.get("position_exposures") or [])[:5],
        "artifact_count": len(state.get("artifacts") or []),
        "ready_to_report": bool(state.get("ready_to_report")),
    }


def _input_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "data_version": context.get("data_version"),
        "portfolio": context.get("portfolio"),
        "preference": context.get("preference"),
        "profile": context.get("profile"),
        "position_exposures": (context.get("position_exposures") or [])[:30],
        "positions": (context.get("positions") or [])[:30],
        "deal_count": len(context.get("deals") or []),
        "watchlist_count": len(context.get("watchlist") or []),
        "news_count": len(context.get("news") or []),
    }


def _compact_tool_trace(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for item in trace[-12:]:
        observation = item.get("observation")
        summary = observation
        if isinstance(observation, dict):
            summary = {
                key: value
                for key, value in observation.items()
                if key in {"status", "summary", "message", "missing_codes", "item_count", "error"}
            }
            if not summary:
                summary = {"status": observation.get("status", "ok"), "keys": list(observation.keys())[:8]}
        compact.append(
            {
                "tool_name": item.get("tool_name"),
                "status": summary.get("status") if isinstance(summary, dict) else "ok",
                "summary": summary,
                "at": item.get("at"),
            }
        )
    return compact


def _audit_pack_for_chapter(pack: dict[str, Any], title: str) -> dict[str, Any]:
    base = {
        "data_version": pack.get("data_version"),
        "portfolio": pack.get("portfolio"),
        "formulas": pack.get("formulas"),
        "largest_exposure": pack.get("largest_exposure"),
        "top5_weights": pack.get("top5_weights"),
        "top5_weight_total": pack.get("top5_weight_total"),
        "data_quality": pack.get("data_quality"),
    }
    if title in {
        "二、持仓明细表",
        "四、收益贡献归因",
        "七、风险雷达",
        "八、可执行关注清单",
        "二、当前组合偏离诊断",
        "三、建议目标配置",
        "四、再平衡路径",
    }:
        base["merged_exposures_top15"] = (pack.get("merged_exposures") or [])[:15]
    if title in {
        "三、集中度与重叠风险",
        "一、组合总览",
        "七、风险雷达",
        "二、当前组合偏离诊断",
        "三、建议目标配置",
        "六、情景分析",
    }:
        base["distribution_checks"] = pack.get("distribution_checks")
        base["artifacts"] = pack.get("artifacts")
    if title == "四、收益贡献归因":
        base["return_contribution_rank"] = pack.get("return_contribution_rank")
    if title == "二、持仓明细表":
        base["account_sources_by_code"] = {
            code: sources
            for code, sources in (pack.get("account_sources_by_code") or {}).items()
            if code in {item.get("code") for item in (pack.get("merged_exposures") or [])[:15]}
        }
    if title == "五、行情与 K线诊断":
        base["latest_quotes"] = pack.get("latest_quotes")
        base["kline_summary"] = pack.get("kline_summary")
    return base


def _workflow_report_contract(workflow_type: str) -> str:
    if workflow_type == "asset_allocation":
        return (
            "本报告是资产配置建议，不是持仓诊断。必须围绕 IPS 约束、当前比例、目标比例、偏离、估算金额、再平衡路径和触发条件展开；"
            "不要输出持仓明细 Top 表，不要重复收益归因榜。建议比例和金额只能引用 artifacts.target_allocation 与 portfolio.total_assets，可写为估算。"
        )
    if workflow_type == "portfolio_diagnosis":
        return (
            "本报告是持仓体检，不是资产配置方案。必须围绕集中度、合并持仓、收益贡献、行情/K线、风险雷达展开；"
            "不要输出目标配置比例、再平衡金额或参考标的清单。"
        )
    return "本报告是客户画像，不要写成持仓诊断或资产配置方案。"


def _skill_template_summary(skill_doc: str, title: str) -> str:
    if not skill_doc:
        return ""
    section = _extract_skill_section(skill_doc, title)
    if section:
        return section[:5000]
    lines = [line.strip() for line in skill_doc.splitlines() if line.strip()]
    keywords = [title, "事实", "Agent 判断", "建议关注", "禁止", "缺失", "权重", "收益贡献"]
    selected = [line for line in lines if any(keyword in line for keyword in keywords)]
    return "\n".join(selected[:40])[:5000]


def _extract_skill_section(skill_doc: str, title: str) -> str:
    wanted = f"### {title}"
    lines = skill_doc.splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.strip() == wanted), -1)
    if start < 0:
        return ""
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx].strip()
        if line.startswith("### ") or line.startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def _normalize_chapter_markdown(markdown: str, title: str) -> str:
    text = _sanitize_text(markdown).strip()
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].lstrip().startswith("#"):
        lines[0] = f"## {title}"
    else:
        lines.insert(0, f"## {title}")
    normalized = "\n".join(lines).strip()
    if not normalized.endswith("---"):
        normalized = normalized.rstrip() + "\n\n---"
    return "\n\n" + normalized + "\n\n"


def _summary(workflow_type: str, context: dict[str, Any]) -> str:
    portfolio = context.get("portfolio") or {}
    if workflow_type == "asset_allocation":
        return f"Agent 已基于 {portfolio.get('base_currency', '')} 总资产口径生成配置建议。"
    if workflow_type == "portfolio_diagnosis":
        return f"Agent 已执行工具循环，最大单一标的约 {float(portfolio.get('max_position_weight') or 0):.1%}。"
    return f"Agent 已基于 {portfolio.get('position_count', 0)} 条持仓记录生成客户画像。"


def _sanitize_text(text: str) -> str:
    for phrase in ("立即买入", "立即卖出", "必涨", "必跌", "稳赚", "满仓"):
        text = text.replace(phrase, "关注")
    return text


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _save(db: Session, run: AIWorkflowRun) -> None:
    run.steps = _json_safe(run.steps or [])
    run.input_context = _json_safe(run.input_context or {})
    run.output = _json_safe(run.output or {})
    run.artifacts = _json_safe(run.artifacts or [])
    db.add(run)
    db.commit()


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _quality_result(validation: dict[str, Any]) -> dict[str, Any]:
    issues = validation.get("issues") if isinstance(validation.get("issues"), list) else []
    clean_issues = [str(issue) for issue in issues if str(issue).strip()]
    return {
        "status": "ok" if not clean_issues else "needs_review",
        "issues": clean_issues,
    }


def _fail_run(db: Session, run: AIWorkflowRun, state: dict[str, Any], error: str, partial_markdown: str = "") -> None:
    state.setdefault("warnings", []).append(error)
    run.status = "failed"
    run.error_message = error[:1000]
    output = {
        **(run.output or {}),
        "agent_mode": "tool_loop",
        "tool_trace": state.get("tool_trace", []),
        "skill_doc": state.get("skill_doc", ""),
        "warnings": state.get("warnings", []),
        "chapter_statuses": state.get("chapter_statuses", []),
    }
    if partial_markdown:
        output["partial_markdown"] = partial_markdown
    run.output = output
    run.updated_at = datetime.now(timezone.utc)
    _save(db, run)
    db.refresh(run)


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
