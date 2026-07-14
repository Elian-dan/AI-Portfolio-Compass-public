import { useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, ReactNode, ThHTMLAttributes } from "react";
import { Alert, Button, Checkbox, Descriptions, Drawer, Dropdown, Empty as ArcoEmpty, Form, Input, Menu, Modal, Select, Spin, Table, Tabs, Tag, Upload } from "@arco-design/web-react";
import { api, AccountDataOverview, AccountDeal, AccountSummary, AIAnalysis, AIConfigResponse, AIRuntimeConfig, AIWorkflowRun, Dashboard, DealPayload, DecisionCard, HealthStatus, ImportPreview, InvestorPreference, KLineItem, KLineResponse, NewsItem, Position, PositionSnapshotPayload, Profile, ProviderState, Review, TradeIntentPlan, TradeIntentTags, TradeReview, TradeReviewList, WorkflowArtifact, WorkflowStep } from "../api";

const layers = ["全部", "核心长期仓", "中期配置仓", "短期交易仓", "期权仓", "遗留观察仓"];
const intentTagGroups: Array<{ key: keyof TradeIntentTags; title: string; items: string[] }> = [
  { key: "trend", title: "趋势标签", items: ["突破", "趋势跟随", "回踩", "反弹", "低吸", "止损离场", "止盈兑现", "减仓"] },
  { key: "market", title: "行情标签", items: ["市场偏强", "市场中性", "市场偏弱", "行业偏热", "行业中性", "行业偏冷", "轮动交易"] },
  { key: "fundamental", title: "基本面标签", items: ["龙头", "跟风", "高质量公司", "事件驱动", "情绪驱动", "周期属性"] },
  { key: "emotion", title: "情绪标签", items: ["执行纪律好", "情绪稳定", "执行犹豫", "FOMO", "怕回撤", "报复交易", "追高", "过早兑现"] },
];
const emptyIntentTags: TradeIntentTags = { trend: [], market: [], fundamental: [], emotion: [] };
const emptyIntentPlan: TradeIntentPlan = { holding_period: "", stop_loss_type: "", take_profit_type: "", stop_loss_price: "", take_profit_price: "" };
let assetMaskEnabled = false;

export function SpaceBetweenTags({ children }: { children: ReactNode }) {
  return <span className="space-between-tags">{children}</span>;
}

export function setAssetMaskEnabled(enabled: boolean) {
  assetMaskEnabled = enabled;
}

const workflowLabels: Record<AIWorkflowRun["workflow_type"], string> = {
  customer_profile: "客户画像分析",
  portfolio_diagnosis: "持仓诊断分析",
  asset_allocation: "资产配置建议",
};
const workflowCards: Array<{ type: AIWorkflowRun["workflow_type"]; title: string; subtitle: string }> = [
  { type: "customer_profile", title: "客户画像分析", subtitle: "结合 KYC、风险偏好、资金流和交易行为生成投资者画像" },
  { type: "portfolio_diagnosis", title: "持仓诊断分析", subtitle: "组合集中度、盈亏、主题暴露、风险和实时关注点" },
  { type: "asset_allocation", title: "资产配置建议", subtitle: "给出目标比例、参考标的、金额口径和调仓方向" },
];
const marketDataProviderOptions = [
  { value: "", label: "系统推荐" },
  { value: "futu", label: "Futu / moomoo OpenD" },
  { value: "tushare", label: "Tushare Pro" },
  { value: "alpaca", label: "Alpaca Market Data" },
  { value: "polygon", label: "Polygon / Massive" },
  { value: "fmp", label: "Financial Modeling Prep" },
  { value: "alpha_vantage", label: "Alpha Vantage" },
  { value: "akshare", label: "AKShare" },
];
const newsDataProviderOptions = [
  { value: "", label: "系统推荐" },
  { value: "futu", label: "Futu / moomoo OpenD" },
  { value: "marketaux", label: "Marketaux" },
  { value: "fmp", label: "Financial Modeling Prep" },
  { value: "alpha_vantage", label: "Alpha Vantage" },
];
const positionMarketOptions = [
  { value: "US", label: "美股" },
  { value: "HK", label: "港股" },
  { value: "CN", label: "A股" },
];
type ResizableHeaderCellProps = ThHTMLAttributes<HTMLTableCellElement> & {
  onResizeStart?: (event: ReactMouseEvent<HTMLSpanElement>) => void;
  onResizeReset?: (event: ReactMouseEvent<HTMLSpanElement>) => void;
};
const minColumnWidth = 96;
const ResizableHeaderCell = ({ children, className, onResizeStart, onResizeReset, ...rest }: ResizableHeaderCellProps) => (
  <th {...rest} className={`${className || ""} resizable-table-th`}>
    {children}
    {onResizeStart && (
      <span
        aria-hidden="true"
        className="column-resize-handle"
        onMouseDown={onResizeStart}
        onDoubleClick={onResizeReset}
      />
    )}
  </th>
);
const resizableTableComponents = { header: { th: ResizableHeaderCell } };

function useResizableTableColumns(defaultWidths: Record<string, number>) {
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultWidths);
  const totalTableWidth = Object.values(columnWidths).reduce((sum, width) => sum + width, 0);
  const resizableHeaderProps = (key: string) => ({
    onResizeStart: (event: ReactMouseEvent<HTMLSpanElement>) => {
      event.preventDefault();
      event.stopPropagation();
      const startX = event.clientX;
      const startWidth = columnWidths[key] ?? minColumnWidth;
      document.body.classList.add("column-resizing");

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const nextWidth = Math.max(minColumnWidth, startWidth + moveEvent.clientX - startX);
        setColumnWidths((current) => ({ ...current, [key]: nextWidth }));
      };
      const handleMouseUp = () => {
        document.body.classList.remove("column-resizing");
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    },
    onResizeReset: (event: ReactMouseEvent<HTMLSpanElement>) => {
      event.preventDefault();
      event.stopPropagation();
      setColumnWidths((current) => ({ ...current, [key]: defaultWidths[key] ?? minColumnWidth }));
    },
  });
  const columnProps = (key: string) => ({
    width: columnWidths[key],
    onHeaderCell: () => resizableHeaderProps(key),
  });
  const staticColumnProps = (key: string) => ({
    width: columnWidths[key] ?? defaultWidths[key] ?? minColumnWidth,
  });
  return { columnProps, staticColumnProps, components: resizableTableComponents, totalTableWidth };
}
const workflowSkeletonSections: Record<AIWorkflowRun["workflow_type"], string[]> = {
  portfolio_diagnosis: [
    "一、组合总览",
    "二、持仓明细表",
    "三、集中度与重叠风险",
    "四、收益贡献归因",
    "五、行情与 K线诊断",
    "六、事件与新闻风险",
    "七、风险雷达",
    "八、可执行关注清单",
  ],
  asset_allocation: [
    "一、配置目标确认",
    "二、当前组合偏离诊断",
    "三、建议目标配置",
    "四、再平衡路径",
    "五、触发条件与监控机制",
    "六、情景分析",
  ],
  customer_profile: [
    "一、客户摘要",
    "二、KYC 与适当性画像",
    "三、真实持仓反推画像",
    "四、交易行为画像",
    "五、画像冲突与适配度",
    "六、建议关注与画像缺口",
  ],
};
type ConfirmOptions = {
  title: string;
  body: string;
  confirmText?: string;
  cancelText?: string;
  tone?: "default" | "danger";
};
type ProfilePageIntent = { kind: "generate" | "open"; runId?: string; requestId: number } | null;

export function FutuConnectionCard({ health, onRefresh, onSync }: { health: HealthStatus | null; onRefresh: () => Promise<void>; onSync: () => Promise<void> }) {
  const [checking, setChecking] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const futu = health?.futu;
  const connected = Boolean(futu?.opend_connected || health?.opend === "connected");
  const accountAccess = Boolean(futu?.account_access);
  const accountCount = futu?.account_count ?? 0;
  const status = !connected ? "offline" : !accountAccess ? "auth" : accountCount ? "discovered" : "empty";
  const statusCopy = {
    offline: { title: "连接 Futu 账户", label: "OpenD 未连接", body: `请先启动并登录 Futu / moomoo OpenD。系统会连接 ${futu?.host || "127.0.0.1"}:${futu?.port || 11111}，不会在这里接收券商密码。`, color: "orange" },
    auth: { title: "OpenD 已连接，等待账户授权", label: "需要检查登录", body: futu?.message || "请确认 OpenD 已登录正确的账户，并已完成账户授权。", color: "orange" },
    discovered: { title: `已发现 ${accountCount} 个 Futu 账户`, label: "可以首次同步", body: "首次同步会读取账户资产、持仓和成交记录，账户会自动出现在账户列表中。", color: "blue" },
    empty: { title: "OpenD 已连接，但尚未发现账户", label: "等待账户", body: "请确认 OpenD 登录的是有交易账户的 Futu 账号，并检查账户授权和市场权限。", color: "orange" },
  }[status];

  async function refreshConnection() {
    setChecking(true);
    try { await onRefresh(); } finally { setChecking(false); }
  }

  async function syncFutu() {
    setSyncing(true);
    try { await onSync(); } finally { setSyncing(false); }
  }

  return (
    <section className="panel futu-connection-card">
      <div className="futu-connection-main">
        <div>
          <span className="section-kicker">首次接入</span>
          <h2>{statusCopy.title}</h2>
          <p>{statusCopy.body}</p>
        </div>
        <Tag color={statusCopy.color}>{statusCopy.label}</Tag>
      </div>
      <div className="futu-connection-actions">
        {status === "discovered" ? (
          <Button type="primary" loading={syncing} onClick={syncFutu}>首次同步</Button>
        ) : (
          <Button type="primary" loading={checking} onClick={refreshConnection}>{status === "offline" ? "启动 OpenD 后检查" : "检查登录和账户授权"}</Button>
        )}
        <Button onClick={refreshConnection} disabled={checking || syncing}>重新检查</Button>
        <Button onClick={() => setShowHelp((value) => !value)}>{showHelp ? "收起说明" : "查看说明"}</Button>
      </div>
      {showHelp ? (
        <div className="futu-connection-help">
          <strong>接入步骤</strong>
          <ol>
            <li>启动并登录 Futu / moomoo OpenD。</li>
            <li>确认 OpenD 监听地址为 {futu?.host || "127.0.0.1"}:{futu?.port || 11111}。</li>
            <li>回到这里点击检查，再点击首次同步。</li>
          </ol>
          <small>券商密码只在 OpenD 中使用；本系统只读取数据，不执行下单、撤单或改单。</small>
        </div>
      ) : null}
    </section>
  );
}

export function Home({
  dashboard,
  positions,
  tradeReviews,
  workflowRuns,
  accounts,
  selectedAccount,
  maskAssets,
  activeCurrency,
  displayRate,
  emptySystem,
  health,
  onFutuRefresh,
  onFutuSync,
  onGenerateDiagnosis,
  onOpenDiagnosisReport,
  onOpenCode,
}: {
  dashboard: Dashboard | null;
  positions: Position[];
  tradeReviews: TradeReviewList | null;
  workflowRuns: AIWorkflowRun[];
  accounts: AccountSummary[];
  selectedAccount: string;
  maskAssets: boolean;
  activeCurrency: string;
  displayRate: number;
  emptySystem: boolean;
  health: HealthStatus | null;
  onFutuRefresh: () => Promise<void>;
  onFutuSync: () => Promise<void>;
  onGenerateDiagnosis: () => void;
  onOpenDiagnosisReport: (runId: string) => void;
  onOpenCode: (code: string) => void;
}) {
  setAssetMaskEnabled(maskAssets);
  const baseCurrency = dashboard?.portfolio.base_currency ?? "";
  const displayRateMeta = dashboard?.portfolio.display_rate_meta?.[activeCurrency];
  const pieCurrency = activeCurrency || "CNY";
  const latestDiagnosis = latestPortfolioDiagnosisRun(workflowRuns);
  const snapshotTime = latestSnapshotTime(dashboard, positions);
  const sourceNames = dataSourceNames(dashboard?.portfolio.accounts ?? accounts);
  const dataQuality = dataQualitySummary(dashboard, positions, latestDiagnosis, snapshotTime);
  const themeGroups = themeExposure(latestDiagnosis, positions, dashboard);
  const layerGroups = layerOverview(positions, dashboard);
  const accountGroups = accountExposure(dashboard?.portfolio.accounts ?? []);
  const marketGroups = marketExposure(positions, dashboard);
  const profitGroups = profitLossDistribution(positions, dashboard);
  const focusPositions = buildFocusPositions(positions, dashboard?.action_cards ?? [], dashboard).slice(0, 12);
  const aiPoints = aiConclusionPoints(latestDiagnosis, dashboard, positions, themeGroups);
  const accountPieData = accountGroups.map((item) => ({
    id: item.account_id,
    label: item.label,
    value: item.value,
    displayValue: formatMoney(convertCurrency(item.value, displayRate), pieCurrency),
    meta: sourceLabel(item.source_name),
  }));
  const marketPieData = marketGroups.map((item) => ({
    id: item.market,
    label: marketName(item.market),
    value: item.value,
    displayValue: formatMoney(convertCurrency(item.value, displayRate), pieCurrency),
    meta: `${formatCount(item.count)} 个持仓`,
  }));
  const layerPieData = layerGroups.map((item) => ({
    id: item.layer,
    label: item.layer,
    value: item.value,
    displayValue: formatMoney(convertCurrency(item.value, displayRate), pieCurrency),
    meta: `${formatCount(item.count)} 只`,
    hoverItems: item.names.slice(0, 3),
  }));
  const profitPieData = profitGroups.map((item) => ({
    id: item.label,
    label: item.label,
    value: item.value,
    displayValue: formatMoney(convertCurrency(item.value, displayRate), pieCurrency),
    meta: `${formatCount(item.count)} 只`,
  }));
  const topPositionTable = useResizableTableColumns({
    name: 210,
    account_id: 150,
    market: 110,
    position_layer: 150,
    normalized_market_value: 150,
    position_weight: 120,
    profit_loss_ratio: 120,
    ai: 170,
    snapshot_time: 190,
  });
  return (
    <div className="stack home-page">
      {emptySystem ? <FutuConnectionCard health={health} onRefresh={onFutuRefresh} onSync={onFutuSync} /> : null}
      {!dashboard || dashboard.empty ? (
        <Empty title="暂无持仓数据" body="连接 OpenD 并刷新后，这里会显示组合风险、持仓事项和数据状态。" />
      ) : (
        <>
          <section className="home-insight-grid">
            <article className="panel ai-summary-panel">
              <div className="toolbar">
                <div>
                  <h2>组合诊断</h2>
                  <small>{latestDiagnosis ? "来自最近一次持仓诊断报告" : "本地规则摘要，生成诊断后会替换为 AI 结论"}</small>
                </div>
                <div className="core-conclusion-actions">
                  <Tag color={latestDiagnosis ? "green" : "orange"}>{latestDiagnosis ? latestDiagnosis.provider : "local"}</Tag>
                  <Button type="primary" onClick={onGenerateDiagnosis}>生成持仓诊断</Button>
                  <Button disabled={!latestDiagnosis} onClick={() => latestDiagnosis && onOpenDiagnosisReport(latestDiagnosis.run_id)}>查看报告</Button>
                </div>
              </div>
              <div className="ai-point-grid">
                {aiPoints.map((item) => (
                  <div className={`ai-point ai-point-${item.tone}`} key={item.key}>
                    <span>{item.label}</span>
                    <strong>{item.summary}</strong>
                    {item.items.length ? (
                      <ul>
                        {item.items.map((detail) => (
                          <li key={`${detail.text}-${detail.reason || ""}`}>
                            {detail.code ? <em>{detail.code}</em> : null}
                            <b>{detail.text}</b>
                            {detail.reason ? <small>{detail.reason}</small> : null}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ))}
              </div>
              <div className="compact-snapshot-meta">
                <span><strong>快照</strong>{formatDate(snapshotTime)}</span>
                <span><strong>口径</strong>{accountName(accounts, selectedAccount)}</span>
                <span><strong>来源</strong>{sourceNames}</span>
              </div>
              <small className="currency-note home-currency-note">{currencyNote(baseCurrency, activeCurrency, displayRate, displayRateMeta)}</small>
            </article>
            <aside className="home-side-summary">
              <section className="summary-grid checkup-metric-grid">
                <Metric label="总资产" value={formatMoney(convertCurrency(dashboard.portfolio.total_assets, displayRate), activeCurrency)} />
                <Metric label="持仓市值" value={formatMoney(convertCurrency(dashboard.portfolio.total_position_value, displayRate), activeCurrency)} />
                <Metric label="现金" value={formatMoney(convertCurrency(dashboard.portfolio.cash, displayRate), activeCurrency)} />
              </section>
              <article className="panel risk-note-panel">
                <h2>风险提示</h2>
                <ul>
                  {riskNotes(dashboard, positions, dataQuality).map((item) => <li key={item}>{item}</li>)}
                </ul>
              </article>
            </aside>
          </section>
          <section className="home-chart-board">
            <div className="pie-overview-grid">
              <PieChart title="多账户资产占比" data={accountPieData} emptyText="暂无账户资产" />
              <PieChart title="多市场资产占比" data={marketPieData} emptyText="暂无市场持仓" />
              <PieChart title="仓位类型资产占比" data={layerPieData} emptyText="暂无分层持仓" />
            </div>
            <div className="analysis-grid">
              <PieChart title="盈利 / 亏损分布" data={profitPieData} emptyText="暂无盈亏数据" />
              <BarChart title="行业/主题集中度" subtitle={latestDiagnosis ? "来自最近一次持仓诊断报告" : "按标的名称和代码启发式归类"} data={themeGroups.slice(0, 8).map((item) => ({ label: item.theme, value: item.weight, displayValue: formatPercent(item.weight) }))} emptyText="暂无主题分类" />
              <BarChart title="交易复盘结果" subtitle="按结果标签统计笔数" data={tradeReviewBarData(tradeReviews, "result_label")} emptyText="暂无交易复盘" />
            </div>
          </section>
          <section className="panel top-channel-panel">
              <div className="toolbar">
                <div>
                  <h2>重点持仓</h2>
                  <small>按仓位、亏损、AI 关注优先级综合排序</small>
                </div>
                <span className="panel-chip">Snapshot</span>
              </div>
              <Table
                className="arco-data-table pro-table top-position-table"
                rowKey={(position: Position) => `${position.account_id}-${position.code}`}
                data={focusPositions}
                size="middle"
                hover
                tableLayoutFixed
                showSorterTooltip
                components={topPositionTable.components}
                border={{ wrapper: true, headerCell: false, bodyCell: false }}
                pagination={false}
                scroll={{ x: topPositionTable.totalTableWidth }}
                onRow={(position) => ({ onClick: () => onOpenCode(position.code) })}
                columns={[
                  {
                    title: "标的",
                    dataIndex: "name",
                    ...topPositionTable.columnProps("name"),
                    sorter: (a: Position, b: Position) => (a.name || a.code).localeCompare(b.name || b.code),
                    render: (_value, position: Position) => (
                      <span className="table-main-cell">
                        <strong>{position.name || position.code}</strong>
                      </span>
                    ),
                  },
                  { title: "账户", dataIndex: "account_id", ...topPositionTable.columnProps("account_id"), render: (value: string) => accountName(accounts, value) },
                  { title: "市场", dataIndex: "market", ...topPositionTable.columnProps("market"), render: (value: string) => marketName(value) },
                  {
                    title: "主题",
                    dataIndex: "position_layer",
                    ...topPositionTable.columnProps("position_layer"),
                    sorter: (a: Position, b: Position) => a.position_layer.localeCompare(b.position_layer),
                    render: (value: string) => <Tag color="arcoblue">{value}</Tag>,
                  },
                  {
                    title: "市值",
                    dataIndex: "normalized_market_value",
                    ...topPositionTable.columnProps("normalized_market_value"),
                    defaultSortOrder: "descend",
                    sorter: (a: Position, b: Position) => a.normalized_market_value - b.normalized_market_value,
                    render: (_value, position: Position) => formatMoney(position.normalized_market_value, position.normalized_currency),
                  },
                  {
                    title: "仓位",
                    dataIndex: "position_weight",
                    ...topPositionTable.columnProps("position_weight"),
                    sorter: (a: Position, b: Position) => a.position_weight - b.position_weight,
                    render: (value: number) => formatPercent(value),
                  },
                  {
                    title: "盈亏",
                    dataIndex: "profit_loss_ratio",
                    ...topPositionTable.columnProps("profit_loss_ratio"),
                    sorter: (a: Position, b: Position) => a.profit_loss_ratio - b.profit_loss_ratio,
                    render: (value: number) => <Tag color={value >= 0 ? "green" : "red"}>{formatPercent(value || 0)}</Tag>,
                  },
                  {
                    title: "AI 建议",
                    ...topPositionTable.columnProps("ai"),
                    render: (_value, position: Position) => aiRecommendationFor(position.code, dashboard.action_cards),
                  },
                  { title: "数据时间", dataIndex: "snapshot_time", ...topPositionTable.columnProps("snapshot_time"), render: (value: string) => formatDate(value) },
                ]}
              />
          </section>
        </>
      )}
    </div>
  );
}

export function CurrencyPill({ currencies, activeCurrency, setDisplayCurrency }: { currencies: string[]; activeCurrency: string; setDisplayCurrency: (currency: string) => void }) {
  if (!currencies.length) return null;
  return (
    <div className="currency-pill">
      <StyledSelect
        compact
        ariaLabel="切换总资产显示币种"
        value={activeCurrency}
        options={currencies.map((currency) => ({ value: currency, label: currency }))}
        onChange={setDisplayCurrency}
      />
    </div>
  );
}

export function StyledSelect({ value, options, onChange, ariaLabel, compact = false, className = "" }: { value: string; options: Array<{ value: string; label: string }>; onChange: (value: string) => void; ariaLabel: string; compact?: boolean; className?: string }) {
  return (
    <Select
      className={`styled-select ${compact ? "compact" : ""} ${className}`}
      size={compact ? "mini" : "default"}
      value={value}
      aria-label={ariaLabel}
      onChange={(nextValue) => onChange(String(nextValue))}
    >
      {options.map((option) => (
        <Select.Option
          key={option.value}
          value={option.value}
        >
          {option.label}
        </Select.Option>
      ))}
    </Select>
  );
}

type PieDatum = {
  id: string;
  label: string;
  value: number;
  displayValue: string;
  meta?: string;
  hoverItems?: string[];
};

export function PieChart({ title, data, emptyText }: { title: string; data: PieDatum[]; emptyText: string }) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const total = data.reduce((sum, item) => sum + Math.max(item.value, 0), 0);
  const slices = total > 0 ? data.map((item) => ({ ...item, weight: Math.max(item.value, 0) / total })) : [];
  const activeSlice = activeIndex === null ? slices[0] : slices[activeIndex] ?? slices[0];
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  let offsetCursor = 0;

  return (
    <article className="pie-card">
      <div className="pie-card-header">
        <div>
          <strong>{title}</strong>
          <small>{slices.length && activeSlice ? `${activeSlice.label} ${formatPercent(activeSlice.weight)}` : emptyText}</small>
        </div>
        {slices.length ? <span>{formatCount(slices.length)} 组</span> : null}
      </div>
      {slices.length ? (
        <>
          <div className="pie-visual-row">
            <div className="pie-chart" aria-label={title}>
              <svg viewBox="0 0 136 136" role="img">
                <circle className="pie-track" cx="68" cy="68" r={radius} />
                <circle className="pie-inner-ring" cx="68" cy="68" r="36" />
                <g transform="rotate(-90 68 68)">
                  {slices.map((item, index) => {
                    const rawLength = item.weight * circumference;
                    const dashLength = Math.max(rawLength, 0.1);
                    const dashOffset = -offsetCursor;
                    offsetCursor += rawLength;
                    return (
                      <circle
                        key={item.id}
                        className={`pie-segment ${activeIndex === index ? "active" : ""}`}
                        cx="68"
                        cy="68"
                        r={radius}
                        stroke={pieColor(index)}
                        strokeDasharray={`${dashLength} ${circumference - dashLength}`}
                        strokeDashoffset={dashOffset}
                        onMouseEnter={() => setActiveIndex(index)}
                        onMouseLeave={() => setActiveIndex(null)}
                        onFocus={() => setActiveIndex(index)}
                        onBlur={() => setActiveIndex(null)}
                        tabIndex={0}
                      />
                    );
                  })}
                </g>
              </svg>
              <span>
                <strong>{formatPercent(activeSlice.weight)}</strong>
                <small>占比</small>
              </span>
            </div>
          </div>
          <div className="pie-legend">
            {slices.map((item, index) => (
              <div className={`pie-legend-row ${activeIndex === index ? "active" : ""}`} key={item.id} onMouseEnter={() => setActiveIndex(index)} onMouseLeave={() => setActiveIndex(null)}>
                <i style={{ backgroundColor: pieColor(index) }} aria-hidden="true" />
                <span title={item.label}>{item.label}</span>
                <small>{item.meta ? `${item.meta} · ` : ""}{item.displayValue}</small>
                <strong>{formatPercent(item.weight)}</strong>
              </div>
            ))}
          </div>
        </>
      ) : <small className="pie-empty">{emptyText}</small>}
    </article>
  );
}

type BarDatum = {
  label: string;
  value: number;
  displayValue: string;
  tone?: "positive" | "negative" | "default";
};

export function BarChart({ title, subtitle, data, emptyText }: { title: string; subtitle: string; data: BarDatum[]; emptyText: string }) {
  const maxValue = Math.max(...data.map((item) => Math.abs(item.value)), 0);
  return (
    <article className="panel bar-card">
      <div className="pie-card-header">
        <div>
          <strong>{title}</strong>
          <small>{data.length ? subtitle : emptyText}</small>
        </div>
        {data.length ? <span>{formatCount(data.length)} 项</span> : null}
      </div>
      {data.length ? (
        <div className="bar-list">
          {data.map((item, index) => (
            <div className={`bar-row ${item.tone || "default"}`} key={`${item.label}-${index}`}>
              <span title={item.label}>{item.label}</span>
              <div className="bar-track"><i style={{ width: `${Math.max(4, Math.abs(item.value) / (maxValue || 1) * 100)}%`, backgroundColor: item.tone === "negative" ? "#ef4444" : item.tone === "positive" ? "#16a34a" : pieColor(index) }} /></div>
              <strong>{item.displayValue}</strong>
            </div>
          ))}
        </div>
      ) : <small className="pie-empty">{emptyText}</small>}
    </article>
  );
}

export function pieColor(index: number) {
  return ["#2563eb", "#16a34a", "#f59e0b", "#0ea5e9", "#ef4444", "#64748b", "#8b5cf6", "#14b8a6"][index % 8];
}

export function AccountDataPage({ accounts, health, emptySystem, onChanged, onImported, setNotice, requestConfirm, onRefresh, onRefreshHealth, loading }: { accounts: AccountSummary[]; health: HealthStatus | null; emptySystem: boolean; onChanged: () => Promise<void>; onImported: () => Promise<void>; setNotice: (notice: string) => void; requestConfirm: (options: ConfirmOptions) => Promise<boolean>; onRefresh: () => Promise<void>; onRefreshHealth: () => Promise<void>; loading: boolean }) {
  const [activeTab, setActiveTab] = useState("data");
  return (
    <div className="stack account-data-page">
      <section className="account-data-workbench">
        <Tabs activeTab={activeTab} onChange={(key) => setActiveTab(String(key))}>
          <Tabs.TabPane key="data" title="数据管理" />
          <Tabs.TabPane key="accounts" title="账户管理" />
        </Tabs>
      </section>
      {activeTab === "data" ? (
        <>
          {emptySystem ? <FutuConnectionCard health={health} onRefresh={onRefreshHealth} onSync={onRefresh} /> : null}
          <DataPage accounts={accounts} onImported={onImported} setNotice={setNotice} requestConfirm={requestConfirm} onRefresh={onRefresh} loading={loading} showAccountManagementLink onOpenAccounts={() => setActiveTab("accounts")} />
        </>
      ) : (
        <AccountsAdminPage accounts={accounts} onChanged={onChanged} setNotice={setNotice} requestConfirm={requestConfirm} onConnectFutu={async () => { setActiveTab("data"); await onRefresh(); }} />
      )}
    </div>
  );
}

export function AccountsAdminPage({ accounts, onChanged, setNotice, requestConfirm, onConnectFutu }: { accounts: AccountSummary[]; onChanged: () => Promise<void>; setNotice: (notice: string) => void; requestConfirm: (options: ConfirmOptions) => Promise<boolean>; onConnectFutu: () => Promise<void> }) {
  const [editing, setEditing] = useState<AccountSummary | null>(null);
  const [form, setForm] = useState(accountFormDefaults());
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  function edit(account: AccountSummary) {
    setEditing(account);
    setForm({
      display_name: account.display_name || account.account_id,
      source_name: account.source_name || "manual",
      institution: account.institution || "",
      account_type: account.account_type || "",
      base_currency: account.base_currency || "CNY",
      markets: account.markets?.join(",") || "",
      import_modes: importModesForAccount(account),
      position_import_modes: account.position_import_modes?.length ? account.position_import_modes : importModesForAccount(account),
      review_import_modes: account.review_import_modes?.length ? account.review_import_modes : importModesForAccount(account),
      market_data_provider: account.market_data_provider || "",
      news_data_provider: account.news_data_provider || "",
      enabled: account.enabled,
    });
    setModalOpen(true);
  }

  function reset() {
    setEditing(null);
    setForm(accountFormDefaults());
    setModalOpen(false);
  }

  async function save() {
    setSaving(true);
    try {
      const payload = {
        display_name: form.display_name.trim(),
        import_modes: mergeImportModes(form.position_import_modes, form.review_import_modes),
        import_mode: mergeImportModes(form.position_import_modes, form.review_import_modes).join(","),
        position_import_modes: form.position_import_modes,
        review_import_modes: form.review_import_modes,
        market_data_provider: form.market_data_provider,
        news_data_provider: form.news_data_provider,
        enabled: form.enabled,
        source_name: form.source_name,
        institution: form.institution.trim(),
        account_type: form.account_type,
        base_currency: form.base_currency,
        markets: form.markets.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean),
      };
      if (editing) {
        await api.updateAccount(editing.account_id, payload);
        setNotice("账户已更新");
      } else {
        await api.createAccount(payload);
        setNotice("账户已创建");
      }
      reset();
      await onChanged();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "账户保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function remove(account: AccountSummary) {
    const first = await requestConfirm({
      title: "删除账户",
      body: `确认删除账户「${account.display_name || account.account_id}」？该操作会先检查账户是否已有资产、持仓或成交数据。`,
      confirmText: "删除账户",
      tone: "danger",
    });
    if (!first) return;
    try {
      await api.deleteAccount(account.account_id, false);
      setNotice("账户已删除");
      await onChanged();
    } catch (error) {
      const confirm = await requestConfirm({
        title: "清理账户关联数据",
        body: "该账户已有资产、持仓或成交数据。继续删除会清理该账户关联数据，确认继续？",
        confirmText: "清理并删除",
        tone: "danger",
      });
      if (!confirm) {
        setNotice("已取消删除");
        return;
      }
      try {
        await api.deleteAccount(account.account_id, true);
        setNotice("账户及关联数据已删除");
        await onChanged();
      } catch (innerError) {
        setNotice(innerError instanceof Error ? innerError.message : "账户删除失败");
      }
    }
  }

  async function toggle(account: AccountSummary) {
    await api.updateAccount(account.account_id, { enabled: !account.enabled });
    setNotice(account.enabled ? "账户已停用" : "账户已启用");
    await onChanged();
  }
  const accountTable = useResizableTableColumns({
    display_name: 180,
    account_id: 170,
    source_name: 170,
    import_mode: 190,
    data_providers: 190,
    base_currency: 110,
    enabled: 110,
    snapshot_time: 190,
    actions: 220,
  });

  return (
    <div className="stack">
      <section className="panel account-list-panel">
        <div className="toolbar">
          <div>
            <h2>账户列表</h2>
            <small>Futu / OpenD 账户通过首次同步自动创建；手动账户用于 Excel、PDF 或截图导入。</small>
          </div>
          <div className="account-list-actions">
            <Button onClick={onConnectFutu}>连接 Futu 账户</Button>
            <Button type="primary" onClick={() => { setEditing(null); setForm(accountFormDefaults()); setModalOpen(true); }}>新增手动账户</Button>
          </div>
        </div>
        {accounts.length ? (
          <Table
            className="arco-data-table pro-table account-table"
            rowKey="account_id"
            data={accounts}
            size="middle"
            hover
            tableLayoutFixed
            showSorterTooltip
            components={accountTable.components}
            border={{ wrapper: true, headerCell: false, bodyCell: false }}
            pagination={false}
            scroll={{ x: accountTable.totalTableWidth }}
            columns={[
              {
                title: "账户",
                dataIndex: "display_name",
                ...accountTable.columnProps("display_name"),
                sorter: (a: AccountSummary, b: AccountSummary) => (a.display_name || a.account_id).localeCompare(b.display_name || b.account_id),
                render: (_value, account: AccountSummary) => (
                  <span className="table-main-cell"><strong>{account.display_name || account.account_id}</strong></span>
                ),
              },
              { title: "账户 ID", dataIndex: "account_id", ...accountTable.columnProps("account_id"), sorter: (a: AccountSummary, b: AccountSummary) => a.account_id.localeCompare(b.account_id) },
              {
                title: "账户来源",
                dataIndex: "source_name",
                ...accountTable.columnProps("source_name"),
                filters: [{ text: "Futu / OpenD", value: "futu" }, { text: "手动导入", value: "manual" }],
                onFilter: (value, row: AccountSummary) => accountSourceKind(row) === value,
                sorter: (a: AccountSummary, b: AccountSummary) => accountSourceLabel(a).localeCompare(accountSourceLabel(b)),
                render: (_value, account: AccountSummary) => <SpaceBetweenTags><Tag color={accountSourceKind(account) === "futu" ? "blue" : "gray"}>{accountSourceLabel(account)}</Tag><Tag color="arcoblue">{accountImportCapabilityLabel(account)}</Tag></SpaceBetweenTags>,
              },
              { title: "导入方式", ...accountTable.columnProps("import_mode"), render: (_value, account: AccountSummary) => accountImportConfigLabel(account) },
              { title: "数据源配置", ...accountTable.columnProps("data_providers"), render: (_value, account: AccountSummary) => accountProviderConfigLabel(account) },
              { title: "币种", dataIndex: "base_currency", ...accountTable.columnProps("base_currency") },
              {
                title: "状态",
                dataIndex: "enabled",
                ...accountTable.columnProps("enabled"),
                render: (enabled: boolean) => <Tag color={enabled ? "green" : "gray"}>{enabled ? "启用" : "停用"}</Tag>,
              },
              {
                title: "更新时间",
                dataIndex: "snapshot_time",
                ...accountTable.columnProps("snapshot_time"),
                render: (_value, account: AccountSummary) => formatDate(account.snapshot_time || account.last_sync_time),
              },
              {
                title: "操作",
                ...accountTable.staticColumnProps("actions"),
                align: "center",
                className: "table-operation-column",
                render: (_value, account: AccountSummary) => (
                  <div className="row-actions">
                    <Button size="mini" onClick={() => edit(account)}>编辑</Button>
                    <Button size="mini" onClick={() => toggle(account)}>{account.enabled ? "停用" : "启用"}</Button>
                    <Button size="mini" status="danger" onClick={() => remove(account)}>删除</Button>
                  </div>
                ),
              },
            ]}
          />
        ) : <Empty title="暂无账户" body="先创建一个账户，再到下方数据模块上传资产、持仓和成交记录。" />}
      </section>
      {modalOpen ? (
        <Drawer
          className="account-edit-drawer"
          width={720}
          visible
          title={editing ? "编辑账户" : "新增账户"}
          footer={(
            <div className="modal-actions">
              <Button onClick={reset}>取消</Button>
              <Button type="primary" onClick={save} disabled={saving || !form.display_name.trim() || !form.position_import_modes.length || !form.review_import_modes.length} loading={saving}>{editing ? "保存修改" : "创建账户"}</Button>
            </div>
          )}
          onCancel={reset}
        >
            <p className="metadata-note">账户 ID 由系统自动生成，导入数据时会自动绑定到账户。</p>
            <Form layout="vertical" className="account-form-grid arco-form-grid">
              <Form.Item label="账户名称" required>
                <Input autoFocus value={form.display_name} placeholder="例如：Futu 美股账户、支付宝理财" onChange={(value) => setForm({ ...form, display_name: value })} />
              </Form.Item>
              <Form.Item label="机构/平台">
                <Input value={form.institution} placeholder="例如：富途、支付宝、中信证券" onChange={(value) => setForm({ ...form, institution: value })} />
              </Form.Item>
              <Form.Item label="账户类型">
                <StyledSelect value={form.account_type} ariaLabel="选择账户类型" options={[{ value: "", label: "未填写" }, { value: "cash", label: "现金账户" }, { value: "margin", label: "融资账户" }, { value: "fund", label: "基金/理财账户" }, { value: "crypto", label: "数字资产账户" }]} onChange={(value) => setForm({ ...form, account_type: value })} />
              </Form.Item>
              <Form.Item label="基准币种">
                <StyledSelect value={form.base_currency} ariaLabel="选择基准币种" options={["CNY", "USD", "HKD", "CNH"].map((currency) => ({ value: currency, label: currency }))} onChange={(value) => setForm({ ...form, base_currency: value })} />
              </Form.Item>
              <Form.Item label="覆盖市场">
                <Input value={form.markets} placeholder="例如：US,HK,CN" onChange={(value) => setForm({ ...form, markets: value })} />
              </Form.Item>
              <Form.Item label="账户来源">
                <SpaceBetweenTags><Tag color={isFutuAccount(editing) ? "blue" : "gray"}>{isFutuAccount(editing) ? "Futu · OpenD" : "手动导入"}</Tag><small className="metadata-note">来源由创建方式决定，不能在这里修改。</small></SpaceBetweenTags>
              </Form.Item>
              <Form.Item label="持仓数据导入方式" required>
                <div className="checkbox-stack">
                  <Checkbox disabled={isFutuAccount(editing)} checked={isFutuAccount(editing) || form.position_import_modes.includes("api")} onChange={(checked) => setForm({ ...form, position_import_modes: toggleImportMode(form.position_import_modes, "api", checked) })}>API 导入</Checkbox>
                  <Checkbox disabled={isFutuAccount(editing)} checked={!isFutuAccount(editing) && form.position_import_modes.includes("local")} onChange={(checked) => setForm({ ...form, position_import_modes: toggleImportMode(form.position_import_modes, "local", checked) })}>本地导入</Checkbox>
                </div>
              </Form.Item>
              <Form.Item label="复盘数据导入方式" required>
                <div className="checkbox-stack">
                  <Checkbox disabled={isFutuAccount(editing)} checked={isFutuAccount(editing) || form.review_import_modes.includes("api")} onChange={(checked) => setForm({ ...form, review_import_modes: toggleImportMode(form.review_import_modes, "api", checked) })}>API 导入</Checkbox>
                  <Checkbox disabled={isFutuAccount(editing)} checked={!isFutuAccount(editing) && form.review_import_modes.includes("local")} onChange={(checked) => setForm({ ...form, review_import_modes: toggleImportMode(form.review_import_modes, "local", checked) })}>本地导入</Checkbox>
                </div>
              </Form.Item>
              <Form.Item label="行情数据配置">
                <StyledSelect value={form.market_data_provider} ariaLabel="选择行情数据配置" options={marketDataProviderOptions} onChange={(value) => setForm({ ...form, market_data_provider: value })} />
              </Form.Item>
              <Form.Item label="新闻数据配置">
                <StyledSelect value={form.news_data_provider} ariaLabel="选择新闻数据配置" options={newsDataProviderOptions} onChange={(value) => setForm({ ...form, news_data_provider: value })} />
              </Form.Item>
              <Form.Item label="账户状态">
                <Checkbox checked={form.enabled} onChange={(checked) => setForm({ ...form, enabled: checked })}>启用账户</Checkbox>
              </Form.Item>
            </Form>
        </Drawer>
      ) : null}
    </div>
  );
}

export function accountFormDefaults() {
  return { display_name: "", source_name: "manual", institution: "", account_type: "", base_currency: "CNY", markets: "", import_modes: ["local"], position_import_modes: ["local"], review_import_modes: ["local"], market_data_provider: "", news_data_provider: "", enabled: true };
}

export function importModesForAccount(account: AccountSummary) {
  if (account.import_modes?.length) return account.import_modes;
  const rawModes = new Set((account.import_mode || "").split(",").map((item) => item.trim().toLowerCase()).filter(Boolean));
  const modes: string[] = [];
  if (rawModes.has("api") || account.broker_provider) modes.push("api");
  if ([...rawModes].some((mode) => ["local", "manual", "excel", "file", "pdf", "screenshot"].includes(mode)) || !account.broker_provider) modes.push("local");
  return modes.length ? modes : ["local"];
}

export function toggleImportMode(modes: string[], mode: string, enabled: boolean) {
  if (enabled) return modes.includes(mode) ? modes : [...modes, mode];
  return modes.filter((item) => item !== mode);
}

export function mergeImportModes(...modeGroups: string[][]) {
  return Array.from(new Set(modeGroups.flat())).filter(Boolean);
}

export function importModeLabel(modes: string[]) {
  const labels = [];
  if (modes.includes("api")) labels.push("API 导入");
  if (modes.includes("local")) labels.push("本地导入");
  return labels.join(" / ") || "未配置";
}

export function accountImportConfigLabel(account: AccountSummary) {
  const positionModes = account.position_import_modes?.length ? account.position_import_modes : importModesForAccount(account);
  const reviewModes = account.review_import_modes?.length ? account.review_import_modes : importModesForAccount(account);
  return `持仓：${importModeLabel(positionModes)} · 复盘：${importModeLabel(reviewModes)}`;
}

export function accountProviderConfigLabel(account: AccountSummary) {
  return `行情：${providerOptionLabel(account.market_data_provider, marketDataProviderOptions)} · 新闻：${providerOptionLabel(account.news_data_provider, newsDataProviderOptions)}`;
}

export function providerOptionLabel(value = "", options: Array<{ value: string; label: string }>) {
  return options.find((item) => item.value === value)?.label || value || "系统推荐";
}

export function NewsView({ items, onOpenCode }: { items: NewsItem[]; onOpenCode?: (code: string) => void }) {
  if (!items.length) {
    return <Empty title="暂无消息面数据" body="刷新数据后，系统会从富途资讯为每个持仓同步最新新闻、公告和评级。" />;
  }
  return (
    <div className="news-list">
      {items.map((item) => (
        <article className="news-item" key={item.news_id}>
          <div className="news-meta">
            <button onClick={() => onOpenCode?.(item.code)}>{item.code}</button>
            <span>{item.news_sub_type || "资讯"}</span>
            <small>{item.publish_time ? formatDate(item.publish_time) : formatDate(item.fetched_at)}</small>
          </div>
          <h3>{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> : item.title}</h3>
          <small>{item.source || "富途资讯"} · {item.view_count ? `${formatCount(item.view_count)} 次浏览` : "已同步"}</small>
        </article>
      ))}
    </div>
  );
}

export function Positions({ positions, layer, setLayer, accounts, selectedAccount, onOpenCode }: { positions: Position[]; layer: string; setLayer: (layer: string) => void; accounts: AccountSummary[]; selectedAccount: string; onOpenCode: (code: string) => void }) {
  const [keyword, setKeyword] = useState("");
  const [market, setMarket] = useState("全部");
  const [pnl, setPnl] = useState("全部");
  const marketOptions = useMemo(() => ["全部", ...Array.from(new Set(positions.map((item) => item.market).filter(Boolean))).sort()], [positions]);
  const layerFilters = useMemo(() => layers.filter((item) => item !== "全部").map((item) => ({ text: item, value: item })), []);
  const marketFilters = useMemo(() => marketOptions.filter((item) => item !== "全部").map((item) => ({ text: marketName(item), value: item })), [marketOptions]);
  const filteredPositions = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return positions.filter((item) => {
      const matchesKeyword = !normalizedKeyword || `${item.name} ${item.code}`.toLowerCase().includes(normalizedKeyword);
      const matchesMarket = market === "全部" || item.market === market;
      const matchesPnl = pnl === "全部" || (pnl === "盈利" ? item.profit_loss_ratio >= 0 : item.profit_loss_ratio < 0);
      return matchesKeyword && matchesMarket && matchesPnl;
    });
  }, [keyword, market, pnl, positions]);
  const positionRowKey = (item: Position) => `${item.account_id}-${item.code}`;
  const positionTable = useResizableTableColumns({
    name: 170,
    code: 140,
    account_id: 140,
    position_layer: 150,
    normalized_market_value: 150,
    market: 130,
    currency_note: 180,
    position_weight: 120,
    profit_loss_ratio: 120,
  });

  return (
    <div className="stack">
      <div className="query-toolbar position-query-toolbar">
        <Input.Search
          className="query-input"
          allowClear
          placeholder="搜索标的名称或代码"
          value={keyword}
          onChange={setKeyword}
        />
        <Select value={layer} onChange={(value) => setLayer(String(value))} className="query-select">
          {layers.map((item) => <Select.Option key={item} value={item}>{item}</Select.Option>)}
        </Select>
        <Select value={market} onChange={(value) => setMarket(String(value))} className="query-select">
          {marketOptions.map((item) => <Select.Option key={item} value={item}>{item === "全部" ? "全部市场" : marketName(item)}</Select.Option>)}
        </Select>
        <Select value={pnl} onChange={(value) => setPnl(String(value))} className="query-select">
          {["全部", "盈利", "亏损"].map((item) => <Select.Option key={item} value={item}>{item === "全部" ? "全部盈亏" : item}</Select.Option>)}
        </Select>
      </div>
      <Table
        className="arco-data-table pro-table position-list-table desktop-position-table"
        rowKey={positionRowKey}
        data={filteredPositions}
        size="middle"
        hover
        tableLayoutFixed
        showSorterTooltip
        pagePosition="br"
        components={positionTable.components}
        border={{ wrapper: true, headerCell: false, bodyCell: false }}
        pagination={{
          pageSize: 20,
          sizeCanChange: true,
          sizeOptions: [10, 20, 50],
          showTotal: (total, range) => `第 ${range[0]}-${Math.min(range[1], total)} 条 / 共 ${total} 条`,
          pageSizeChangeResetCurrent: true,
        }}
        scroll={{ x: positionTable.totalTableWidth, y: 520 }}
        onRow={(item) => ({ onClick: () => onOpenCode(item.code) })}
        columns={[
          {
            title: "标的",
            dataIndex: "name",
            ...positionTable.columnProps("name"),
            sorter: (a: Position, b: Position) => (a.name || a.code).localeCompare(b.name || b.code),
            render: (_value, item: Position) => (
              <span className="table-main-cell"><strong>{item.name || item.code}</strong></span>
            ),
          },
          {
            title: "代码",
            dataIndex: "code",
            ...positionTable.columnProps("code"),
            sorter: (a: Position, b: Position) => a.code.localeCompare(b.code),
            render: (_value, item: Position) => `${item.code}${item.missing_market_code ? " · 简称展示" : ""}`,
          },
          {
            title: "账户",
            dataIndex: "account_id",
            ...positionTable.columnProps("account_id"),
            sorter: (a: Position, b: Position) => (a.account_count || 1) - (b.account_count || 1),
            render: (_value, item: Position) => item.account_count ? `${formatCount(item.account_count)} 个账户` : accountName(accounts, item.account_id),
          },
          {
            title: "仓位类型",
            dataIndex: "position_layer",
            ...positionTable.columnProps("position_layer"),
            filters: layerFilters,
            onFilter: (value, row: Position) => row.position_layer === value,
            sorter: (a: Position, b: Position) => a.position_layer.localeCompare(b.position_layer),
          },
          {
            title: "市值",
            dataIndex: "normalized_market_value",
            ...positionTable.columnProps("normalized_market_value"),
            defaultSortOrder: "descend",
            sorter: (a: Position, b: Position) => a.normalized_market_value - b.normalized_market_value,
            render: (_value, item: Position) => formatMoney(item.normalized_market_value, item.normalized_currency),
          },
          {
            title: "市场",
            dataIndex: "market",
            ...positionTable.columnProps("market"),
            filters: marketFilters,
            onFilter: (value, row: Position) => row.market === value,
            render: (value: string) => marketName(value),
          },
          {
            title: "币种说明",
            ...positionTable.columnProps("currency_note"),
            render: (_value, item: Position) => positionCurrencyLabel(item),
          },
          {
            title: "仓位",
            dataIndex: "position_weight",
            ...positionTable.columnProps("position_weight"),
            sorter: (a: Position, b: Position) => a.position_weight - b.position_weight,
            render: (value: number) => formatPercent(value),
          },
          {
            title: "盈亏",
            dataIndex: "profit_loss_ratio",
            ...positionTable.columnProps("profit_loss_ratio"),
            filters: [
              { text: "盈利", value: "gain" },
              { text: "亏损", value: "loss" },
            ],
            onFilter: (value, row: Position) => value === "gain" ? row.profit_loss_ratio >= 0 : row.profit_loss_ratio < 0,
            sorter: (a: Position, b: Position) => a.profit_loss_ratio - b.profit_loss_ratio,
            render: (value: number) => <span className={value >= 0 ? "gain" : "loss"}>{formatPercent(value)}</span>,
          },
        ]}
      />
      <div className="mobile-position-list">
        {filteredPositions.map((item) => (
          <button className="mobile-position-card" key={`${item.account_id}-${item.code}`} onClick={() => onOpenCode(item.code)}>
            <span>
              <strong>{item.name || item.code}</strong>
              <small>{item.code} · {item.position_layer}</small>
            </span>
            <span>
              <b>{formatMoney(item.normalized_market_value, item.normalized_currency)}</b>
              <small className={item.profit_loss_ratio >= 0 ? "gain" : "loss"}>{formatPercent(item.profit_loss_ratio)} · {formatPercent(item.position_weight)}</small>
            </span>
          </button>
        ))}
      </div>
      {!filteredPositions.length && <Empty title="没有符合条件的持仓" body="切换筛选或刷新数据后再查看。" />}
    </div>
  );
}

export function ReviewPage({ review, tradeReviews, selectedAccount, accounts, refreshingMarketData, onRefreshMarketData, onSaveIntent }: { review: Review | null; tradeReviews: TradeReviewList | null; selectedAccount: string; accounts: AccountSummary[]; refreshingMarketData: boolean; onRefreshMarketData: () => Promise<void>; onSaveIntent: (reviewId: string, note: string, tags: TradeIntentTags, plan: TradeIntentPlan) => Promise<void> }) {
  const [editingId, setEditingId] = useState("");
  const [draftNote, setDraftNote] = useState("");
  const [draftTags, setDraftTags] = useState<TradeIntentTags>(emptyIntentTags);
  const [draftPlan, setDraftPlan] = useState<TradeIntentPlan>(emptyIntentPlan);
  const [reviewFilter, setReviewFilter] = useState("全部");
  const [reviewSearch, setReviewSearch] = useState("");
  const [resultFilter, setResultFilter] = useState("全部结果");
  const [intentFilter, setIntentFilter] = useState("全部意图");
  const editingItem = tradeReviews?.items.find((item) => item.review_id === editingId) ?? null;
  const reviewTable = useResizableTableColumns({
    code: 150,
    side: 110,
    deal_time: 180,
    result_label: 150,
    price: 120,
    one_day_return: 130,
    five_day_return: 130,
    intent: 130,
    actions: 170,
  });
  if (!tradeReviews || tradeReviews.empty) {
    const account = accounts.find((item) => item.account_id === selectedAccount);
    const isFutuScope = selectedAccount === "all" || account?.broker_provider === "futu";
    return (
      <div className="stack">
        <Empty
          title="暂无成交复盘"
          body={isFutuScope ? "当前口径下还没有读取到富途历史成交。完成同步并读取到订单后，这里会按每笔成交复核交易理由和纪律。" : "当前账户来自截图、PDF 或手动导入，暂时没有订单明细来源，所以不会生成订单维度复盘。订单复盘目前只支持能从 API 拉取成交记录的 Futu 账户。"}
        />
      </div>
    );
  }
  const summary = tradeReviews.summary;
  const displayItems = tradeReviews.items.filter((item) => {
    const search = reviewSearch.trim().toLowerCase();
    const matchesSearch = !search || `${item.code} ${item.result_label} ${item.discipline_label}`.toLowerCase().includes(search);
    const matchesReview = reviewFilter === "全部" || (
      reviewFilter === "待处理"
        ? !hasIntent(item) || /风险|买高|卖飞|待验证|亏/.test(`${item.result_label}${item.discipline_label}`)
        : reviewFilter === "风险"
          ? /风险|买高|卖飞|亏/.test(`${item.result_label}${item.discipline_label}`)
          : hasIntent(item)
    );
    const matchesResult = resultFilter === "全部结果" || (resultFilter === "正向" ? /计划内|盈利|兑现|超额/.test(item.result_label) : /风险|亏|买高|卖飞|承压|待验证/.test(item.result_label));
    const matchesIntent = intentFilter === "全部意图" || (intentFilter === "已记录" ? hasIntent(item) : !hasIntent(item));
    return matchesSearch && matchesReview && matchesResult && matchesIntent;
  });
  return (
    <div className="stack">
      <section className="summary-grid">
        <Metric label="复盘成交" value={summary.trade_count} />
        <Metric label="待验证" value={summary.waiting_count} />
        <Metric label="买高/卖飞风险" value={summary.risk_count} />
        <Metric label="计划内或有理由" value={summary.planned_count} />
      </section>
      <section className="panel">
        <div className="toolbar review-toolbar">
          <div>
            <h2>成交复盘</h2>
            <small>默认聚焦风险项和未补意图项，减少长列表噪音</small>
          </div>
          <div className="review-filter-row">
            <Button type="primary" onClick={onRefreshMarketData} loading={refreshingMarketData} disabled={refreshingMarketData}>刷新复盘行情</Button>
            <Input.Search className="review-search-input" allowClear placeholder="搜索标的 / 结果" value={reviewSearch} onChange={setReviewSearch} />
            <Select value={reviewFilter} onChange={(value) => setReviewFilter(String(value))} className="review-filter-select">
              {["待处理", "风险", "已记录", "全部"].map((item) => <Select.Option key={item} value={item}>{item}</Select.Option>)}
            </Select>
            <Select value={resultFilter} onChange={(value) => setResultFilter(String(value))} className="review-filter-select">
              {["全部结果", "正向", "风险/待验证"].map((item) => <Select.Option key={item} value={item}>{item}</Select.Option>)}
            </Select>
            <Select value={intentFilter} onChange={(value) => setIntentFilter(String(value))} className="review-filter-select">
              {["全部意图", "已记录", "待补充"].map((item) => <Select.Option key={item} value={item}>{item}</Select.Option>)}
            </Select>
          </div>
        </div>
        <Table
          className="arco-data-table pro-table review-table"
          rowKey="review_id"
          data={displayItems}
          size="middle"
          hover
          tableLayoutFixed
          showSorterTooltip
          components={reviewTable.components}
          border={{ wrapper: true, headerCell: false, bodyCell: false }}
          pagination={{
            pageSize: 8,
            sizeCanChange: true,
            sizeOptions: [8, 16, 32],
            showTotal: (total, range) => `第 ${range[0]}-${Math.min(range[1], total)} 条 / 共 ${total} 条`,
            pageSizeChangeResetCurrent: true,
          }}
          scroll={{ x: reviewTable.totalTableWidth, y: 520 }}
          columns={[
            {
              title: "标的",
              dataIndex: "code",
              ...reviewTable.columnProps("code"),
              sorter: (a: TradeReview, b: TradeReview) => a.code.localeCompare(b.code),
              render: (_value, item: TradeReview) => (
                <span className="table-main-cell">
                  <strong>{item.code}</strong>
                </span>
              ),
            },
            { title: "方向", dataIndex: "side", ...reviewTable.columnProps("side"), filters: ["买入", "卖出"].map((item) => ({ text: item, value: item })), onFilter: (value, row: TradeReview) => sideName(row.side) === value, render: (value: string) => sideName(value) },
            { title: "成交时间", ...reviewTable.columnProps("deal_time"), sorter: (a: TradeReview, b: TradeReview) => new Date(a.deal_time ?? a.created_at).getTime() - new Date(b.deal_time ?? b.created_at).getTime(), render: (_value, item: TradeReview) => formatDate(item.deal_time ?? item.created_at) },
            { title: "结果", dataIndex: "result_label", ...reviewTable.columnProps("result_label"), filters: Array.from(new Set(displayItems.map((item) => item.result_label))).map((item) => ({ text: item, value: item })), onFilter: (value, row: TradeReview) => row.result_label === value, render: (value: string) => <Tag color={tradeReviewClass(value) === "risk" ? "red" : "arcoblue"}>{value}</Tag> },
            { title: "成交价", dataIndex: "price", ...reviewTable.columnProps("price"), sorter: (a: TradeReview, b: TradeReview) => a.price - b.price, render: (value: number) => formatPrice(value) },
            { title: "1日表现", dataIndex: "one_day_return", ...reviewTable.columnProps("one_day_return"), sorter: (a: TradeReview, b: TradeReview) => Number(a.one_day_return ?? -Infinity) - Number(b.one_day_return ?? -Infinity), render: (value?: number | null) => formatOptionalPercent(value) },
            { title: "5日表现", dataIndex: "five_day_return", ...reviewTable.columnProps("five_day_return"), sorter: (a: TradeReview, b: TradeReview) => Number(a.five_day_return ?? -Infinity) - Number(b.five_day_return ?? -Infinity), render: (value?: number | null) => formatOptionalPercent(value) },
            { title: "交易意图", ...reviewTable.columnProps("intent"), filters: [{ text: "已记录", value: "recorded" }, { text: "待补充", value: "missing" }], onFilter: (value, row: TradeReview) => value === "recorded" ? hasIntent(row) : !hasIntent(row), render: (_value, item: TradeReview) => <Tag color={hasIntent(item) ? "green" : "orange"}>{hasIntent(item) ? "已记录" : "待补充"}</Tag> },
            {
              title: "操作",
              ...reviewTable.staticColumnProps("actions"),
              align: "center",
              className: "table-operation-column",
              render: (_value, item: TradeReview) => (
                <Button
                  size="small"
                  type="primary"
                  onClick={() => {
                    setEditingId(item.review_id);
                    setDraftNote(item.user_note);
                    setDraftTags(copyIntentTags(item.intent_tags));
                    setDraftPlan({ ...emptyIntentPlan, ...(item.intent_plan ?? {}) });
                  }}
                >
                  {hasIntent(item) ? "查看/编辑" : "补充意图"}
                </Button>
              ),
            },
          ]}
        />
      </section>
      {editingItem ? (
        <IntentEditorModal
          item={editingItem}
          note={draftNote}
          setNote={setDraftNote}
          tags={draftTags}
          setTags={setDraftTags}
          plan={draftPlan}
          setPlan={setDraftPlan}
          onClose={() => setEditingId("")}
          onSave={async () => { await onSaveIntent(editingItem.review_id, draftNote, draftTags, draftPlan); setEditingId(""); }}
        />
      ) : null}
    </div>
  );
}

export function IntentTagEditor({ tags, setTags }: { tags: TradeIntentTags; setTags: (tags: TradeIntentTags) => void }) {
  return (
    <div className="intent-groups">
      {intentTagGroups.map((group) => (
        <div className="intent-group" key={group.key}>
          <div className="intent-group-title">
            <strong>{group.title.replace("标签", "")}</strong>
            <span>{(tags[group.key] ?? []).length ? `已选 ${(tags[group.key] ?? []).length}` : "可多选"}</span>
          </div>
          <Checkbox.Group
            className="intent-options intent-option-pills"
            value={tags[group.key] ?? []}
            options={group.items}
            onChange={(values) => setTags({ ...tags, [group.key]: values.map(String) })}
          />
        </div>
      ))}
    </div>
  );
}

export function IntentEditorModal({ item, note, setNote, tags, setTags, plan, setPlan, onClose, onSave }: { item: TradeReview; note: string; setNote: (value: string) => void; tags: TradeIntentTags; setTags: (tags: TradeIntentTags) => void; plan: TradeIntentPlan; setPlan: (plan: TradeIntentPlan) => void; onClose: () => void; onSave: () => Promise<void> }) {
  const [saving, setSaving] = useState(false);
  const [aiExpanded, setAiExpanded] = useState(false);
  const planHasContent = Boolean(plan.holding_period || plan.stop_loss_type || plan.take_profit_type || plan.stop_loss_price || plan.take_profit_price);
  const [planOpen, setPlanOpen] = useState(planHasContent);
  const selectedIntentTags = intentTagGroups.flatMap((group) => (tags[group.key] ?? []).map((tag) => `${group.title.replace("标签", "")}:${tag}`));
  const aiCommentary = item.ai_commentary?.trim() || "";
  const aiPreview = aiCommentary.length > 120 ? `${aiCommentary.slice(0, 120)}...` : aiCommentary;
  async function submit() {
    setSaving(true);
    try {
      await onSave();
    } finally {
      setSaving(false);
    }
  }
  return (
    <Drawer
      className="intent-drawer"
      width="min(860px, 100vw)"
      visible
      title="补充交易意图"
      footer={(
        <div className="intent-drawer-footer">
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={submit} loading={saving}>保存</Button>
        </div>
      )}
      onCancel={onClose}
    >
      <div className="intent-workbench">
        <section className="intent-trade-hero">
          <div className="intent-trade-title">
            <small>这笔交易</small>
            <h3>{item.code}</h3>
          </div>
          <div className="intent-trade-facts">
            <span><small>方向</small><strong>{sideName(item.side)}</strong></span>
            <span><small>成交价</small><strong>{formatPrice(item.price)}</strong></span>
            <span><small>数量</small><strong>{item.quantity}</strong></span>
            <span><small>成交时间</small><strong>{formatDate(item.deal_time ?? item.created_at)}</strong></span>
            <span><small>结果</small><Tag color={tradeReviewClass(item.result_label) === "risk" ? "red" : "arcoblue"}>{item.result_label}</Tag></span>
            <span><small>纪律</small><strong>{item.discipline_label}</strong></span>
          </div>
        </section>

        <section className="intent-ai-card">
          <div className="intent-card-heading">
            <div>
              <h3>系统判断</h3>
              <small>先参考，不代表最终复盘结论</small>
            </div>
            {aiCommentary.length > 120 ? (
              <Button size="mini" type="text" onClick={() => setAiExpanded((value) => !value)}>{aiExpanded ? "收起" : "展开"}</Button>
            ) : null}
          </div>
          <p>{aiCommentary ? (aiExpanded ? aiCommentary : aiPreview) : "暂无 AI 复盘说明"}</p>
        </section>

        <section className="intent-section intent-primary-section">
          <div className="intent-card-heading">
            <div>
              <h3>快速标记意图</h3>
              <small>选出当时最接近的理由，之后可以继续补充</small>
            </div>
            <span className="intent-count-badge">{selectedIntentTags.length ? `已选 ${selectedIntentTags.length}` : "未选择"}</span>
          </div>
          <div className="intent-selected-summary">
            {selectedIntentTags.length ? selectedIntentTags.map((tag) => <span key={tag}>{tag}</span>) : <small>选中的意图会显示在这里，保存前可以快速确认。</small>}
          </div>
          <IntentTagEditor tags={tags} setTags={setTags} />
        </section>

        <section className="intent-section">
          <h3>当时为什么做这笔交易</h3>
          <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="例如：卖出是因为止盈兑现，还是因为原计划失效；买入是因为突破、回踩、消息驱动，还是单纯怕错过。" />
        </section>

        <details className="intent-section intent-plan-details" open={planOpen} onToggle={(event) => setPlanOpen(event.currentTarget.open)}>
          <summary>
            <span>退出计划</span>
            <small>{planHasContent ? "已填写" : "可选"}</small>
          </summary>
          <div className="intent-plan-grid">
            <label>计划持有周期<SelectInput value={plan.holding_period ?? ""} options={["未填写", "日内", "1-5日", "1-4周", "1-3个月", "长期"]} onChange={(value) => setPlan({ ...plan, holding_period: value })} /></label>
            <label>计划止损类型<SelectInput value={plan.stop_loss_type ?? ""} options={["未填写", "价格止损", "时间止损", "逻辑失效", "波动止损"]} onChange={(value) => setPlan({ ...plan, stop_loss_type: value })} /></label>
            <label>计划止盈类型<SelectInput value={plan.take_profit_type ?? ""} options={["未填写", "目标价止盈", "分批止盈", "移动止盈", "事件兑现"]} onChange={(value) => setPlan({ ...plan, take_profit_type: value })} /></label>
            <label>计划止损价<input value={plan.stop_loss_price ?? ""} onChange={(event) => setPlan({ ...plan, stop_loss_price: event.target.value })} /></label>
            <label>计划止盈价<input value={plan.take_profit_price ?? ""} onChange={(event) => setPlan({ ...plan, take_profit_price: event.target.value })} /></label>
          </div>
        </details>
      </div>
    </Drawer>
  );
}

export function IntentTagSummary({ tags }: { tags: TradeIntentTags }) {
  const selected = intentTagGroups.flatMap((group) => (tags?.[group.key] ?? []).map((tag) => `${group.title.replace("标签", "")}:${tag}`));
  if (!selected.length) return <small>暂无意图标签</small>;
  return <div className="intent-summary">{selected.map((item) => <span key={item}>{item}</span>)}</div>;
}

export function SelectInput({ value, options, onChange }: { value: string; options: string[]; onChange: (value: string) => void }) {
  const normalizedValue = value || "未填写";
  return (
    <StyledSelect
      value={normalizedValue}
      ariaLabel="选择交易计划"
      options={options.map((option) => ({ value: option, label: option }))}
      onChange={(nextValue) => onChange(nextValue === "未填写" ? "" : nextValue)}
    />
  );
}

export function ProfilePage({ profile, positions, selectedAccount, accounts, health, setNotice, requestConfirm, homeIntent, onHomeIntentHandled, onWorkflowRunsChanged }: { profile: Profile | null; positions: Position[]; selectedAccount: string; accounts: AccountSummary[]; health: HealthStatus | null; setNotice: (notice: string) => void; requestConfirm: (options: ConfirmOptions) => Promise<boolean>; homeIntent?: ProfilePageIntent; onHomeIntentHandled?: () => void; onWorkflowRunsChanged?: (runs: AIWorkflowRun[]) => void }) {
  const [preference, setPreference] = useState<InvestorPreference | null>(null);
  const [workflowRuns, setWorkflowRuns] = useState<AIWorkflowRun[]>([]);
  const [activeRun, setActiveRun] = useState<AIWorkflowRun | null>(null);
  const [streamText, setStreamText] = useState("");
  const [streamArtifacts, setStreamArtifacts] = useState<WorkflowArtifact[]>([]);
  const [streamSteps, setStreamSteps] = useState<WorkflowStep[]>([]);
  const [runningWorkflow, setRunningWorkflow] = useState("");
  const [workflowWindowOpen, setWorkflowWindowOpen] = useState(false);
  const [workflowStatusText, setWorkflowStatusText] = useState("");
  const [preferenceEditorOpen, setPreferenceEditorOpen] = useState(false);
  const workflowSourceRef = useRef<EventSource | null>(null);
  const handledHomeIntentRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.profilePreferences(selectedAccount), api.profileWorkflows(selectedAccount)])
      .then(([pref, runs]) => {
        if (cancelled) return;
        setPreference(pref);
        setWorkflowRuns(runs.items);
        const active = runs.items.find((run) => run.status === "running" || run.status === "pending");
        setRunningWorkflow(active?.workflow_type ?? "");
        if (!activeRun && runs.items.length) {
          setActiveRun(runs.items[0]);
          setStreamText(runs.items[0].output?.markdown ?? runs.items[0].output?.partial_markdown ?? "");
          setStreamArtifacts(runs.items[0].artifacts ?? []);
          setStreamSteps(stepsForDisplay(runs.items[0]));
        }
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "组合诊断数据加载失败"));
    return () => {
      cancelled = true;
    };
  }, [selectedAccount]);

  useEffect(() => {
    onWorkflowRunsChanged?.(workflowRuns);
  }, [workflowRuns, onWorkflowRunsChanged]);

  useEffect(() => {
    if (!homeIntent || handledHomeIntentRef.current === homeIntent.requestId) return;
    if (homeIntent.kind === "generate") {
      handledHomeIntentRef.current = homeIntent.requestId;
      onHomeIntentHandled?.();
      startWorkflow("portfolio_diagnosis");
      return;
    }
    if (homeIntent.kind === "open" && homeIntent.runId) {
      const target = workflowRuns.find((run) => run.run_id === homeIntent.runId);
      if (!target) return;
      handledHomeIntentRef.current = homeIntent.requestId;
      onHomeIntentHandled?.();
      openHistoricalRun(target);
    }
  }, [homeIntent, workflowRuns]);

  async function savePreference(next: InvestorPreference) {
    const saved = await api.saveProfilePreferences(selectedAccount, next);
    setPreference(saved);
    setNotice("投资偏好已保存");
  }

  async function startWorkflow(workflowType: AIWorkflowRun["workflow_type"]) {
    const sendsExternal = Boolean(health?.ai?.configured && health.ai.provider !== "local");
    if (sendsExternal) {
      const ok = await requestConfirm({
        title: "生成组合诊断分析",
        body: "将发送当前账户口径下的账户摘要、持仓、成交、投资偏好和行情摘要给当前启用的大模型生成分析。",
        confirmText: "继续分析",
      });
      if (!ok) {
        setNotice("已取消组合诊断分析");
        return;
      }
    }
    setRunningWorkflow(workflowType);
    setWorkflowWindowOpen(true);
    setWorkflowStatusText("正在创建工作流...");
    setActiveRun(createPendingWorkflowRun(workflowType, selectedAccount));
    setStreamText("");
    setStreamArtifacts([]);
    setStreamSteps([]);
    try {
      const created = await api.createProfileWorkflow(workflowType, selectedAccount, sendsExternal);
      setWorkflowStatusText("工作流已创建，正在连接流式通道...");
      setActiveRun(created.run);
      setWorkflowRuns((items) => [created.run, ...items]);
      attachWorkflowStream(created.run, true);
    } catch (error) {
      setRunningWorkflow("");
      setWorkflowStatusText(error instanceof Error ? error.message : "组合诊断生成失败");
      setNotice(error instanceof Error ? error.message : "组合诊断生成失败");
    }
  }

  function attachWorkflowStream(run: AIWorkflowRun, resetText = false) {
    workflowSourceRef.current?.close();
    if (resetText) {
      setStreamText("");
      setStreamArtifacts([]);
      setStreamSteps([]);
    }
    setRunningWorkflow(run.workflow_type);
    const source = new EventSource(api.profileWorkflowStreamUrl(run.run_id));
    workflowSourceRef.current = source;
    source.addEventListener("run_started", (event) => {
      const nextRun = JSON.parse((event as MessageEvent).data) as AIWorkflowRun;
      setActiveRun((current) => ({ ...nextRun, steps: current?.run_id === nextRun.run_id && current.steps.length ? current.steps : nextRun.steps ?? [] }));
      setWorkflowRuns((items) => [nextRun, ...items.filter((item) => item.run_id !== nextRun.run_id)]);
      setWorkflowStatusText("已连接流式通道，开始执行...");
    });
    source.addEventListener("step_started", (event) => {
      const step = JSON.parse((event as MessageEvent).data) as WorkflowStep;
      updateRunStep(step);
      setWorkflowStatusText(`正在执行：步骤${step.step_no} ${step.title}`);
    });
    source.addEventListener("step_completed", (event) => {
      const step = JSON.parse((event as MessageEvent).data) as WorkflowStep;
      updateRunStep(step);
      setWorkflowStatusText(`已完成：步骤${step.step_no} ${step.title}`);
    });
    source.addEventListener("agent_thought", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { turn?: number; thought_summary?: string; why?: string; expected_observation?: string };
      if (payload.turn) {
        updateRunStep({
          step_no: payload.turn,
          title: "Agent 正在思考下一步",
          detail: payload.why || "基于已获得的 observation 决定下一步工具调用",
          action_type: "agent_thought",
          action_label: "Agent 思考",
          status: "running",
          artifact_ids: [],
          agent_note: payload.thought_summary,
          expected_observation: payload.expected_observation,
        });
      }
      setWorkflowStatusText(payload.thought_summary || payload.why || "Agent 正在思考下一步...");
    });
    source.addEventListener("tool_started", (event) => {
      const step = JSON.parse((event as MessageEvent).data) as WorkflowStep;
      updateRunStep(step);
      setWorkflowStatusText(`正在调用工具：${step.tool_name || step.action_label}`);
    });
    source.addEventListener("tool_completed", (event) => {
      const step = JSON.parse((event as MessageEvent).data) as WorkflowStep;
      updateRunStep(step);
      setWorkflowStatusText(`工具完成：${step.tool_name || step.action_label}`);
    });
    source.addEventListener("agent_warning", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { message?: string };
      setWorkflowStatusText(payload.message || "章节降级，继续生成后续内容");
    });
    source.addEventListener("artifact_created", (event) => {
      const artifact = JSON.parse((event as MessageEvent).data) as WorkflowArtifact;
      setStreamArtifacts((items) => [...items.filter((item) => item.artifact_id !== artifact.artifact_id), artifact]);
      setWorkflowStatusText(`已生成图表：${artifact.title}`);
    });
    source.addEventListener("content_delta", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { delta: string };
      setStreamText((text) => text + payload.delta);
      setWorkflowStatusText("正在按章节流式生成报告...");
    });
    source.addEventListener("report_quality_issues", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { issues?: string[] };
      const count = Array.isArray(payload.issues) ? payload.issues.length : 0;
      setWorkflowStatusText(count ? `报告已生成，发现 ${count} 个质量问题待复核` : "报告质量检查完成");
    });
    source.addEventListener("run_completed", (event) => {
      const nextRun = JSON.parse((event as MessageEvent).data) as AIWorkflowRun;
      setActiveRun(nextRun);
      setStreamText(nextRun.output?.markdown ?? "");
      setStreamArtifacts(nextRun.artifacts ?? []);
      setStreamSteps(stepsForDisplay(nextRun));
      setWorkflowRuns((items) => [nextRun, ...items.filter((item) => item.run_id !== nextRun.run_id)]);
      setRunningWorkflow("");
      const qualityIssues = getWorkflowQualityIssues(nextRun);
      setWorkflowStatusText(qualityIssues.length ? `生成完成，发现 ${qualityIssues.length} 个质量问题待复核` : "生成完成，结果已保存");
      setNotice(qualityIssues.length ? `${nextRun.workflow_label}已生成，质量问题待复核` : `${nextRun.workflow_label}已生成`);
      source.close();
      if (workflowSourceRef.current === source) workflowSourceRef.current = null;
    });
    source.addEventListener("run_failed", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { error: string };
      setRunningWorkflow("");
      setWorkflowStatusText(payload.error || "生成失败");
      setNotice(payload.error || "组合诊断生成失败");
      source.close();
      if (workflowSourceRef.current === source) workflowSourceRef.current = null;
      api.profileWorkflowDetail(run.run_id).then(({ run: latest }) => {
        setActiveRun(latest);
        setStreamText(latest.output?.markdown ?? latest.output?.partial_markdown ?? "");
        setStreamArtifacts(latest.artifacts ?? []);
        setStreamSteps(stepsForDisplay(latest));
        setWorkflowRuns((items) => [latest, ...items.filter((item) => item.run_id !== latest.run_id)]);
      }).catch(() => undefined);
    });
    source.onerror = () => {
      setRunningWorkflow("");
      setWorkflowStatusText("流式连接中断，可稍后重新打开这条记录继续查看或终止");
      setNotice("组合诊断流式连接中断");
      source.close();
      if (workflowSourceRef.current === source) workflowSourceRef.current = null;
    };
  }

  function updateRunStep(step: WorkflowStep) {
    setStreamSteps((items) => upsertWorkflowStep(items, step));
    setActiveRun((run) => {
      if (!run) return run;
      const steps = upsertWorkflowStep(run.steps ?? [], step);
      return { ...run, steps };
    });
  }

  function openHistoricalRun(run: AIWorkflowRun) {
    workflowSourceRef.current?.close();
    setActiveRun(run);
    setStreamText(run.output?.markdown ?? run.output?.partial_markdown ?? "");
    setStreamArtifacts(run.artifacts ?? []);
    setStreamSteps(stepsForDisplay(run));
    setWorkflowStatusText(run.status === "running" || run.status === "pending" ? "已重新接入生成进度" : "已加载历史报告");
    setWorkflowWindowOpen(true);
    if (run.status === "running" || run.status === "pending") {
      attachWorkflowStream(run, false);
    }
  }

  async function cancelWorkflow(run: AIWorkflowRun) {
    const cancelled = await api.cancelProfileWorkflow(run.run_id);
    workflowSourceRef.current?.close();
    workflowSourceRef.current = null;
    setRunningWorkflow("");
    setActiveRun(cancelled.run);
    setStreamSteps(stepsForDisplay(cancelled.run));
    setWorkflowRuns((items) => [cancelled.run, ...items.filter((item) => item.run_id !== cancelled.run.run_id)]);
    setWorkflowStatusText("已终止生成");
    setNotice("已终止报告生成");
  }

  async function deleteWorkflowRun(run: AIWorkflowRun) {
    try {
      await api.deleteProfileWorkflow(run.run_id);
      setWorkflowRuns((items) => items.filter((item) => item.run_id !== run.run_id));
      if (activeRun?.run_id === run.run_id) {
        workflowSourceRef.current?.close();
        workflowSourceRef.current = null;
        setActiveRun(null);
        setStreamText("");
        setStreamArtifacts([]);
        setStreamSteps([]);
        setWorkflowWindowOpen(false);
        setWorkflowStatusText("");
      }
      if ((run.status === "running" || run.status === "pending") && runningWorkflow === run.workflow_type) {
        setRunningWorkflow("");
      }
      setNotice("报告记录已删除");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "报告记录删除失败");
    }
  }

  const draft = preference ?? {
    empty: true,
    account_id: selectedAccount,
    kyc_profile: {},
    risk_tolerance: "",
    investment_horizon: "",
    liquidity_needs: "",
    target_return: "",
    notes: "",
  };
  const displayedText = streamText || activeRun?.output?.markdown || "";
  const displayedArtifacts = streamArtifacts.length ? streamArtifacts : activeRun?.artifacts ?? [];
  const displayedRun = activeRun ? { ...activeRun, steps: streamSteps.length ? streamSteps : stepsForDisplay(activeRun) } : null;

  return (
    <div className="stack">
      <PreferenceSummaryCard preference={draft} onEdit={() => setPreferenceEditorOpen(true)} />
      {preferenceEditorOpen ? <PreferenceEditorModal preference={draft} onSave={savePreference} onClose={() => setPreferenceEditorOpen(false)} /> : null}
      <WorkflowFeatureCards runs={workflowRuns} runningWorkflow={runningWorkflow} onGenerate={startWorkflow} />
      <WorkflowRunTable runs={workflowRuns} onOpen={openHistoricalRun} onDelete={deleteWorkflowRun} />
      {workflowWindowOpen && displayedRun ? (
        <WorkflowWindow
          run={displayedRun}
          text={displayedText}
          artifacts={displayedArtifacts}
          statusText={workflowStatusText}
          onClose={() => setWorkflowWindowOpen(false)}
          onRetry={() => startWorkflow(displayedRun.workflow_type)}
          onCancel={() => cancelWorkflow(displayedRun)}
        />
      ) : null}
    </div>
  );
}

export function PreferenceSummaryCard({ preference, onEdit }: { preference: InvestorPreference; onEdit: () => void }) {
  const filled = preference.kyc_completeness?.filled_count ?? [
    preference.risk_tolerance,
    preference.investment_horizon,
    preference.liquidity_needs,
    preference.target_return,
    preference.kyc_profile?.investment_objective,
    preference.kyc_profile?.investment_experience,
  ].filter(Boolean).length;
  const total = preference.kyc_completeness?.total_count;
  return (
    <section className="panel preference-summary-card">
      <div>
        <h2>投资偏好</h2>
        <small>本地保存 KYC 问卷、风险承受能力、资金来源、现金流和适当性约束，作为 AI 分析依据</small>
      </div>
      <div className="preference-summary-meta">
        <strong>{filled ? `已填写 ${filled}${total ? `/${total}` : ""} 项` : "尚未填写"}</strong>
        <small>{preference.updated_at ? `最近更新 ${formatDate(preference.updated_at)}` : "用于提升画像和配置建议置信度"}</small>
      </div>
      <Button onClick={onEdit}>编辑</Button>
    </section>
  );
}

export function PreferenceEditorModal({ preference, onSave, onClose }: { preference: InvestorPreference; onSave: (preference: InvestorPreference) => Promise<void>; onClose: () => void }) {
  const [draft, setDraft] = useState<InvestorPreference>(preference);
  const [saving, setSaving] = useState(false);

  useEffect(() => setDraft(preference), [preference.account_id, preference.updated_at]);
  const kycValue = (key: string) => String(draft.kyc_profile?.[key] ?? "");
  const setKyc = (key: string, value: string) => setDraft({ ...draft, kyc_profile: { ...draft.kyc_profile, [key]: value } });

  async function submit() {
    setSaving(true);
    try {
      await onSave(draft);
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      className="preference-editor-drawer"
      width={860}
      visible
      title="编辑投资偏好"
      footer={(
        <div className="modal-actions preference-editor-actions">
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={submit} loading={saving}>保存</Button>
        </div>
      )}
      onCancel={onClose}
    >
      <Tabs defaultActiveTab="basic">
        <Tabs.TabPane key="basic" title="基础与财务">
          <div className="kyc-questionnaire">
          <div className="field-label">年龄区间<SelectInput value={kycValue("age_range")} options={["未填写", "18-29", "30-39", "40-49", "50-59", "60以上"]} onChange={(value) => setKyc("age_range", value)} /></div>
          <div className="field-label">就业状态<SelectInput value={kycValue("employment_status")} options={["未填写", "受雇", "自雇", "企业主", "自由职业", "退休", "学生", "其他"]} onChange={(value) => setKyc("employment_status", value)} /></div>
          <div className="field-label">详细职业与行业<input value={kycValue("occupation_industry")} onChange={(event) => setKyc("occupation_industry", event.target.value)} placeholder="例如：软件工程师 / 互联网" /></div>
          <div className="field-label">年收入范围<SelectInput value={kycValue("annual_income")} options={["未填写", "低于20万", "20万-50万", "50万-100万", "100万-300万", "300万以上"]} onChange={(value) => setKyc("annual_income", value)} /></div>
          <div className="field-label">收入稳定性<SelectInput value={kycValue("income_stability")} options={["未填写", "稳定工资", "奖金/佣金波动", "经营性收入", "投资收入为主", "暂不稳定"]} onChange={(value) => setKyc("income_stability", value)} /></div>
          <div className="field-label">净资产范围<SelectInput value={kycValue("net_worth")} options={["未填写", "低于50万", "50万-200万", "200万-500万", "500万-1000万", "1000万以上"]} onChange={(value) => setKyc("net_worth", value)} /></div>
          <div className="field-label">可投资/流动资产<SelectInput value={kycValue("liquid_assets")} options={["未填写", "低于20万", "20万-50万", "50万-200万", "200万-500万", "500万以上"]} onChange={(value) => setKyc("liquid_assets", value)} /></div>
          <div className="field-label">负债与杠杆情况<SelectInput value={kycValue("liabilities")} options={["未填写", "无负债", "房贷为主", "消费贷/信用贷", "经营贷", "保证金/融资负债"]} onChange={(value) => setKyc("liabilities", value)} /></div>
          <div className="field-label">月度现金流状况<SelectInput value={kycValue("monthly_cash_flow")} options={["未填写", "稳定结余", "基本收支平衡", "阶段性大额支出", "现金流波动较大", "需要投资账户补流动性"]} onChange={(value) => setKyc("monthly_cash_flow", value)} /></div>
          <div className="field-label">投资资金来源<SelectInput value={kycValue("source_of_funds")} options={["未填写", "工资/奖金", "经营收入", "资产出售", "投资收益", "继承/赠与", "其他合法来源"]} onChange={(value) => setKyc("source_of_funds", value)} /></div>
          <div className="field-label">财富来源<SelectInput value={kycValue("source_of_wealth")} options={["未填写", "劳动收入积累", "创业/经营积累", "房产/资产增值", "长期投资积累", "家庭赠与/继承", "其他"]} onChange={(value) => setKyc("source_of_wealth", value)} /></div>
          <div className="field-label">税务身份/居民地<input value={kycValue("tax_residency")} onChange={(event) => setKyc("tax_residency", event.target.value)} placeholder="例如：中国税收居民，常驻上海" /></div>
          <div className="field-label">其他投资/持仓<input value={kycValue("other_investments")} onChange={(event) => setKyc("other_investments", event.target.value)} placeholder="例如：房产、基金、理财、保险" /></div>
          </div>
        </Tabs.TabPane>
        <Tabs.TabPane key="investment" title="投资偏好">
          <div className="kyc-questionnaire">
          <div className="field-label">投资目标<SelectInput value={kycValue("investment_objective")} options={["未填写", "资本保值", "稳定收入", "长期增值", "积极增长", "短线交易"]} onChange={(value) => setKyc("investment_objective", value)} /></div>
          <div className="field-label">投资经验<SelectInput value={kycValue("investment_experience")} options={["未填写", "少于1年", "1-3年", "3-5年", "5年以上", "专业投资经验"]} onChange={(value) => setKyc("investment_experience", value)} /></div>
          <div className="field-label">熟悉产品<SelectInput value={kycValue("product_knowledge")} options={["未填写", "仅股票/ETF", "股票+基金", "股票+期权", "股票+债券+基金", "复杂衍生品"]} onChange={(value) => setKyc("product_knowledge", value)} /></div>
          <div className="field-label">产品知识确认<SelectInput value={kycValue("knowledge_confirmation")} options={["未填写", "了解基础风险", "了解波动与亏损风险", "了解期权/杠杆风险", "需要进一步学习"]} onChange={(value) => setKyc("knowledge_confirmation", value)} /></div>
          <div className="field-label">可承受最大回撤<SelectInput value={kycValue("loss_tolerance")} options={["未填写", "5%以内", "5%-10%", "10%-20%", "20%-35%", "35%以上"]} onChange={(value) => setKyc("loss_tolerance", value)} /></div>
          <div className="field-label">风险承受能力<SelectInput value={draft.risk_tolerance} options={["未填写", "保守", "稳健", "积极", "激进"]} onChange={(value) => setDraft({ ...draft, risk_tolerance: value })} /></div>
          <div className="field-label">投资期限<SelectInput value={draft.investment_horizon} options={["未填写", "3个月以内", "3-12个月", "1-3年", "3年以上"]} onChange={(value) => setDraft({ ...draft, investment_horizon: value })} /></div>
          <div className="field-label">流动性需求<input value={draft.liquidity_needs} onChange={(event) => setDraft({ ...draft, liquidity_needs: event.target.value })} placeholder="例如：保留 6 个月生活费" /></div>
          <div className="field-label">重大资金用途<input value={kycValue("major_expense_plan")} onChange={(event) => setKyc("major_expense_plan", event.target.value)} placeholder="例如：一年内购房/教育/创业支出" /></div>
          <div className="field-label">目标收益<input value={draft.target_return} onChange={(event) => setDraft({ ...draft, target_return: event.target.value })} placeholder="例如：年化 8%-12%" /></div>
          <div className="field-label">投资限制/禁忌<input value={kycValue("investment_restrictions")} onChange={(event) => setKyc("investment_restrictions", event.target.value)} placeholder="例如：不使用融资、不碰单腿期权" /></div>
          <div className="field-label wide">备注<textarea value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} placeholder="例如：未来一年可能有大额支出、不希望使用杠杆等" /></div>
          </div>
        </Tabs.TabPane>
      </Tabs>
    </Drawer>
  );
}

export function WorkflowFeatureCards({ runs, runningWorkflow, onGenerate }: { runs: AIWorkflowRun[]; runningWorkflow: string; onGenerate: (workflowType: AIWorkflowRun["workflow_type"]) => void }) {
  return (
    <section className="workflow-card-grid">
      {workflowCards.map((item) => {
        const history = runs.filter((run) => run.workflow_type === item.type);
        const latest = history[0];
        const activeRun = history.find((run) => run.status === "running" || run.status === "pending");
        const generating = Boolean(activeRun);
        return (
          <article className="workflow-feature-card" key={item.type}>
            <div>
              <h2>{item.title}</h2>
              <p>{latest?.output?.summary || item.subtitle}</p>
              <small>{latest ? `${workflowStatusLabel(latest.status)} · ${formatDate(latest.created_at)}` : "尚未生成"}</small>
            </div>
            <div className="workflow-card-actions">
              <Button type="primary" onClick={() => onGenerate(item.type)} disabled={Boolean(runningWorkflow) || generating} loading={generating || runningWorkflow === item.type}>
                生成报告
              </Button>
            </div>
          </article>
        );
      })}
    </section>
  );
}

export function WorkflowRunTable({ runs, onOpen, onDelete }: { runs: AIWorkflowRun[]; onOpen: (run: AIWorkflowRun) => void; onDelete: (run: AIWorkflowRun) => void | Promise<void> }) {
  const [statusFilter, setStatusFilter] = useState("all");
  const filteredRuns = runs.filter((run) => statusFilter === "all" || (statusFilter === "active" ? run.status === "running" || run.status === "pending" : run.status === statusFilter));
  const sortedRuns = [...filteredRuns].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  const workflowRunTable = useResizableTableColumns({
    workflow_label: 190,
    provider: 150,
    model: 190,
    created_at: 210,
    status: 130,
    actions: 240,
  });
  return (
    <section className="workflow-run-table-panel">
      <div className="workflow-section-heading">
        <div>
          <h2>报告任务记录</h2>
          <small>{runs.length ? `${sortedRuns.length}/${runs.length} 条任务` : "暂无报告任务"}</small>
        </div>
        <Select value={statusFilter} onChange={(value) => setStatusFilter(String(value))} className="workflow-status-filter">
          <Select.Option value="all">全部状态</Select.Option>
          <Select.Option value="active">运行中</Select.Option>
          <Select.Option value="completed">完成</Select.Option>
          <Select.Option value="failed">失败</Select.Option>
          <Select.Option value="cancelled">已终止</Select.Option>
        </Select>
      </div>
      {sortedRuns.length ? (
        <Table
          className="arco-data-table pro-table workflow-run-arco-table"
          rowKey="run_id"
          data={sortedRuns}
          size="middle"
          hover
          tableLayoutFixed
          showSorterTooltip
          components={workflowRunTable.components}
          border={{ wrapper: true, headerCell: false, bodyCell: false }}
          pagination={{
            pageSize: 8,
            sizeCanChange: true,
            sizeOptions: [8, 16, 32],
            showTotal: (total, range) => `第 ${range[0]}-${Math.min(range[1], total)} 条 / 共 ${total} 条`,
            pageSizeChangeResetCurrent: true,
          }}
          scroll={{ x: workflowRunTable.totalTableWidth }}
          columns={[
            {
              title: "报告类别",
              dataIndex: "workflow_label",
              ...workflowRunTable.columnProps("workflow_label"),
              sorter: (a: AIWorkflowRun, b: AIWorkflowRun) => a.workflow_label.localeCompare(b.workflow_label),
              render: (_value, run: AIWorkflowRun) => (
                <span className="table-main-cell">
                  <strong>{run.workflow_label}</strong>
                </span>
              ),
            },
            { title: "提供方", dataIndex: "provider", ...workflowRunTable.columnProps("provider"), sorter: (a: AIWorkflowRun, b: AIWorkflowRun) => a.provider.localeCompare(b.provider) },
            { title: "模型", dataIndex: "model", ...workflowRunTable.columnProps("model"), sorter: (a: AIWorkflowRun, b: AIWorkflowRun) => a.model.localeCompare(b.model) },
            { title: "生成时间", dataIndex: "created_at", ...workflowRunTable.columnProps("created_at"), sorter: (a: AIWorkflowRun, b: AIWorkflowRun) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(), render: (value: string) => formatDate(value) },
            { title: "状态", dataIndex: "status", ...workflowRunTable.columnProps("status"), filters: ["pending", "running", "completed", "failed", "cancelled"].map((item) => ({ text: workflowStatusLabel(item as AIWorkflowRun["status"]), value: item })), onFilter: (value, row: AIWorkflowRun) => row.status === value, render: (value: AIWorkflowRun["status"]) => <Tag color={value === "completed" ? "green" : value === "failed" ? "red" : value === "cancelled" ? "gray" : "orange"}>{workflowStatusLabel(value)}</Tag> },
            {
              title: "操作",
              ...workflowRunTable.staticColumnProps("actions"),
              align: "center",
              className: "table-operation-column",
              render: (_value, run: AIWorkflowRun) => {
                const canDownload = Boolean(run.output?.markdown || run.output?.partial_markdown);
                return (
                  <div className="row-actions">
                    <Button type="primary" size="small" onClick={() => onOpen(run)}>查看</Button>
                    <Button size="small" disabled={!canDownload} href={canDownload ? api.profileWorkflowDownloadUrl(run.run_id) : undefined}>下载</Button>
                    <Button size="small" onClick={() => onDelete(run)}>删除</Button>
                  </div>
                );
              },
            },
          ]}
        />
      ) : <p className="reason">生成报告后，这里会集中展示所有报告任务。</p>}
    </section>
  );
}

export function WorkflowWindow({ run, text, artifacts, statusText, onClose, onRetry, onCancel }: { run: AIWorkflowRun; text: string; artifacts: WorkflowArtifact[]; statusText: string; onClose: () => void; onRetry: () => void; onCancel: () => void }) {
  return (
    <Modal
      className="workflow-modal"
      visible
      title={run.workflow_label}
      footer={null}
      onCancel={onClose}
      style={{ width: "min(1320px, calc(100vw - 32px))" }}
    >
      <WorkflowPanel run={run} text={text} artifacts={artifacts} statusText={statusText} onClose={onClose} onRetry={onRetry} onCancel={onCancel} />
    </Modal>
  );
}

export function WorkflowPanel({ run, text, artifacts, statusText, onRetry }: { run: AIWorkflowRun; text: string; artifacts: WorkflowArtifact[]; statusText: string; onClose?: () => void; onRetry?: () => void; onCancel?: () => void; onOpen?: () => void }) {
  const displaySteps = stepsForDisplay(run);
  const phase = getWorkflowPhase(run, displaySteps, artifacts, text);
  const progress = getWorkflowProgress(phase, displaySteps, artifacts, text, run.workflow_type);
  const expectation = getWorkflowExpectation(phase, run, progress, statusText);
  const qualityIssues = getWorkflowQualityIssues(run);
  const isTerminalProblem = phase === "failed" || phase === "cancelled";
  const canShowReport = phase === "completed" || Boolean(text.trim());
  const reportSections = getReportSections(text);
  const reportHighlights = getReportHighlights(text);
  return (
    <section className="panel workflow-panel">
      <WorkflowTopBar
        run={run}
        phase={phase}
        progress={progress}
        expectation={expectation}
      />
      <div className="workflow-workbench">
        <aside className="workflow-side-rail">
          <WorkflowPhaseTimeline phase={phase} steps={displaySteps} artifacts={artifacts} text={text} />
          <WorkflowArtifactStatus artifacts={artifacts} />
          <WorkflowReportNav sections={reportSections} />
          <WorkflowExecutionDetails steps={displaySteps} />
        </aside>
        <WorkflowReportReader
          run={run}
          text={text}
          artifacts={artifacts}
          qualityIssues={qualityIssues}
          isTerminalProblem={isTerminalProblem}
          canShowReport={canShowReport}
          statusText={statusText}
          onRetry={onRetry}
          highlights={reportHighlights}
        />
      </div>
    </section>
  );
}

export function WorkflowTopBar({ run, phase, progress, expectation }: { run: AIWorkflowRun; phase: WorkflowPhase; progress: number; expectation: WorkflowExpectation }) {
  return (
    <div className={`workflow-topbar ${phase}`}>
      <div className="workflow-topbar-main">
        <Tag color={phase === "completed" ? "green" : phase === "failed" ? "red" : phase === "cancelled" ? "gray" : "arcoblue"}>{getWorkflowStatusBadge(phase)}</Tag>
        <div>
          <h2>{expectation.title}</h2>
          <small>{run.workflow_label} · {run.provider} · {run.model} · {formatDate(run.created_at)}</small>
        </div>
      </div>
      <div className="workflow-topbar-progress" aria-label={`报告生成进度 ${progress}%`}>
        <strong>{progress}%</strong>
        <div className="workflow-progress-track"><i style={{ width: `${progress}%` }} /></div>
        <small>{expectation.timeHint}</small>
      </div>
    </div>
  );
}

export function WorkflowReportReader({ run, text, artifacts, qualityIssues, isTerminalProblem, canShowReport, statusText, onRetry, highlights }: { run: AIWorkflowRun; text: string; artifacts: WorkflowArtifact[]; qualityIssues: string[]; isTerminalProblem: boolean; canShowReport: boolean; statusText: string; onRetry?: () => void; highlights: string[] }) {
  return (
    <main className="workflow-report-reader">
      {isTerminalProblem ? (
        <WorkflowTerminalState run={run} statusText={statusText} onRetry={onRetry} />
      ) : (
        <>
          <WorkflowReportSummary highlights={highlights} run={run} />
          {qualityIssues.length ? <WorkflowQualityIssues issues={qualityIssues} /> : null}
          <section className="workflow-report-section">
            <div className="workflow-section-heading">
              <h2>图表</h2>
              <small>{getArtifactProgressLabel(artifacts)}</small>
            </div>
            {artifacts.length ? <WorkflowArtifacts artifacts={artifacts} /> : <WorkflowArtifactPlaceholder />}
          </section>
          <section className="workflow-report-section workflow-reading-section">
            <div className="workflow-section-heading">
              <h2>报告正文</h2>
              <small>{run.status === "running" ? "正在逐段生成" : "已按原始报告结构展示"}</small>
            </div>
            {canShowReport ? <><MarkdownReport text={text} />{run.status === "running" ? <p className="streaming-note"><Spinner />正在继续生成...</p> : null}</> : <WorkflowSkeletonReport workflowType={run.workflow_type} />}
          </section>
        </>
      )}
    </main>
  );
}

export function WorkflowReportSummary({ highlights, run }: { highlights: string[]; run: AIWorkflowRun }) {
  return (
    <section className="workflow-report-summary">
      <div>
        <span className="workflow-progress-kicker">优先看这里</span>
        <h2>{run.status === "completed" ? "结论摘要" : "已生成内容摘要"}</h2>
      </div>
      {highlights.length ? (
        <ul>
          {highlights.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <p className="reason">报告正文出现后，会自动提取关键判断和建议关注点。</p>
      )}
    </section>
  );
}

export function WorkflowTerminalState({ run, statusText, onRetry }: { run: AIWorkflowRun; statusText: string; onRetry?: () => void }) {
  const cancelled = run.status === "cancelled";
  return (
    <div className={`workflow-terminal-state ${cancelled ? "cancelled" : "failed"}`}>
      <Tag color={cancelled ? "gray" : "red"}>{cancelled ? "已终止" : "生成失败"}</Tag>
      <h2>{cancelled ? "本次报告已终止" : "本次报告未生成成功"}</h2>
      <p>{cancelled ? "已终止，本次生成不会继续。可以关闭窗口，或重新发起一次报告生成。" : run.error_message || statusText || "生成过程遇到问题，未保存完整报告。"}</p>
      {onRetry ? <Button type="primary" onClick={onRetry}>重新生成</Button> : null}
    </div>
  );
}

export function WorkflowQualityIssues({ issues }: { issues: string[] }) {
  return (
    <div className="workflow-quality-issues">
      <div>
        <strong>需要复核的数据口径</strong>
        <small>报告已保存，以下项目建议阅读时留意。</small>
      </div>
      <ul>
        {issues.slice(0, 3).map((issue) => <li key={issue}>{issue}</li>)}
      </ul>
      {issues.length > 3 ? <small>另有 {issues.length - 3} 条，可在执行明细中继续排查。</small> : null}
    </div>
  );
}

type WorkflowPhase = "prepare" | "analyze" | "chart" | "write" | "validate" | "completed" | "failed" | "cancelled";

type WorkflowExpectation = {
  title: string;
  message: string;
  timeHint: string;
  next: string;
  closeHint: string;
};

const workflowPhaseItems: Array<{ key: WorkflowPhase; label: string }> = [
  { key: "prepare", label: "准备数据" },
  { key: "analyze", label: "分析数据" },
  { key: "chart", label: "生成图表" },
  { key: "write", label: "撰写报告" },
  { key: "validate", label: "校验保存" },
];

const expectedArtifactCount = 4;

export function getWorkflowPhase(run: AIWorkflowRun, steps: WorkflowStep[], artifacts: WorkflowArtifact[], text: string): WorkflowPhase {
  if (run.status === "cancelled") return "cancelled";
  if (run.status === "failed") return "failed";
  if (run.status === "completed") return "completed";
  const hasText = text.trim().length > 0;
  const activeStep = steps.find((step) => step.status === "running");
  const activeText = `${activeStep?.title ?? ""} ${activeStep?.detail ?? ""} ${activeStep?.tool_name ?? ""} ${activeStep?.action_label ?? ""}`;
  if (/validate|校验|保存/.test(activeText)) return "validate";
  if (hasText) return "write";
  if (artifacts.length > 0 || /图表|分布|calculate|metrics|allocation|exposure/.test(activeText)) return "chart";
  if (steps.some((step) => step.status === "completed") || /工具|查询|持仓|账户|行情|K线|Agent/.test(activeText)) return "analyze";
  return "prepare";
}

export function getWorkflowProgress(phase: WorkflowPhase, steps: WorkflowStep[], artifacts: WorkflowArtifact[], text: string, workflowType: AIWorkflowRun["workflow_type"]): number {
  if (phase === "completed") return 100;
  if (phase === "failed" || phase === "cancelled") return 0;
  const completedStepCount = steps.filter((step) => step.status === "completed").length;
  const stepProgress = Math.min(22, Math.round((completedStepCount / Math.max(steps.length, 10)) * 22));
  const expectedChapterCount = workflowSkeletonSections[workflowType]?.length || 6;
  const completedChapterCount = steps.filter((step) => step.tool_name?.startsWith("generate_chapter_") && step.status === "completed").length;
  if (phase === "prepare") return Math.max(6, stepProgress);
  if (phase === "analyze") return Math.max(14, 14 + stepProgress);
  if (phase === "chart") return Math.min(56, 40 + artifacts.length * 4);
  if (phase === "write") return Math.min(90, 60 + Math.round((completedChapterCount / expectedChapterCount) * 30));
  if (phase === "validate") return 94;
  return 8;
}

export function getWorkflowExpectation(phase: WorkflowPhase, run: AIWorkflowRun, progress: number, statusText: string): WorkflowExpectation {
  const closeHint = "关闭窗口不影响生成，完成后可在历史报告查看。";
  const normalizedStatusText = formatWorkflowStatusText(statusText);
  if (phase === "failed") {
    return {
      title: "生成失败",
      message: run.error_message || normalizedStatusText || "生成过程遇到问题，已保留当前进度。",
      timeHint: "可以重新生成",
      next: "检查失败原因后，可重新发起报告生成。",
      closeHint: "已完成的历史报告不会受影响。",
    };
  }
  if (phase === "cancelled") {
    return {
      title: "已终止生成",
      message: "已终止，本次生成不会继续。",
      timeHint: "已停止",
      next: "可以关闭窗口，或重新发起报告生成。",
      closeHint: "关闭窗口不会恢复本次任务。",
    };
  }
  if (phase === "completed") {
    return {
      title: "报告已保存",
      message: "报告、图表和执行记录已保存，可随时从历史报告查看。",
      timeHint: `保存于 ${formatDate(run.updated_at || run.created_at)}`,
      next: "可以关闭窗口或切换查看历史报告。",
      closeHint: "关闭窗口不会丢失报告。",
    };
  }
  if (phase === "prepare") {
    return { title: "正在准备数据", message: normalizedStatusText || "正在创建任务并连接流式通道。", timeHint: "预计还需 40-90 秒", next: "下一步会读取账户、持仓和偏好数据。", closeHint };
  }
  if (phase === "analyze") {
    return { title: "正在分析数据", message: normalizedStatusText || "正在读取账户、持仓、偏好和行情数据。", timeHint: "预计还需 30-70 秒", next: "随后会生成报告所需的结构化图表。", closeHint };
  }
  if (phase === "chart") {
    return { title: "正在生成图表", message: normalizedStatusText || "正在整理报告所需的分布、贡献和风险图表。", timeHint: "预计还需 20-50 秒", next: "图表准备后会开始组织报告正文。", closeHint };
  }
  if (phase === "validate") {
    return { title: "正在校验保存", message: normalizedStatusText || "正在检查报告口径、风险提示和缺失数据说明。", timeHint: "预计还需 10-20 秒", next: "完成后会保存报告，并单独标注质量问题。", closeHint };
  }
  return { title: "正在撰写报告", message: normalizedStatusText || "正在把数据、图表和观察结果组织成结构化报告。", timeHint: progress >= 86 ? "预计还需 10-25 秒" : "预计还需 20-40 秒", next: "正文会继续逐段出现，完成后自动保存。", closeHint };
}

export function WorkflowProgressHeader({ phase, progress, expectation }: { phase: WorkflowPhase; progress: number; expectation: WorkflowExpectation }) {
  const phaseIndex = workflowPhaseItems.findIndex((item) => item.key === phase);
  const phaseLabel = phaseIndex >= 0 ? `第 ${phaseIndex + 1}/${workflowPhaseItems.length} 阶段` : "生成状态";
  return (
    <div className={`workflow-progress-card ${phase}`}>
      <div className="workflow-progress-copy">
        <span className="workflow-progress-kicker">{phase === "completed" ? "已完成" : phase === "failed" ? "需要处理" : "生成中"}</span>
        <h3>{expectation.title}</h3>
        <p>{expectation.message}</p>
        <small>{expectation.next}</small>
      </div>
      <div className="workflow-progress-side">
        <strong>{phase === "completed" ? "已完成" : phaseLabel}</strong>
        <div className="workflow-progress-track"><i style={{ width: `${progress}%` }} /></div>
        <small>{phase === "completed" ? expectation.timeHint : `${expectation.timeHint} · 阶段进度`}</small>
      </div>
      <div className="workflow-close-hint">{expectation.closeHint}</div>
    </div>
  );
}

export function WorkflowPhaseTimeline({ phase, steps, artifacts, text }: { phase: WorkflowPhase; steps: WorkflowStep[]; artifacts: WorkflowArtifact[]; text: string }) {
  const timelinePhase = phase === "failed" || phase === "cancelled" ? getLastKnownWorkflowPhase(steps, artifacts, text) : phase;
  const activeIndex = workflowPhaseItems.findIndex((item) => item.key === timelinePhase);
  return (
    <div className="workflow-phase-panel">
      <div className="workflow-section-heading">
        <h2>生成进度</h2>
      </div>
      <div className="workflow-phase-timeline">
        {workflowPhaseItems.map((item, index) => {
          const status = phase === "completed" || index < activeIndex ? "completed" : index === activeIndex ? phase === "failed" || phase === "cancelled" ? "failed" : "running" : "pending";
          return (
            <div className={`workflow-phase ${status}`} key={item.key}>
              <i aria-hidden="true" />
              <span>{status === "completed" ? "完成" : status === "running" ? "进行中" : status === "failed" ? "中断" : "等待"}</span>
              <strong>{item.label}</strong>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function getLastKnownWorkflowPhase(steps: WorkflowStep[], artifacts: WorkflowArtifact[], text: string): WorkflowPhase {
  if (text.trim()) return "write";
  if (artifacts.length) return "chart";
  if (steps.some((step) => step.status === "completed")) return "analyze";
  return "prepare";
}

export function WorkflowArtifactStatus({ artifacts }: { artifacts: WorkflowArtifact[] }) {
  return (
    <div className="workflow-artifact-status">
      <div className="workflow-section-heading">
        <h2>已生成资产</h2>
        <small>{artifacts.length ? `${artifacts.length}/${expectedArtifactCount} 个图表` : "等待图表"}</small>
      </div>
      <div className="workflow-asset-list">
        {artifacts.length ? artifacts.slice(0, expectedArtifactCount).map((artifact) => (
          <span className="ready" key={artifact.artifact_id}>{artifact.title}</span>
        )) : (
          <>
            <span className="pending">分布图表</span>
            <span className="pending">集中度图表</span>
            <span className="pending">贡献图表</span>
            <span className="pending">风险图表</span>
          </>
        )}
      </div>
    </div>
  );
}

export function WorkflowReportNav({ sections }: { sections: ReportSection[] }) {
  return (
    <nav className="workflow-report-nav" aria-label="报告章节">
      <div className="workflow-section-heading">
        <h2>报告目录</h2>
        <small>{sections.length ? `${sections.length} 个章节` : "正文生成后出现"}</small>
      </div>
      {sections.length ? (
        <div className="workflow-report-nav-list">
          {sections.map((section) => <a className={`level-${section.level}`} href={`#${section.id}`} key={section.id}><span>{section.number}</span>{section.title}</a>)}
        </div>
      ) : <p className="reason">还没有可跳转的章节。</p>}
    </nav>
  );
}

export function getWorkflowQualityIssues(run: AIWorkflowRun): string[] {
  const output = run.output ?? {};
  if (Array.isArray(output.quality_issues)) return output.quality_issues.filter((issue): issue is string => typeof issue === "string" && issue.trim().length > 0);
  const validation = output.validation_result;
  const issues = validation && Array.isArray(validation.issues) ? validation.issues : [];
  return issues.filter((issue): issue is string => typeof issue === "string" && issue.trim().length > 0);
}

export function WorkflowExecutionDetails({ steps }: { steps: WorkflowStep[] }) {
  const [open, setOpen] = useState(false);
  const runningStep = steps.find((step) => step.status === "running");
  return (
    <div className="workflow-details">
      <Button className="workflow-details-toggle" onClick={() => setOpen((value) => !value)}>
        {open ? "收起执行明细" : "查看执行明细"}
        <small>{runningStep ? getStepUserHint(runningStep) : `${steps.filter((step) => step.status === "completed").length}/${steps.length || 0} 步已完成`}</small>
      </Button>
      {open ? (
        <div className="workflow-steps">
          {steps.length ? steps.map((step) => (
            <div className={`workflow-step ${step.status}`} key={step.step_no}>
              <span className="step-status-badge">
                {step.status === "completed" ? "已完成" : step.status === "running" ? <><Spinner />运行中</> : step.status === "failed" ? "失败" : "等待"}
              </span>
              <div>
                <strong>{getWorkflowStepLabel(step)}</strong>
                <p>{step.status === "running" ? getStepUserHint(step) : step.detail}</p>
                {step.agent_note ? <small className="agent-note">Agent：{step.agent_note}</small> : null}
                {step.expected_observation ? <small>期望：{step.expected_observation}</small> : null}
                {step.observation ? <small>观察：{summarizeObservation(step.observation)}</small> : null}
                <small>{formatWorkflowStatusText(getStepUserHint(step))}</small>
              </div>
            </div>
          )) : <p className="reason">等待 Agent 规划与工具调用事件...</p>}
        </div>
      ) : null}
    </div>
  );
}

export function getWorkflowStepLabel(step: WorkflowStep): string {
  if (step.action_type === "agent_thought") return "正在判断下一步";
  const chapterMatch = (step.tool_name || step.action_label || "").match(/generate_chapter_(\d+)/);
  if (chapterMatch) return `撰写第 ${chapterMatch[1]} 章`;
  const source = `${step.title} ${step.detail} ${step.tool_name ?? ""} ${step.action_label}`;
  if (/read_skill_doc|技能|框架/.test(source)) return "确认分析框架";
  if (/portfolio|账户|持仓|context|exposure/.test(source)) return "读取组合数据";
  if (/quote|行情|K线|kline/.test(source)) return "补充行情数据";
  if (/audit_calculation_pack|AI 审计|审计/.test(source)) return "复核计算结果";
  if (/calculate_audit_pack|整理计算包|audit pack/.test(source)) return "整理报告数据";
  if (/calculate|metrics|allocation|distribution/.test(source)) return "计算核心指标";
  if (/图表|chart/.test(source)) return "生成报告图表";
  if (/finalize|report|报告/.test(source)) return "开始撰写报告";
  return formatWorkflowStatusText(step.title);
}

export function WorkflowSkeletonReport({ workflowType }: { workflowType: AIWorkflowRun["workflow_type"] }) {
  const sections = workflowSkeletonSections[workflowType] ?? [];
  return (
    <div className="workflow-skeleton-report">
      {sections.length ? sections.map((title) => (
        <div className="workflow-skeleton-block" key={title}>
          <strong>{title}</strong>
          <span />
          <span />
        </div>
      )) : <p className="reason">正在根据技能模板确认报告章节。</p>}
      <p><Spinner />正在组织报告正文，内容生成后会逐段出现。</p>
    </div>
  );
}

export function getArtifactProgressLabel(artifacts: WorkflowArtifact[]): string {
  if (!artifacts.length) return "等待图表生成";
  if (artifacts.length >= expectedArtifactCount) return "图表已准备，正在组织报告正文";
  return `已生成 ${artifacts.length}/${expectedArtifactCount}`;
}

export function getRunningStepHint(steps: WorkflowStep[], artifacts: WorkflowArtifact[], text: string): string {
  const runningStep = steps.find((step) => step.status === "running");
  if (runningStep) return getStepUserHint(runningStep);
  if (text.trim()) return "报告正文正在逐段生成。";
  if (artifacts.length) return "图表已开始生成，报告正文随后出现。";
  return "正在等待下一步执行事件。";
}

export function getStepUserHint(step: WorkflowStep): string {
  const source = `${step.title} ${step.detail} ${step.tool_name ?? ""} ${step.action_label}`;
  if (/read_skill_doc|技能|框架/.test(source)) return "正在确认报告结构和分析规则。";
  if (/portfolio|账户|持仓|context|exposure/.test(source)) return "正在读取账户、持仓和口径数据，用于生成报告基础分析。";
  if (/quote|行情|K线|kline/.test(source)) return "正在补充行情和趋势数据，让结论更贴近最新状态。";
  if (/audit_calculation_pack|AI 审计|审计/.test(source)) return "AI 正在复核计算包，异常会标注但不会拖垮整份报告。";
  if (/calculate_audit_pack|整理计算包|audit pack/.test(source)) return "正在整理可审计计算包，报告数字会以它为准。";
  if (/generate_chapter|生成第/.test(source)) return "正在生成当前章节，若超时会局部降级并继续后续章节。";
  if (/calculate|metrics|allocation|distribution|图表|分布/.test(source)) return "正在计算报告分布和关键指标，稍后会先生成图表。";
  if (/finalize|report|报告/.test(source)) return "数据已经准备好，正在组织报告正文。";
  if (/Agent|思考/.test(source)) return "Agent 正在根据已获得的数据决定下一步。";
  return step.detail || "正在执行当前步骤。";
}

export function formatWorkflowStatusText(text: string): string {
  return text
    .replace(/分析持仓/g, "分析数据")
    .replace(/查询画像上下文/g, "查询报告上下文")
    .replace(/组合风险/g, "报告指标")
    .replace(/持仓诊断/g, "报告分析");
}

export function upsertWorkflowStep(items: WorkflowStep[], step: WorkflowStep): WorkflowStep[] {
  const index = items.findIndex((item) => item.step_no === step.step_no);
  const next = index >= 0 ? items.map((item) => item.step_no === step.step_no ? { ...item, ...step } : item) : [...items, step];
  return next.sort((a, b) => a.step_no - b.step_no);
}

export function stepsForDisplay(run: AIWorkflowRun): WorkflowStep[] {
  if (run.steps?.length) return run.steps;
  const trace = run.output?.tool_trace ?? [];
  return trace.map((item, index) => {
    const toolName = String(item.tool_name || item.tool || "agent_tool");
    const observation = item.observation && typeof item.observation === "object" ? item.observation as Record<string, unknown> : undefined;
    return {
      step_no: Number(item.turn || index + 1),
      title: `调用工具：${toolName}`,
      detail: "历史工具调用记录",
      action_type: "tool",
      action_label: toolName,
      status: "completed",
      artifact_ids: [],
      tool_name: toolName,
      tool_args: item.tool_args && typeof item.tool_args === "object" ? item.tool_args as Record<string, unknown> : undefined,
      observation,
      agent_note: "已从历史 tool_trace 还原",
    };
  });
}

export function summarizeObservation(observation: Record<string, unknown>): string {
  const status = typeof observation.status === "string" ? observation.status : "";
  const error = typeof observation.error === "string" ? observation.error : "";
  const message = typeof observation.message === "string" ? observation.message : "";
  const itemCount = typeof observation.item_count === "number" ? `${observation.item_count} 条记录` : "";
  const artifactCount = Array.isArray(observation.artifacts) ? `${observation.artifacts.length} 个图表` : "";
  const keys = Object.keys(observation).filter((key) => !["status", "error", "message", "items", "artifacts"].includes(key)).slice(0, 4).join("、");
  return [status, error || message, itemCount, artifactCount, keys].filter(Boolean).join(" · ") || "已返回结构化结果";
}

export function createPendingWorkflowRun(workflowType: AIWorkflowRun["workflow_type"], accountId: string): AIWorkflowRun {
  const now = new Date().toISOString();
  return {
    run_id: `pending_${workflowType}_${Date.now()}`,
    workflow_type: workflowType,
    workflow_label: workflowLabels[workflowType],
    account_id: accountId,
    question: workflowLabels[workflowType],
    status: "pending",
    steps: [
      { step_no: 1, title: "正在创建工作流", detail: "已收到请求，正在向后端登记任务", action_type: "create", action_label: "创建任务", status: "running", artifact_ids: [] },
      { step_no: 2, title: "等待流式连接", detail: "任务创建后会连接 SSE 通道并持续展示执行过程", action_type: "stream", action_label: "连接流式通道", status: "pending", artifact_ids: [] },
      { step_no: 3, title: "执行报告查询", detail: "查询账户、持仓、成交、画像偏好和行情摘要", action_type: "query", action_label: "执行脚本 - 查询报告上下文", status: "pending", artifact_ids: [] },
      { step_no: 4, title: "生成图表与报告", detail: "图表和报告正文会在这里逐步出现", action_type: "report", action_label: "流式生成", status: "pending", artifact_ids: [] },
    ],
    input_context: {},
    output: {},
    artifacts: [],
    provider: "local",
    model: "pending",
    data_version: "",
    error_message: "",
    created_at: now,
    updated_at: now,
  };
}

export function WorkflowArtifacts({ artifacts }: { artifacts: WorkflowArtifact[] }) {
  return (
    <div className="artifact-grid">
      {artifacts.map((artifact) => (
        <div className="artifact" key={artifact.artifact_id}>
          <div className="artifact-heading">
            <strong>{artifact.title}</strong>
            <small>Top {Math.min(8, artifact.data.length)}</small>
          </div>
          {artifact.data.slice(0, 8).map((item) => (
            <div className="bar-row" key={item.label}>
              <span>{item.label}</span>
              <div><i style={{ width: `${Math.min(100, Math.abs(item.value) * 100)}%` }} /></div>
              <small>{formatPercent(item.value)}</small>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function WorkflowArtifactPlaceholder() {
  return (
    <div className="workflow-artifact-placeholder">
      <Spinner />
      <strong>正在整理图表</strong>
      <small>账户、持仓和行情数据准备好后，会优先展示关键分布和风险图表。</small>
    </div>
  );
}

export function MarkdownReport({ text }: { text: string }) {
  const blocks = parseMarkdownBlocks(normalizeMarkdownText(text));
  const headingMeta = getReportHeadingMeta(text);
  let headingIndex = 0;
  return (
    <div className="markdown-report">
      {blocks.map((block, index) => {
        if (block.type === "h1") {
          const meta = headingMeta[headingIndex++] ?? fallbackHeadingMeta(block.content, headingIndex - 1);
          return <MarkdownHeading meta={meta} key={index} />;
        }
        if (block.type === "h2") {
          const meta = headingMeta[headingIndex++] ?? fallbackHeadingMeta(block.content, headingIndex - 1);
          return <MarkdownHeading meta={meta} key={index} />;
        }
        if (block.type === "h3") {
          const meta = headingMeta[headingIndex++] ?? fallbackHeadingMeta(block.content, headingIndex - 1);
          return <MarkdownHeading meta={meta} key={index} />;
        }
        if (block.type === "h4") {
          const meta = headingMeta[headingIndex++] ?? fallbackHeadingMeta(block.content, headingIndex - 1);
          return <MarkdownHeading meta={meta} key={index} />;
        }
        if (block.type === "list") return <ul className="markdown-list" key={index}>{block.items.map((item) => <li key={item}>{renderInlineMarkdown(item)}</li>)}</ul>;
        if (block.type === "ordered-list") return <ol className="markdown-ordered-list" key={index}>{block.items.map((item) => <li key={item}>{renderInlineMarkdown(item)}</li>)}</ol>;
        if (block.type === "quote") return <blockquote className="markdown-quote" key={index}>{block.items.map((item) => <p key={item}>{renderInlineMarkdown(item)}</p>)}</blockquote>;
        if (block.type === "hr") return <hr className="markdown-divider" key={index} />;
        if (block.type === "table") return <MarkdownTable key={index} rows={block.rows} />;
        return block.content ? <p className="markdown-paragraph" key={index}>{renderInlineMarkdown(block.content)}</p> : <br key={index} />;
      })}
    </div>
  );
}

export function MarkdownHeading({ meta }: { meta: ReportHeadingMeta }) {
  const className = `markdown-heading markdown-heading-level-${meta.level}`;
  const content = <><span className="markdown-heading-number">{meta.number}</span><span className="markdown-heading-text">{renderInlineMarkdown(meta.title)}</span></>;
  if (meta.level === 1) return <h2 id={meta.id} className={className}>{content}</h2>;
  if (meta.level === 2) return <h3 id={meta.id} className={className}>{content}</h3>;
  return <h4 id={meta.id} className={className}>{content}</h4>;
}

type MarkdownBlock =
  | { type: "h1" | "h2" | "h3" | "h4" | "p"; content: string }
  | { type: "list"; items: string[] }
  | { type: "ordered-list"; items: string[] }
  | { type: "quote"; items: string[] }
  | { type: "hr" }
  | { type: "table"; rows: string[][] };

type ReportSection = {
  id: string;
  title: string;
  level: 1 | 2 | 3 | 4;
  number: string;
};

type ReportHeadingMeta = ReportSection & {
  rawLevel: 1 | 2 | 3 | 4;
};

type MarkdownHeadingBlock = { type: "h1" | "h2" | "h3" | "h4"; content: string };

export function headingAnchor(index: number): string {
  return `report-section-${index}`;
}

export function getReportSections(text: string): ReportSection[] {
  return getReportHeadingMeta(text).filter((section) => section.level === 1);
}

export function getReportHeadingMeta(text: string): ReportHeadingMeta[] {
  const headingBlocks = parseMarkdownBlocks(normalizeMarkdownText(text)).filter((block): block is MarkdownHeadingBlock => block.type === "h1" || block.type === "h2" || block.type === "h3" || block.type === "h4");
  const baseLevel = headingBlocks.reduce<number>((min, block) => Math.min(min, Number(block.type.slice(1))), 4) as 1 | 2 | 3 | 4;
  const counters = [0, 0, 0, 0];
  return headingBlocks.map((block, index) => {
    const rawLevel = Number(block.type.slice(1)) as 1 | 2 | 3 | 4;
    const relativeLevel = Math.min(4, Math.max(1, rawLevel - baseLevel + 1)) as 1 | 2 | 3 | 4;
    counters[relativeLevel - 1] += 1;
    for (let cursor = relativeLevel; cursor < counters.length; cursor += 1) counters[cursor] = 0;
    for (let cursor = 0; cursor < relativeLevel - 1; cursor += 1) {
      if (!counters[cursor]) counters[cursor] = 1;
    }
    return {
      id: headingAnchor(index),
      title: stripHeadingNumber(block.content),
      level: relativeLevel,
      rawLevel,
      number: counters.slice(0, relativeLevel).join("."),
    };
  });
}

export function fallbackHeadingMeta(content: string, index: number): ReportHeadingMeta {
  return {
    id: headingAnchor(index),
    title: stripHeadingNumber(content),
    level: 1,
    rawLevel: 1,
    number: String(index + 1),
  };
}

export function stripHeadingNumber(value: string): string {
  return value
    .replace(/\*\*/g, "")
    .replace(/^\s*(?:第?[一二三四五六七八九十百]+[章节部分]?|[一二三四五六七八九十百]+|[0-9]+(?:\.[0-9]+)*)(?:[、.．:：\-\s]+)\s*/, "")
    .trim();
}

export function getReportHighlights(text: string): string[] {
  const blocks = parseMarkdownBlocks(normalizeMarkdownText(text));
  const prioritized: string[] = [];
  let inPrioritySection = false;
  for (const block of blocks) {
    if (block.type === "h1" || block.type === "h2" || block.type === "h3" || block.type === "h4") {
      inPrioritySection = /摘要|核心|结论|Agent|建议|关注|风险/.test(block.content);
      continue;
    }
    if (!inPrioritySection && prioritized.length >= 2) continue;
    const plain = markdownBlockToPlainText(block);
    if (plain.length >= 18 && !/^\|/.test(plain)) prioritized.push(trimHighlight(plain));
    if (prioritized.length >= 4) break;
  }
  return Array.from(new Set(prioritized)).slice(0, 4);
}

export function markdownBlockToPlainText(block: MarkdownBlock): string {
  if (block.type === "p") return block.content;
  if (block.type === "list" || block.type === "ordered-list") return block.items[0] ?? "";
  if (block.type === "quote") return block.items[0] ?? "";
  return "";
}

export function trimHighlight(value: string): string {
  const normalized = value.replace(/\*\*/g, "").replace(/`/g, "").replace(/\s+/g, " ").trim();
  return normalized.length > 140 ? `${normalized.slice(0, 138)}...` : normalized;
}

export function getWorkflowStatusBadge(phase: WorkflowPhase): string {
  if (phase === "completed") return "已保存";
  if (phase === "failed") return "生成失败";
  if (phase === "cancelled") return "已终止";
  return "生成中";
}

export function normalizeMarkdownText(text: string): string {
  let normalized = text.replace(/\\n/g, "\n").replace(/\\t/g, "\t");
  normalized = normalized.replace(/^```(?:markdown|md)?\s*$/gim, "").replace(/^```\s*$/gim, "");
  return normalized;
}

export function parseMarkdownBlocks(text: string): MarkdownBlock[] {
  const lines = text.split("\n");
  const blocks: MarkdownBlock[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }
    if (line.startsWith("# ")) {
      blocks.push({ type: "h1", content: line.slice(2).trim() });
      index += 1;
      continue;
    }
    if (line.startsWith("## ")) {
      blocks.push({ type: "h2", content: line.slice(3).trim() });
      index += 1;
      continue;
    }
    if (line.startsWith("### ")) {
      blocks.push({ type: "h3", content: line.slice(4).trim() });
      index += 1;
      continue;
    }
    if (line.startsWith("#### ")) {
      blocks.push({ type: "h4", content: line.slice(5).trim() });
      index += 1;
      continue;
    }
    if (/^-{3,}$/.test(line)) {
      blocks.push({ type: "hr" });
      index += 1;
      continue;
    }
    if (line.startsWith(">")) {
      const items: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        items.push(lines[index].trim().replace(/^>\s?/, "").trim());
        index += 1;
      }
      blocks.push({ type: "quote", items: items.filter(Boolean) });
      continue;
    }
    if (/^\*\*[^*]+[:：]?\*\*$/.test(line)) {
      blocks.push({ type: "h4", content: line.replace(/^\*\*/, "").replace(/\*\*$/, "").trim() });
      index += 1;
      continue;
    }
    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith("- ")) {
        items.push(lines[index].trim().slice(2).trim());
        index += 1;
      }
      blocks.push({ type: "list", items });
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, "").trim());
        index += 1;
      }
      blocks.push({ type: "ordered-list", items });
      continue;
    }
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        const raw = lines[index].trim();
        const cells = raw.split("|").slice(1, -1).map((cell) => cell.trim());
        const isSeparator = cells.every((cell) => /^:?-{3,}:?$/.test(cell));
        if (!isSeparator) rows.push(cells);
        index += 1;
      }
      blocks.push({ type: "table", rows });
      continue;
    }
    blocks.push({ type: "p", content: line });
    index += 1;
  }
  return blocks;
}

export function MarkdownTable({ rows }: { rows: string[][] }) {
  if (!rows.length) return null;
  const [head, ...body] = rows;
  return (
    <div className="markdown-table-wrap" data-row-count={body.length}>
      <table className="markdown-table">
        <thead><tr>{head.map((cell, index) => <th key={`${cell}-${index}`}>{renderInlineMarkdown(cell)}</th>)}</tr></thead>
        <tbody>
          {body.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{renderInlineMarkdown(cell)}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

export function renderInlineMarkdown(value: string) {
  const parts = value.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code className="markdown-inline-code" key={index}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <span key={index}>{part}</span>;
  });
}

export function Detail({ detail, selectedAccount, onSaveLayer, onGenerateAi, generatingAi, setDetail, setNotice }: { detail: { position: Position; account_positions?: Position[]; cards: DecisionCard[]; news: NewsItem[]; ai_analysis: AIAnalysis | null } | null; selectedAccount: string; onSaveLayer: (layer: string) => void; onGenerateAi: () => void; generatingAi: boolean; setDetail: (detail: { position: Position; account_positions?: Position[]; cards: DecisionCard[]; news: NewsItem[]; ai_analysis: AIAnalysis | null }) => void; setNotice: (notice: string) => void }) {
  const accountDistributionTable = useResizableTableColumns({
    account_id: 180,
    name: 180,
    quantity: 130,
    normalized_market_value: 170,
    position_weight: 130,
  });
  return (
    <div className="stack detail-grid">
      {!detail ? <Empty title="未选择标的" body="从持仓列表进入后查看完整分析。" /> : (
        <>
          <section className="panel detail-hero-panel">
            <div className="detail-hero-main">
              <div>
                <small className="detail-market-label">{marketName(detail.position.market)} · {detail.position.raw_currency || detail.position.normalized_currency}</small>
                <h2>{detail.position.name || detail.position.code}</h2>
                <span className="detail-code">{detail.position.code}</span>
              </div>
              <div className="detail-hero-actions">
                <Tag color={detail.position.profit_loss_ratio >= 0 ? "green" : "red"}>{detail.position.profit_loss_ratio >= 0 ? "盈利" : "亏损"}</Tag>
                <div className="detail-layer-field">
                  <span>仓位类型</span>
                  <Select value={detail.position.position_layer} onChange={(value) => onSaveLayer(String(value))} className="detail-layer-select">
                    {layers.slice(1).map((item) => <Select.Option key={item} value={item}>{item}</Select.Option>)}
                  </Select>
                </div>
              </div>
            </div>
            <div className="detail-stat-grid">
              <Metric label="当前价" value={formatPrice(detail.position.current_price)} />
              <Metric label="成本价" value={formatPrice(detail.position.average_cost)} />
              <Metric label="账户币种市值" value={formatMoney(detail.position.normalized_market_value, detail.position.normalized_currency)} />
              <Metric label="仓位" value={formatPercent(detail.position.position_weight)} />
              <Metric label="盈亏" value={formatPercent(detail.position.profit_loss_ratio)} />
            </div>
            <Descriptions
              className="detail-descriptions"
              column={3}
              data={[
                { label: "原始币种市值", value: formatMoney(detail.position.raw_market_value, detail.position.raw_currency) },
                { label: "账户数量", value: `${formatCount(detail.account_positions?.length || 1)} 个` },
                { label: "分层依据", value: detail.position.layer_source || "系统分层" },
              ]}
            />
            <p className="reason">{exchangeRateLabel(detail.position)}</p>
            {detail.position.missing_market_code ? <p className="warning">该持仓缺少真实证券代码，当前按简称展示，不自动拉取行情和新闻。</p> : null}
            <p className="reason">{detail.position.layer_reason}</p>
          </section>
          <KLineChart position={detail.position} accountId={selectedAccount} />
          <section className="panel detail-tabs-panel">
            <Tabs defaultActiveTab="ai">
              <Tabs.TabPane key="ai" title="AI分析">
                <AIAnalysisPanel
                  code={detail.position.code}
                  accountId={selectedAccount}
                  analysis={detail.ai_analysis}
                  onGenerate={onGenerateAi}
                  onGenerated={(aiAnalysis) => setDetail({ ...detail, ai_analysis: aiAnalysis })}
                  generating={generatingAi}
                  setNotice={setNotice}
                />
              </Tabs.TabPane>
              <Tabs.TabPane key="news" title="新闻">
                <NewsView items={detail.news} />
              </Tabs.TabPane>
              <Tabs.TabPane key="accounts" title="账户分布">
                <Table
                  className="arco-data-table pro-table"
                  rowKey={(item: Position) => `${item.account_id}-${item.code}`}
                  data={detail.account_positions ?? []}
                  size="middle"
                  hover
                  tableLayoutFixed
                  showSorterTooltip
                  components={accountDistributionTable.components}
                  border={{ wrapper: true, headerCell: false, bodyCell: false }}
                  pagination={false}
                  scroll={{ x: accountDistributionTable.totalTableWidth }}
                  columns={[
                    { title: "账户", dataIndex: "account_id", ...accountDistributionTable.columnProps("account_id"), sorter: (a: Position, b: Position) => a.account_id.localeCompare(b.account_id), render: (_value, item: Position) => <span className="table-main-cell"><strong>{item.account_id}</strong></span> },
                    { title: "标的", dataIndex: "name", ...accountDistributionTable.columnProps("name"), sorter: (a: Position, b: Position) => (a.name || a.code).localeCompare(b.name || b.code) },
                    { title: "数量", dataIndex: "quantity", ...accountDistributionTable.columnProps("quantity"), sorter: (a: Position, b: Position) => a.quantity - b.quantity, render: (value: number) => formatPrice(value) },
                    { title: "市值", dataIndex: "normalized_market_value", ...accountDistributionTable.columnProps("normalized_market_value"), sorter: (a: Position, b: Position) => a.normalized_market_value - b.normalized_market_value, render: (_value, item: Position) => formatMoney(item.normalized_market_value, item.normalized_currency) },
                    { title: "仓位", dataIndex: "position_weight", ...accountDistributionTable.columnProps("position_weight"), sorter: (a: Position, b: Position) => a.position_weight - b.position_weight, render: (value: number) => formatPercent(value) },
                  ]}
                />
              </Tabs.TabPane>
            </Tabs>
          </section>
        </>
      )}
    </div>
  );
}

const klinePeriods = [
  { label: "日 K", value: "K_DAY", count: 90 },
  { label: "周 K", value: "K_WEEK", count: 104 },
  { label: "月 K", value: "K_MON", count: 120 },
];

export function KLineChart({ position, accountId }: { position: Position; accountId: string }) {
  const [period, setPeriod] = useState(klinePeriods[0]);
  const [data, setData] = useState<KLineResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.positionKLine(position.code, accountId, period.value, period.count)
      .then((result) => {
        if (alive) setData(result);
      })
      .catch((error) => {
        if (alive) {
          setData({
            code: position.code,
            ktype: period.value,
            status: "missing",
            message: error instanceof Error ? error.message : "K 线数据获取失败",
            items: [],
          });
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [accountId, period, position.code]);

  const items = data?.items ?? [];
  const statusText = loading ? "加载中" : items.length ? `${items.length} 条` : "暂无数据";
  return (
    <section className="panel kline-panel">
      <div className="toolbar">
        <div>
          <h2>K 线行情</h2>
          <small>{position.code} · Futu / moomoo OpenD 历史 K 线</small>
        </div>
        <div className="inline-actions">
          {klinePeriods.map((item) => (
            <Button key={item.value} size="small" type={period.value === item.value ? "primary" : "secondary"} onClick={() => setPeriod(item)}>
              {item.label}
            </Button>
          ))}
          <Tag color={items.length ? "green" : "gray"}>{statusText}</Tag>
        </div>
      </div>
      {items.length ? <KLineSvg items={items} /> : <KLineEmpty loading={loading} message={data?.message} />}
    </section>
  );
}

function KLineSvg({ items }: { items: KLineItem[] }) {
  const width = 720;
  const height = 260;
  const left = 44;
  const right = 18;
  const top = 18;
  const priceHeight = 166;
  const volumeTop = 206;
  const volumeHeight = 36;
  const chartWidth = width - left - right;
  const highs = items.map((item) => item.high || item.close);
  const lows = items.map((item) => item.low || item.close);
  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const priceRange = Math.max(maxPrice - minPrice, maxPrice * 0.01, 1);
  const maxVolume = Math.max(...items.map((item) => item.volume), 1);
  const step = chartWidth / Math.max(items.length, 1);
  const bodyWidth = Math.max(3, Math.min(10, step * 0.58));
  const yForPrice = (price: number) => top + ((maxPrice - price) / priceRange) * priceHeight;
  const gridValues = [maxPrice, minPrice + priceRange * 0.5, minPrice];
  const last = items[items.length - 1];

  return (
    <div className="kline-chart-wrap">
      <svg className="kline-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="K 线行情图">
        {gridValues.map((value) => {
          const y = yForPrice(value);
          return (
            <g key={value}>
              <line className="kline-grid" x1={left} y1={y} x2={width - right} y2={y} />
              <text className="kline-axis-label" x={8} y={y + 4}>{formatPrice(value)}</text>
            </g>
          );
        })}
        <line className="kline-axis" x1={left} y1={top} x2={left} y2={volumeTop + volumeHeight} />
        <line className="kline-axis" x1={left} y1={volumeTop + volumeHeight} x2={width - right} y2={volumeTop + volumeHeight} />
        {items.map((item, index) => {
          const x = left + step * index + step / 2;
          const openY = yForPrice(item.open || item.close);
          const closeY = yForPrice(item.close);
          const highY = yForPrice(item.high || item.close);
          const lowY = yForPrice(item.low || item.close);
          const bodyY = Math.min(openY, closeY);
          const bodyHeight = Math.max(Math.abs(openY - closeY), 2);
          const up = item.close >= item.open;
          const volumeHeightValue = (item.volume / maxVolume) * volumeHeight;
          return (
            <g key={`${item.time_key}-${index}`} className={up ? "kline-candle kline-up" : "kline-candle kline-down"}>
              <line x1={x} y1={highY} x2={x} y2={lowY} />
              <rect x={x - bodyWidth / 2} y={bodyY} width={bodyWidth} height={bodyHeight} rx="1" />
              <rect className="kline-volume" x={x - bodyWidth / 2} y={volumeTop + volumeHeight - volumeHeightValue} width={bodyWidth} height={Math.max(volumeHeightValue, 1)} rx="1" />
            </g>
          );
        })}
        <text className="kline-date-label" x={left} y={height - 8}>{items[0]?.time_key?.slice(0, 10)}</text>
        <text className="kline-date-label" x={width - right} y={height - 8} textAnchor="end">{last?.time_key?.slice(0, 10)}</text>
      </svg>
      <div className="kline-summary">
        <span>最新收盘 {formatPrice(last.close)}</span>
        <span>区间高点 {formatPrice(maxPrice)}</span>
        <span>区间低点 {formatPrice(minPrice)}</span>
      </div>
    </div>
  );
}

function KLineEmpty({ loading, message }: { loading: boolean; message?: string }) {
  return (
    <div className="kline-empty-chart" aria-label="暂无 K 线数据">
      <svg viewBox="0 0 720 220" role="img">
        <line x1="40" y1="28" x2="40" y2="188" />
        <line x1="40" y1="188" x2="690" y2="188" />
        {[70, 120, 170, 220, 270, 320, 370, 420, 470, 520, 570, 620].map((x, index) => (
          <g key={x}>
            <line x1={x} y1={60 + (index % 4) * 14} x2={x} y2={144 + (index % 3) * 10} />
            <rect x={x - 5} y={88 + (index % 5) * 10} width="10" height={44 - (index % 3) * 6} rx="2" />
          </g>
        ))}
      </svg>
      <div>
        <strong>{loading ? "正在读取 K 线数据" : "暂无 K 线数据"}</strong>
        <small>{message || "富途暂未返回有效 K 线。请确认 OpenD 已连接且该标的有行情权限。"}</small>
      </div>
    </div>
  );
}

export function AIAnalysisPanel({ analysis, onGenerate, generating }: { code: string; accountId: string; analysis: AIAnalysis | null; onGenerate: () => void; onGenerated: (analysis: AIAnalysis) => void; generating: boolean; setNotice: (notice: string) => void }) {
  const output = analysis?.output;

  return (
    <section className="panel ai-panel">
      <div className="toolbar">
        <div>
          <h2>AI 辅助分析</h2>
          <small>{analysis ? `${providerName(analysis.provider)} · ${analysis.model} · ${analysis.status} · ${formatDate(analysis.created_at)}` : "基于当前持仓快照、仓位分层和消息面生成"}</small>
        </div>
        <div className="inline-actions">
          <Button type="primary" onClick={onGenerate} disabled={generating} loading={generating}>生成 AI 分析</Button>
        </div>
      </div>
      {!analysis ? (
        <p className="reason">尚未生成 AI 分析。配置大模型 API Key 后会调用外部模型；未配置时会使用本地结构化推理兜底。</p>
      ) : (
        <div className="ai-content">
          <div className="ai-callout">
            <span>{safeAIText(output?.recommendation, "观察")}</span>
            <p>{safeAIText(output?.conclusion, "暂无结论")}</p>
          </div>
          <Checklist title="理由" items={output?.reasons ?? []} />
          <Checklist title="风险" items={output?.risks ?? []} />
          <Checklist title="失效条件" items={output?.invalid_conditions ?? []} />
          <Checklist title="缺失数据" items={output?.missing_data ?? []} emptyText="无明显缺失" />
          {analysis.error_message ? <p className="warning">{analysis.error_message}</p> : null}
        </div>
      )}
    </section>
  );
}

function safeAIText(value: unknown, fallback: string): string {
  if (typeof value === "string") return value || fallback;
  if (Array.isArray(value)) return value.map((item: unknown): string => safeAIText(item, "")).filter(Boolean).join("；") || fallback;
  if (value && typeof value === "object") {
    const values: string[] = Object.values(value as Record<string, unknown>).map((item: unknown): string => safeAIText(item, "")).filter(Boolean);
    const applicable: string | undefined = values.find((item: string) => !item.startsWith("不适用") && item !== "无");
    return applicable || values[0] || fallback;
  }
  return value == null ? fallback : String(value);
}

export function Checklist({ title, items, emptyText = "暂无" }: { title: string; items: string[]; emptyText?: string }) {
  return (
    <div className="checklist">
      <strong>{title}</strong>
      {items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <small>{emptyText}</small>}
    </div>
  );
}

export function DataPage({ accounts, onImported, setNotice, requestConfirm, onRefresh, loading, showAccountManagementLink = true, onOpenAccounts }: { accounts: AccountSummary[]; onImported: () => Promise<void>; setNotice: (notice: string) => void; requestConfirm: (options: ConfirmOptions) => Promise<boolean>; onRefresh: () => Promise<void>; loading: boolean; showAccountManagementLink?: boolean; onOpenAccounts?: () => void }) {
  const enabledAccounts = accounts.filter((account) => account.enabled);
  const [activeAccountId, setActiveAccountId] = useState(enabledAccounts[0]?.account_id ?? "");
  const [overview, setOverview] = useState<AccountDataOverview | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [importing, setImporting] = useState(false);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);
  const [pullingDataType, setPullingDataType] = useState<string | null>(null);
  const [editingPosition, setEditingPosition] = useState<Position | null | "new">(null);
  const [editingDeal, setEditingDeal] = useState<AccountDeal | null | "new">(null);
  const [activeDataTab, setActiveDataTab] = useState("positions");
  const activeAccount = enabledAccounts.find((account) => account.account_id === activeAccountId) ?? enabledAccounts[0];
  const activeAccountConfigKey = activeAccount ? [
    activeAccount.account_id,
    activeAccount.import_modes?.join(",") || "",
    activeAccount.position_import_modes?.join(",") || "",
    activeAccount.review_import_modes?.join(",") || "",
    activeAccount.market_data_provider || "",
    activeAccount.news_data_provider || "",
    activeAccount.markets?.join(",") || "",
  ].join("|") : "";

  useEffect(() => {
    if (!activeAccountId && enabledAccounts[0]?.account_id) {
      setActiveAccountId(enabledAccounts[0].account_id);
    }
    if (activeAccountId && !enabledAccounts.some((account) => account.account_id === activeAccountId)) {
      setActiveAccountId(enabledAccounts[0]?.account_id ?? "");
    }
  }, [enabledAccounts, activeAccountId]);

  useEffect(() => {
    if (!activeAccountId) {
      setOverview(null);
      return;
    }
    api.accountDataOverview(activeAccountId)
      .then(setOverview)
      .catch((error) => setNotice(error instanceof Error ? error.message : "账户数据加载失败"));
  }, [activeAccountId, activeAccountConfigKey]);

  async function chooseImport(file: File | null) {
    if (!file || !activeAccountId) return;
    setImporting(true);
    setPreview(null);
    setNotice("正在校验 Excel 数据");
    try {
      const result = await api.importPreview("excel", file, activeAccountId);
      setPreview(result);
      if (result.errors?.length) {
        setNotice(`文件未导入：${result.errors[0]}`);
        return;
      }
      const parsed = [
        result.position_count ? `${formatCount(result.position_count)} 条持仓` : "",
        result.deal_count ? `${formatCount(result.deal_count)} 笔成交` : "",
      ].filter(Boolean).join("、");
      setNotice(parsed ? `已解析 ${parsed}` : "未识别到可导入记录");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "解析失败");
    } finally {
      setImporting(false);
    }
  }

  async function confirmImport() {
    if (!preview) return;
    if (preview.errors?.length) {
      setNotice("预览存在错误，不能确认导入");
      return;
    }
    setImporting(true);
    setNotice("正在写入账户数据");
    try {
      const result = await api.importConfirm(preview.source_name, preview);
      setNotice(`${result.status}：新增 ${result.inserted_count}，更新 ${result.updated_count}`);
      setPreview(null);
      await onImported();
      if (activeAccountId) setOverview(await api.accountDataOverview(activeAccountId));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "导入失败");
    } finally {
      setImporting(false);
    }
  }

  async function downloadTemplate() {
    setDownloadingTemplate(true);
    setNotice("正在下载 Excel 模板");
    try {
      await api.downloadImportTemplate(activeDataTab === "deals" ? "deal" : "position");
      setNotice("Excel 模板已开始下载");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Excel 模板下载失败");
    } finally {
      setDownloadingTemplate(false);
    }
  }

  async function refreshApiData() {
    if (!activeAccountId) return;
    await onRefresh();
    try {
      setOverview(await api.accountDataOverview(activeAccountId));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "账户数据刷新后加载失败");
    }
  }

  async function checkApiConnection(dataType: string, market?: string, provider?: string) {
    if (!activeAccountId) return;
    setNotice("正在检测 API 联通");
    try {
      const result = await api.checkAccountProvider(activeAccountId, { data_type: dataType, market, provider });
      setOverview((current) => current ? { ...current, provider_states: result.provider_states } : current);
      setOverview(await api.accountDataOverview(activeAccountId));
      setNotice(result.status === "not_configured" ? result.message : "API 联通状态已刷新");
    } catch (error) {
      const message = error instanceof Error ? error.message : "API 联通检测失败";
      setNotice(message.includes("Not Found") ? "后端尚未加载 API 检测接口，请重启本地服务后再试" : message);
    }
  }

  async function pullAccountData(dataType: string) {
    if (!activeAccountId) return;
    setPullingDataType(dataType);
    setNotice(dataType === "news" ? "正在拉取新闻数据" : "正在拉取行情数据");
    try {
      const result = await api.pullAccountMarketData(activeAccountId, { data_type: dataType });
      setOverview((current) => current ? { ...current, provider_states: result.provider_states } : current);
      setOverview(await api.accountDataOverview(activeAccountId));
      setNotice(result.message || "数据已拉取并缓存");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "数据拉取失败");
    } finally {
      setPullingDataType(null);
    }
  }

  async function deletePosition(position: Position) {
    const confirmed = await requestConfirm({
      title: "删除持仓",
      body: `确认删除持仓「${position.name || position.code}」？`,
      confirmText: "删除",
      cancelText: "取消",
      tone: "danger",
    });
    if (!confirmed) return;
    try {
      const result = await api.deleteAccountPosition(position.account_id, position.code, position.snapshot_time);
      setOverview(result.overview);
      setNotice("持仓已删除");
      await onImported();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "持仓删除失败");
    }
  }

  async function deleteDeal(deal: AccountDeal) {
    const confirmed = await requestConfirm({
      title: "删除成交",
      body: `确认删除成交「${deal.deal_id}」？`,
      confirmText: "删除",
      cancelText: "取消",
      tone: "danger",
    });
    if (!confirmed) return;
    try {
      const result = await api.deleteAccountDeal(deal.account_id, deal.deal_id);
      setOverview(result.overview);
      setNotice("成交已删除");
      await onImported();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "成交删除失败");
    }
  }

  if (!enabledAccounts.length) {
    return (
      <div className="stack data-console">
        <section className="panel">
          <Empty title="暂无可用账户" body={showAccountManagementLink ? "先在账户页创建并启用账户，再上传资产、持仓和成交数据。" : "先在上方账户列表创建并启用账户，再上传资产、持仓和成交数据。"} />
          {showAccountManagementLink && onOpenAccounts ? <Button type="primary" onClick={onOpenAccounts}>去创建账户</Button> : null}
        </section>
      </div>
    );
  }

  const activeImportModes = importModesForAccount(activeAccount);
  const canImportApi = activeImportModes.includes("api");
  const canImportLocal = activeImportModes.includes("local");

  return (
    <div className="data-console stack">
      <DataDetailTabs
        accounts={enabledAccounts}
        activeAccount={activeAccount}
        overview={overview}
        canImportApi={canImportApi}
        canImportLocal={canImportLocal}
        importing={importing}
        loading={loading}
        downloadingTemplate={downloadingTemplate}
        showAccountManagementLink={showAccountManagementLink}
        onOpenAccounts={onOpenAccounts}
        onDownloadTemplate={downloadTemplate}
        onChooseImport={chooseImport}
        onRefreshApiData={refreshApiData}
        onCheckApiConnection={checkApiConnection}
        onPullAccountData={pullAccountData}
        pullingDataType={pullingDataType}
        preview={preview}
        onConfirmImport={confirmImport}
        onSelectAccount={(accountId) => {
          setActiveAccountId(accountId);
          setPreview(null);
        }}
        onAddPosition={() => setEditingPosition("new")}
        onEditPosition={(position) => setEditingPosition(position)}
        onDeletePosition={deletePosition}
        onAddDeal={() => setEditingDeal("new")}
        onEditDeal={(deal) => setEditingDeal(deal)}
        onDeleteDeal={deleteDeal}
        activeDataTab={activeDataTab}
        onDataTabChange={setActiveDataTab}
      />
      {editingPosition ? (
        <PositionSnapshotModal
          account={activeAccount}
          position={editingPosition === "new" ? null : editingPosition}
          onClose={() => setEditingPosition(null)}
          setNotice={setNotice}
          onSaved={async (nextOverview) => {
            setOverview(nextOverview);
            setEditingPosition(null);
            setNotice("持仓快照已保存");
            await onImported();
          }}
        />
      ) : null}
      {editingDeal ? (
        <DealModal
          account={activeAccount}
          deal={editingDeal === "new" ? null : editingDeal}
          onClose={() => setEditingDeal(null)}
          setNotice={setNotice}
          onSaved={async (nextOverview) => {
            setOverview(nextOverview);
            setEditingDeal(null);
            setNotice("成交已保存");
            await onImported();
          }}
        />
      ) : null}
    </div>
  );
}

export function AccountFilterBar({ accounts, activeAccount, overview, showAccountManagementLink, onOpenAccounts, onSelect }: { accounts: AccountSummary[]; activeAccount: AccountSummary; overview: AccountDataOverview | null; showAccountManagementLink: boolean; onOpenAccounts?: () => void; onSelect: (accountId: string) => void }) {
  return (
    <section className="panel account-filter-bar">
      <div className="account-filter-main">
        <span className="section-kicker">当前账户</span>
        <StyledSelect
          className="account-filter-select"
          value={activeAccount.account_id}
          ariaLabel="选择账户"
          options={accounts.map((account) => ({ value: account.account_id, label: `${account.display_name || account.account_id} · ${account.base_currency}` }))}
          onChange={onSelect}
        />
      </div>
      <div className="account-filter-meta">
        <span><small>币种</small><strong>{activeAccount.base_currency}</strong></span>
        <span><small>持仓</small><strong>{formatCount(overview?.positions.length ?? 0)}</strong></span>
        <span><small>成交</small><strong>{formatCount(overview?.deals.length ?? 0)}</strong></span>
        {showAccountManagementLink && onOpenAccounts ? <Button onClick={onOpenAccounts}>管理账户</Button> : null}
      </div>
    </section>
  );
}

export function DataActions({ canImportApi, canImportLocal, importing, loading, downloadingTemplate, showAccountManagementLink, onOpenAccounts, onDownloadTemplate, onChooseImport, onRefreshApiData, label = "导入数据", importContext = "position" }: { canImportApi: boolean; canImportLocal: boolean; importing: boolean; loading: boolean; downloadingTemplate: boolean; showAccountManagementLink: boolean; onOpenAccounts?: () => void; onDownloadTemplate: () => Promise<void>; onChooseImport: (file: File | null) => Promise<void>; onRefreshApiData: () => Promise<void>; label?: string; importContext?: "position" | "deal" }) {
  const disabled = importing || loading || downloadingTemplate;
  const contextLabel = importContext === "position" ? "持仓" : "成交";
  const excelInputRef = useRef<HTMLInputElement | null>(null);
  const droplist = (
    <Menu>
      {canImportApi ? <Menu.Item key="api" onClick={onRefreshApiData}>API 刷新{contextLabel}数据</Menu.Item> : null}
      {canImportLocal ? (
        <>
          <Menu.Item key="excel" onClick={() => excelInputRef.current?.click()}>Excel 导入{contextLabel}数据</Menu.Item>
          <Menu.Item key="template" onClick={onDownloadTemplate}>模板下载</Menu.Item>
        </>
      ) : null}
      {!canImportApi && !canImportLocal && showAccountManagementLink && onOpenAccounts ? <Menu.Item key="config" onClick={onOpenAccounts}>配置导入方式</Menu.Item> : null}
    </Menu>
  );
  return (
    <>
      <input ref={excelInputRef} hidden type="file" accept=".xlsx" onChange={(event) => { const file = event.target.files?.[0] ?? null; event.target.value = ""; void onChooseImport(file); }} />
      <Dropdown droplist={droplist} trigger="click" disabled={disabled}>
        <Button loading={importing || loading || downloadingTemplate}>{label}</Button>
      </Dropdown>
    </>
  );
}

export function AccountRail({ accounts, activeAccountId, overview, onSelect }: { accounts: AccountSummary[]; activeAccountId: string; overview: AccountDataOverview | null; onSelect: (accountId: string) => void }) {
  return (
    <aside className="panel account-rail" aria-label="账户列表">
      <div className="account-rail-heading">
        <h2>账户</h2>
        <small>{formatCount(accounts.length)} 个启用账户</small>
      </div>
      <div className="account-rail-list">
        {accounts.map((account) => {
          const active = account.account_id === activeAccountId;
          const positionCount = active ? overview?.positions.length ?? 0 : null;
          const dealCount = active ? overview?.deals.length ?? 0 : null;
          return (
            <button
              className={`account-rail-item ${active ? "active" : ""}`}
              key={account.account_id}
              onClick={() => onSelect(account.account_id)}
              type="button"
            >
              <span className="account-rail-main">
                <strong>{account.display_name || account.account_id}</strong>
                <small><Tag color={accountSourceKind(account) === "futu" ? "blue" : "gray"}>{accountSourceLabel(account)}</Tag> · {account.base_currency}</small>
              </span>
              <span className="account-rail-assets">{formatMoney(account.display_total_assets ?? account.total_assets ?? 0, account.display_currency || account.base_currency)}</span>
              <span className="account-rail-meta">
                <small>{account.snapshot_time || account.last_sync_time ? formatDate(account.snapshot_time || account.last_sync_time) : "暂无同步"}</small>
                <small>{active ? `${formatCount(positionCount ?? 0)} 持仓 · ${formatCount(dealCount ?? 0)} 成交` : "选择后查看明细"}</small>
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

export function AccountOverviewHeader({ account, overview, showAccountManagementLink, onOpenAccounts }: { account: AccountSummary; overview: AccountDataOverview | null; showAccountManagementLink: boolean; onOpenAccounts?: () => void }) {
  const updatedAt = overview?.updated_at.account || account.snapshot_time || account.last_sync_time;
  return (
    <section className="panel account-overview-header">
      <div className="account-overview-title">
        <div>
          <span className="section-kicker">当前账户</span>
          <h2>{account.display_name || account.account_id}</h2>
          <small><Tag color={accountSourceKind(account) === "futu" ? "blue" : "gray"}>{accountSourceLabel(account)}</Tag> · {accountImportCapabilityLabel(account)} · 基准币种 {account.base_currency}</small>
        </div>
        <div className="account-overview-actions">
          <Tag color={account.enabled ? "green" : "gray"}>{account.enabled ? "启用" : "停用"}</Tag>
          {showAccountManagementLink && onOpenAccounts ? <Button onClick={onOpenAccounts}>管理账户</Button> : null}
        </div>
      </div>
      <div className="account-overview-strip">
        <span><small>最近更新</small><strong>{updatedAt ? formatDate(updatedAt) : "暂无刷新记录"}</strong></span>
        <span><small>持仓</small><strong>{formatCount(overview?.positions.length ?? 0)}</strong></span>
        <span><small>成交</small><strong>{formatCount(overview?.deals.length ?? 0)}</strong></span>
      </div>
    </section>
  );
}

export function DataUpdatePanel({ canImportApi, canImportLocal, importing, loading, downloadingTemplate, showAccountManagementLink, onOpenAccounts, onDownloadTemplate, onChooseImport, onRefreshApiData, preview, onConfirmImport }: { canImportApi: boolean; canImportLocal: boolean; importing: boolean; loading: boolean; downloadingTemplate: boolean; showAccountManagementLink: boolean; onOpenAccounts?: () => void; onDownloadTemplate: () => Promise<void>; onChooseImport: (file: File | null) => Promise<void>; onRefreshApiData: () => Promise<void>; preview: ImportPreview | null; onConfirmImport: () => Promise<void> }) {
  return (
    <section className="panel data-update-panel">
      <div className="toolbar data-update-toolbar">
        <div>
          <h2>数据更新</h2>
          <small>当前账户的数据入口；本地文件会先预览，确认后才写入。</small>
        </div>
        <div className="import-actions">
          {canImportApi ? <Button type="primary" onClick={onRefreshApiData} disabled={loading} loading={loading}>API 刷新</Button> : null}
          {canImportLocal ? (
            <>
              <Button onClick={onDownloadTemplate} disabled={downloadingTemplate} loading={downloadingTemplate}>模板下载</Button>
              <Upload
                showUploadList={false}
                accept=".xlsx"
                disabled={importing}
                beforeUpload={(file) => { onChooseImport(file as File); return false; }}
              >
                <Button disabled={importing} loading={importing}>Excel 导入</Button>
              </Upload>
            </>
          ) : null}
        </div>
      </div>
      {!canImportApi && !canImportLocal ? <small className="metadata-note">{showAccountManagementLink ? "该账户尚未配置数据导入方式，请到账户页编辑。" : "该账户尚未配置数据导入方式，请在上方账户列表编辑。"}</small> : null}
      {preview ? <ImportPreviewPanel preview={preview} importing={importing} onConfirm={onConfirmImport} /> : null}
      {!canImportApi && !canImportLocal && showAccountManagementLink && onOpenAccounts ? <Button onClick={onOpenAccounts}>配置导入方式</Button> : null}
    </section>
  );
}

export function DataDetailTabs({
  accounts,
  activeAccount,
  overview,
  canImportApi,
  canImportLocal,
  importing,
  loading,
  downloadingTemplate,
  showAccountManagementLink,
  onOpenAccounts,
  onDownloadTemplate,
  onChooseImport,
  onRefreshApiData,
  onCheckApiConnection,
  onPullAccountData,
  pullingDataType,
  preview,
  onConfirmImport,
  onSelectAccount,
  onAddPosition,
  onEditPosition,
  onDeletePosition,
  onAddDeal,
  onEditDeal,
  onDeleteDeal,
  activeDataTab,
  onDataTabChange,
}: {
  accounts: AccountSummary[];
  activeAccount: AccountSummary;
  overview: AccountDataOverview | null;
  canImportApi: boolean;
  canImportLocal: boolean;
  importing: boolean;
  loading: boolean;
  downloadingTemplate: boolean;
  showAccountManagementLink: boolean;
  onOpenAccounts?: () => void;
  onDownloadTemplate: () => Promise<void>;
  onChooseImport: (file: File | null) => Promise<void>;
  onRefreshApiData: () => Promise<void>;
  onCheckApiConnection: (dataType: string, market?: string, provider?: string) => Promise<void>;
  onPullAccountData: (dataType: string) => Promise<void>;
  pullingDataType: string | null;
  preview: ImportPreview | null;
  onConfirmImport: () => Promise<void>;
  onSelectAccount: (accountId: string) => void;
  onAddPosition: () => void;
  onEditPosition: (position: Position) => void;
  onDeletePosition: (position: Position) => void;
  onAddDeal: () => void;
  onEditDeal: (deal: AccountDeal) => void;
  onDeleteDeal: (deal: AccountDeal) => void;
  activeDataTab: string;
  onDataTabChange: (tab: string) => void;
}) {
  const isPositionTab = activeDataTab === "positions";
  const apiOnlySources = [
    { key: "quotes", dataType: "quote", title: "行情数据", updatedAt: overview?.updated_at.quote, ready: Boolean(overview?.updated_at.quote), note: "按当前账户持仓标的检测行情 API，并可拉取一次行情缓存。" },
    { key: "news", dataType: "news", title: "新闻数据", updatedAt: overview?.updated_at.news, ready: Boolean(overview?.updated_at.news), note: "按当前账户持仓标的检测新闻 API，并可拉取一次新闻缓存。" },
  ];
  return (
    <section className="panel data-detail-panel">
      <div className="toolbar data-management-toolbar">
        <div>
          <h2>数据管理</h2>
          <small>当前账户的数据管理入口；持仓、成交、行情和新闻数据统一缓存管理</small>
        </div>
        <div className="inline-actions">
          <div className="data-management-filter">
            <span className="section-kicker">当前账户</span>
            <StyledSelect
              className="account-filter-select"
              value={activeAccount.account_id}
              ariaLabel="选择账户"
              options={accounts.map((account) => ({ value: account.account_id, label: `${account.display_name || account.account_id} · ${account.base_currency}` }))}
              onChange={onSelectAccount}
            />
          </div>
        </div>
      </div>
      {!canImportApi && !canImportLocal ? <small className="metadata-note">{showAccountManagementLink ? "该账户尚未配置数据导入方式，请到账户页编辑。" : "该账户尚未配置数据导入方式，请在上方账户列表编辑。"}</small> : null}
      {preview ? <ImportPreviewPanel preview={preview} importing={importing} onConfirm={onConfirmImport} /> : null}
      <Tabs activeTab={activeDataTab} onChange={(key) => onDataTabChange(String(key))}>
        <Tabs.TabPane
          key="positions"
          title={<span className="detail-tab-title">持仓数据 <small>{formatCount(overview?.positions.length ?? 0)}</small></span>}
        >
          <div className="data-detail-tab-body">
            <div className="data-detail-action-row">
              <div className="data-detail-meta">更新时间 {overview?.updated_at.position ? formatDate(overview.updated_at.position) : "暂无刷新记录"}</div>
              <DataTableActions
                isPositionTab={isPositionTab}
                canImportApi={canImportApi}
                canImportLocal={canImportLocal}
                importing={importing}
                loading={loading}
                downloadingTemplate={downloadingTemplate}
                showAccountManagementLink={showAccountManagementLink}
                onOpenAccounts={onOpenAccounts}
                onDownloadTemplate={onDownloadTemplate}
                onChooseImport={onChooseImport}
                onRefreshApiData={onRefreshApiData}
                onAdd={onAddPosition}
              />
            </div>
            <AccountPositionsTable positions={overview?.positions ?? []} onEdit={onEditPosition} onDelete={onDeletePosition} />
          </div>
        </Tabs.TabPane>
        <Tabs.TabPane
          key="deals"
          title={<span className="detail-tab-title">成交数据 <small>{formatCount(overview?.deals.length ?? 0)}</small></span>}
        >
          <div className="data-detail-tab-body">
            <div className="data-detail-action-row">
              <div className="data-detail-meta">更新时间 {overview?.updated_at.deal ? formatDate(overview.updated_at.deal) : "暂无刷新记录"}</div>
              <DataTableActions
                isPositionTab={isPositionTab}
                canImportApi={canImportApi}
                canImportLocal={canImportLocal}
                importing={importing}
                loading={loading}
                downloadingTemplate={downloadingTemplate}
                showAccountManagementLink={showAccountManagementLink}
                onOpenAccounts={onOpenAccounts}
                onDownloadTemplate={onDownloadTemplate}
                onChooseImport={onChooseImport}
                onRefreshApiData={onRefreshApiData}
                onAdd={onAddDeal}
              />
            </div>
            <AccountDealsTable deals={overview?.deals ?? []} onEdit={onEditDeal} onDelete={onDeleteDeal} />
          </div>
        </Tabs.TabPane>
        {apiOnlySources.map((source) => (
          <Tabs.TabPane
            key={source.key}
            title={<span className="detail-tab-title">{source.title}</span>}
          >
            <div className="data-detail-tab-body">
              <div className="data-detail-action-row">
                <div className="data-detail-meta">当前账户 {activeAccount.display_name || activeAccount.account_id}</div>
              </div>
              <ApiConnectionStatusCard
                account={activeAccount}
                source={source}
                states={(overview?.provider_states ?? []).filter((item) => item.data_type === source.dataType)}
                canImportApi={canImportApi}
                loading={loading}
                pulling={pullingDataType === source.dataType}
                onOpenAccounts={onOpenAccounts}
                onCheck={onCheckApiConnection}
                onPull={onPullAccountData}
              />
            </div>
          </Tabs.TabPane>
        ))}
      </Tabs>
    </section>
  );
}

export function DataTableActions({ isPositionTab, canImportApi, canImportLocal, importing, loading, downloadingTemplate, showAccountManagementLink, onOpenAccounts, onDownloadTemplate, onChooseImport, onRefreshApiData, onAdd }: { isPositionTab: boolean; canImportApi: boolean; canImportLocal: boolean; importing: boolean; loading: boolean; downloadingTemplate: boolean; showAccountManagementLink: boolean; onOpenAccounts?: () => void; onDownloadTemplate: () => Promise<void>; onChooseImport: (file: File | null) => Promise<void>; onRefreshApiData: () => Promise<void>; onAdd: () => void }) {
  return (
    <div className="data-table-actions">
      <Button type="primary" onClick={onAdd}>新增数据</Button>
      <DataActions
        canImportApi={canImportApi}
        canImportLocal={canImportLocal}
        importing={importing}
        loading={loading}
        downloadingTemplate={downloadingTemplate}
        showAccountManagementLink={showAccountManagementLink}
        onOpenAccounts={onOpenAccounts}
        onDownloadTemplate={onDownloadTemplate}
        onChooseImport={onChooseImport}
        onRefreshApiData={onRefreshApiData}
        label="导入数据"
        importContext={isPositionTab ? "position" : "deal"}
      />
    </div>
  );
}

export function ApiConnectionActions({ canImportApi, loading, showAccountManagementLink, onOpenAccounts, onCheckApiConnection }: { canImportApi: boolean; loading: boolean; showAccountManagementLink: boolean; onOpenAccounts?: () => void; onCheckApiConnection: () => Promise<void> }) {
  return (
    <div className="data-table-actions">
      {canImportApi ? <Button type="primary" onClick={onCheckApiConnection} loading={loading} disabled={loading}>检测 API 联通</Button> : null}
      {!canImportApi && showAccountManagementLink && onOpenAccounts ? <Button onClick={onOpenAccounts}>配置 API</Button> : null}
    </div>
  );
}

export function ApiConnectionStatusCard({ account, source, states, canImportApi, loading, pulling, onOpenAccounts, onCheck, onPull }: { account: AccountSummary; source: { title: string; dataType: string; updatedAt?: string | null; ready: boolean; note: string }; states: ProviderState[]; canImportApi: boolean; loading: boolean; pulling: boolean; onOpenAccounts?: () => void; onCheck: (dataType: string, market?: string, provider?: string) => Promise<void>; onPull: (dataType: string) => Promise<void> }) {
  const visibleStates = states.filter((item) => item.provider);
  const primary = pickPrimaryProviderState(source.dataType, visibleStates);
  const requiredEnv = requiredProviderEnv(primary, source.dataType);
  const status = apiSetupStatus(source.dataType, visibleStates);
  const canCheck = canImportApi && Boolean(primary?.provider) && !loading;
  const canPull = canImportApi && Boolean(primary?.provider) && !loading && !pulling;
  return (
    <div className="api-simple-panel">
      <div className="api-simple-hero">
        <div className="api-simple-main">
          <span className="section-kicker">{source.dataType === "quote" ? "行情配置" : "新闻配置"}</span>
          <h3>{status.title}</h3>
          <p>{status.body}</p>
          <div className="api-next-step">
            <strong>{requiredEnv ? `需要填写：${requiredEnv}` : status.nextTitle}</strong>
            <span>{requiredEnv ? apiEnvHelpText(requiredEnv) : status.nextBody}</span>
          </div>
        </div>
        <div className="api-simple-side">
          <Tag color={status.color}>{status.label}</Tag>
          <Button type="primary" disabled={!canCheck} loading={loading} onClick={() => primary && onCheck(primary.data_type, primary.market, primary.provider)}>检测联通</Button>
          <Button type="primary" disabled={!canPull} loading={pulling} onClick={() => onPull(source.dataType)}>拉取数据</Button>
          {onOpenAccounts ? <Button onClick={onOpenAccounts}>管理账户</Button> : null}
        </div>
      </div>

      <div className="api-simple-result">
        <span>
          <small>当前账户</small>
          <strong>{account.display_name || account.account_id}</strong>
        </span>
        <span>
          <small>识别市场</small>
          <strong>{providerMarketsLabel(visibleStates)}</strong>
        </span>
        <span>
          <small>推荐数据源</small>
          <strong>{primary?.provider_label || "待配置"}</strong>
        </span>
        <span>
          <small>同步结果</small>
          <strong>{source.updatedAt ? formatDate(source.updatedAt) : "暂无"}</strong>
        </span>
      </div>

      <details className="api-advanced-details">
        <summary>
          <span>高级诊断</span>
          <small>查看 provider、检测时间和底层状态</small>
        </summary>
        <div className="api-provider-section">
          <div className="api-provider-section-head">
            <div>
              <strong>数据源明细</strong>
              <small>{source.note}</small>
            </div>
            {loading ? <Tag color="blue">检测中</Tag> : null}
          </div>
          {visibleStates.length ? (
            <div className="api-provider-list">
              {visibleStates.map((item) => (
                <div className="api-provider-row" key={`${item.data_type}-${item.market}-${item.provider}`}>
                  <div>
                    <strong>{marketName(item.market)} · {item.provider_label || item.provider}</strong>
                    <small>{providerSetupHint(item)}</small>
                    {item.message ? <small className="metadata-note">{item.message}</small> : null}
                  </div>
                  <div className="api-connection-status">
                    <Tag color={providerStatusColor(item.status)}>{providerStatusLabel(item.status)}</Tag>
                    <span>{item.last_success_time ? formatDate(item.last_success_time) : item.checked_at ? `检测 ${formatDate(item.checked_at)}` : "尚未检测"}</span>
                    <Button size="mini" disabled={!canImportApi || loading} onClick={() => onCheck(item.data_type, item.market, item.provider)}>检测</Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="暂无数据源状态" body="先在账户管理里设置账户市场，或在 .env 配置行情/新闻数据源。" />
          )}
        </div>
      </details>
    </div>
  );
}

export function providerSetupHint(item: ProviderState) {
  if (item.status === "not_configured") return item.message || "缺少 API Key，请在 .env 中补齐后重启服务。";
  if (item.provider === "futu") return "券商账户源：需要本地 OpenD 在线并完成账户授权。";
  if (item.data_type === "announcement" || item.data_type === "filing") return "官方公告源：只保存元数据与原始链接。";
  return item.license_note || "独立 API 源：按用户自带 Key 和订阅权限使用。";
}

export function pickPrimaryProviderState(dataType: string, states: ProviderState[]) {
  const preferredOrder = dataType === "quote" ? ["not_configured", "unavailable", "available", "configured"] : ["not_configured", "unavailable", "available", "configured", "unsupported"];
  return [...states].sort((a, b) => preferredOrder.indexOf(a.status) - preferredOrder.indexOf(b.status))[0] ?? null;
}

export function apiSetupStatus(dataType: string, states: ProviderState[]) {
  const available = states.find((item) => item.status === "available");
  if (available) {
    return {
      title: `${available.provider_label || "数据源"} 已可用`,
      body: dataType === "quote" ? "这个账户已经可以同步行情。后续只需要定期刷新。" : "这个账户已经可以同步新闻或资讯。",
      label: "已联通",
      color: "green",
      nextTitle: "下一步：执行 API 刷新",
      nextBody: "刷新后会写入最新同步结果。",
    };
  }
  const missing = states.find((item) => item.status === "not_configured");
  if (missing) {
    const providerEnv = requiredProviderEnv(missing, dataType);
    const needsApiKey = Boolean(providerEnv);
    return {
      title: dataType === "quote" ? "未配置行情源" : "未配置新闻源",
      body: needsApiKey
        ? `${marketName(missing.market)} 推荐使用 ${missing.provider_label || missing.provider}，但还缺少 API Key。`
        : providerSetupHint(missing),
      label: "需要配置",
      color: "orange",
      nextTitle: needsApiKey ? "下一步：填写 API Key" : "下一步：检查本地服务",
      nextBody: needsApiKey ? "填写后重启本地服务，再检测联通。" : "确认 OpenD 已启动、已登录并完成账户授权，然后检测联通。",
    };
  }
  const configured = states.find((item) => item.status === "configured");
  if (configured) {
    return {
      title: `${configured.provider_label || "数据源"} 已配置`,
      body: "配置项存在，但还没有成功同步结果。可以先检测联通。",
      label: "待检测",
      color: "blue",
      nextTitle: "下一步：检测联通",
      nextBody: "检测通过后再执行 API 刷新。",
    };
  }
  return {
    title: dataType === "quote" ? "暂无可用行情源" : "暂无可用新闻源",
    body: dataType === "quote" ? "当前账户还没有匹配到可用行情数据源。" : "当前市场没有匹配到独立新闻源，可查看公告源或稍后配置。",
    label: "不可用",
    color: "gray",
    nextTitle: "下一步：确认账户市场",
    nextBody: "先确认账户持仓市场是否正确，再配置数据源。",
  };
}

export function requiredProviderEnv(item: ProviderState | null, dataType: string) {
  const message = item?.message || "";
  const match = message.match(/未配置\s+([A-Z0-9_,\s]+)/);
  if (match?.[1]) return match[1].split(/[,，\s]+/).filter(Boolean)[0];
  if (item?.provider === "tushare") return "TUSHARE_TOKEN";
  if (item?.provider === "marketaux") return "MARKETAUX_API_TOKEN";
  if (item?.provider === "alpaca") return "ALPACA_API_KEY";
  if (item?.provider === "fmp") return "FMP_API_KEY";
  if (item?.provider === "alpha_vantage") return "ALPHA_VANTAGE_API_KEY";
  if (item?.provider === "polygon") return "POLYGON_API_KEY";
  return "";
}

export function apiEnvHelpText(envName: string) {
  if (envName === "TUSHARE_TOKEN") return "在 .env 中填写 Tushare Pro token，重启服务后点击检测联通。";
  if (envName === "MARKETAUX_API_TOKEN") return "在 .env 中填写 Marketaux token，重启服务后点击检测联通。";
  return `在 .env 中填写 ${envName}，重启服务后点击检测联通。`;
}

export function providerMarketsLabel(states: ProviderState[]) {
  const markets = Array.from(new Set(states.map((item) => marketName(item.market)).filter(Boolean)));
  return markets.length ? markets.join("、") : "未识别";
}

export function providerStatusLabel(status: string) {
  const labels: Record<string, string> = {
    available: "已联通",
    configured: "已配置",
    not_configured: "未配置",
    unavailable: "不可用",
    missing: "无返回",
    stale: "已过期",
    unsupported: "不支持",
  };
  return labels[status] ?? status;
}

export function providerStatusColor(status: string) {
  if (status === "available" || status === "configured") return "green";
  if (status === "not_configured" || status === "unsupported") return "gray";
  if (status === "stale" || status === "missing") return "orange";
  return "red";
}

export function DataModule({ title, updatedAt, children }: { title: string; updatedAt?: string | null; children: ReactNode }) {
  return (
    <section className="panel data-module-panel">
      <div className="toolbar">
        <div>
          <h2>{title}</h2>
          <small>{updatedAt ? `更新时间 ${formatDate(updatedAt)}` : "暂无刷新记录"}</small>
        </div>
      </div>
      {children}
    </section>
  );
}

export function AssetSnapshotCard({ overview, account }: { overview: AccountDataOverview | null; account: AccountSummary }) {
  const snapshot = overview?.asset_snapshot;
  if (!snapshot) return <Empty title="暂无账户资产快照" body="导入 Excel、文字型 PDF 或通过 API 刷新后展示。" />;
  return (
    <div className="summary-grid account-summary-grid">
      <Metric label="总资产" value={formatMoney(snapshot.total_assets, snapshot.currency || account.base_currency)} />
      <Metric label="现金" value={formatMoney(snapshot.cash, snapshot.currency || account.base_currency)} />
      <Metric label="持仓市值" value={formatMoney(snapshot.market_value, snapshot.currency || account.base_currency)} />
      <Metric label="币种" value={snapshot.currency || account.base_currency} />
      <Metric label="快照时间" value={formatDate(snapshot.snapshot_time)} />
    </div>
  );
}

type PositionSnapshotForm = {
  code: string;
  name: string;
  market: string;
  asset_type: string;
  quantity: string;
  average_cost: string;
  current_price: string;
  market_value: string;
  currency: string;
  normalized_market_value: string;
  normalized_currency: string;
  exchange_rate_to_base: string;
  profit_loss_ratio: string;
  position_weight: string;
  position_layer: string;
  snapshot_time: string;
};

const assetTypeOptions = [
  { value: "stock", label: "股票" },
  { value: "fund", label: "基金" },
  { value: "option", label: "期权" },
  { value: "bond", label: "债券" },
  { value: "crypto", label: "数字资产" },
];

export function normalizePositionMarket(value: string) {
  const market = value.trim().toUpperCase();
  if (market === "SH" || market === "SZ" || market === "SSE" || market === "SZSE") return "CN";
  if (market === "A股" || market === "A") return "CN";
  if (market === "美股") return "US";
  if (market === "港股") return "HK";
  return positionMarketOptions.some((item) => item.value === market) ? market : "";
}

export function defaultPositionMarket(account: AccountSummary) {
  const accountMarket = account.markets?.map(normalizePositionMarket).find(Boolean);
  return accountMarket || "US";
}

export function emptyPositionForm(account: AccountSummary): PositionSnapshotForm {
  return {
    code: "",
    name: "",
    market: defaultPositionMarket(account),
    asset_type: "stock",
    quantity: "",
    average_cost: "",
    current_price: "",
    market_value: "",
    currency: account.base_currency || "CNY",
    normalized_market_value: "",
    normalized_currency: account.base_currency || "CNY",
    exchange_rate_to_base: "",
    profit_loss_ratio: "",
    position_weight: "",
    position_layer: "中期配置仓",
    snapshot_time: toDatetimeLocal(new Date().toISOString()),
  };
}

export function positionToForm(position: Position, account: AccountSummary): PositionSnapshotForm {
  return {
    code: position.code,
    name: position.name,
    market: normalizePositionMarket(position.market) || defaultPositionMarket(account),
    asset_type: position.asset_type || "stock",
    quantity: String(position.quantity ?? ""),
    average_cost: String(position.average_cost ?? ""),
    current_price: String(position.current_price ?? ""),
    market_value: String(position.raw_market_value ?? ""),
    currency: position.raw_currency || account.base_currency || "CNY",
    normalized_market_value: String(position.normalized_market_value ?? ""),
    normalized_currency: position.normalized_currency || account.base_currency || "CNY",
    exchange_rate_to_base: position.exchange_rate_to_base == null ? "" : String(position.exchange_rate_to_base),
    profit_loss_ratio: String(((position.profit_loss_ratio ?? 0) * 100).toFixed(2)),
    position_weight: String(((position.position_weight ?? 0) * 100).toFixed(2)),
    position_layer: position.position_layer || "中期配置仓",
    snapshot_time: toDatetimeLocal(position.snapshot_time),
  };
}

export function toDatetimeLocal(value?: string) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function numberOrNull(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function inferMarketFromCode(code: string) {
  const normalized = code.trim().toUpperCase();
  if (normalized.startsWith("US.")) return "US";
  if (normalized.startsWith("HK.")) return "HK";
  if (normalized.startsWith("CN.") || normalized.startsWith("SH.") || normalized.startsWith("SZ.") || normalized.startsWith("FUND.")) return "CN";
  return "";
}

export function inferAssetTypeFromCode(code: string, fallback = "stock") {
  const normalized = code.trim().toUpperCase();
  if (normalized.startsWith("FUND.")) return "fund";
  return fallback || "stock";
}

export function positionFormToPayload(form: PositionSnapshotForm, original?: Position | null): PositionSnapshotPayload {
  const quantity = numberOrNull(form.quantity) ?? 0;
  const currentPrice = numberOrNull(form.current_price) ?? 0;
  const averageCost = numberOrNull(form.average_cost) ?? 0;
  const currency = form.currency.trim() || form.normalized_currency.trim() || "CNY";
  const normalizedCurrency = form.normalized_currency.trim() || currency;
  return {
    original_code: original?.code,
    original_snapshot_time: original?.snapshot_time,
    code: form.code.trim(),
    name: form.name.trim(),
    market: normalizePositionMarket(form.market) || inferMarketFromCode(form.code),
    asset_type: form.asset_type.trim() || inferAssetTypeFromCode(form.code),
    quantity,
    average_cost: averageCost,
    current_price: currentPrice,
    market_value: null,
    currency,
    normalized_market_value: null,
    normalized_currency: normalizedCurrency,
    exchange_rate_to_base: numberOrNull(form.exchange_rate_to_base),
    profit_loss_ratio: null,
    position_weight: null,
    position_layer: form.position_layer,
    snapshot_time: form.snapshot_time,
  };
}

export function AccountPositionsTable({ positions, onEdit, onDelete }: { positions: Position[]; onEdit: (position: Position) => void; onDelete: (position: Position) => void }) {
  const accountPositionsTable = useResizableTableColumns({
    name: 170,
    code: 140,
    market: 120,
    asset_type: 120,
    quantity: 130,
    average_cost: 150,
    normalized_market_value: 160,
    position_weight: 120,
    profit_loss_ratio: 120,
    actions: 150,
  });
  if (!positions.length) {
    return (
      <div className="stack">
        <Empty title="暂无持仓快照" body="导入或新增持仓快照后，这里会显示当前账户持仓。" />
      </div>
    );
  }
  return (
    <div className="table-section">
      <Table
        className="arco-data-table pro-table position-table"
        rowKey={(item: Position) => `${item.account_id}-${item.code}-${item.snapshot_time}`}
        data={positions}
        size="middle"
        hover
        tableLayoutFixed
        showSorterTooltip
        components={accountPositionsTable.components}
        border={{ wrapper: true, headerCell: false, bodyCell: false }}
        pagination={false}
        scroll={{ x: accountPositionsTable.totalTableWidth }}
        columns={[
          {
            title: "标的",
            dataIndex: "name",
            ...accountPositionsTable.columnProps("name"),
            sorter: (a: Position, b: Position) => (a.name || a.code).localeCompare(b.name || b.code),
            render: (_value, item: Position) => <span className="table-main-cell"><strong>{item.name || item.code}</strong></span>,
          },
          { title: "代码", dataIndex: "code", ...accountPositionsTable.columnProps("code"), sorter: (a: Position, b: Position) => a.code.localeCompare(b.code) },
          {
            title: "市场",
            dataIndex: "market",
            ...accountPositionsTable.columnProps("market"),
            filters: Array.from(new Set(positions.map((item) => item.market).filter(Boolean))).map((item) => ({ text: marketName(item), value: item })),
            onFilter: (value, row: Position) => row.market === value,
            render: (value: string) => value || "-",
          },
          { title: "类型", dataIndex: "asset_type", ...accountPositionsTable.columnProps("asset_type"), sorter: (a: Position, b: Position) => (a.asset_type || "").localeCompare(b.asset_type || ""), render: (value: string) => value || "-" },
          { title: "数量", dataIndex: "quantity", ...accountPositionsTable.columnProps("quantity"), sorter: (a: Position, b: Position) => a.quantity - b.quantity, render: (value: number) => formatPrice(value) },
          {
            title: "成本/现价",
            dataIndex: "average_cost",
            ...accountPositionsTable.columnProps("average_cost"),
            render: (_value, item: Position) => `${formatPrice(item.average_cost)} / ${formatPrice(item.current_price)}`,
          },
          {
            title: "市值",
            dataIndex: "normalized_market_value",
            ...accountPositionsTable.columnProps("normalized_market_value"),
            sorter: (a: Position, b: Position) => a.normalized_market_value - b.normalized_market_value,
            render: (_value, item: Position) => formatMoney(item.normalized_market_value, item.normalized_currency),
          },
          {
            title: "仓位",
            dataIndex: "position_weight",
            ...accountPositionsTable.columnProps("position_weight"),
            sorter: (a: Position, b: Position) => a.position_weight - b.position_weight,
            render: (value: number) => formatPercent(value),
          },
          {
            title: "盈亏",
            dataIndex: "profit_loss_ratio",
            ...accountPositionsTable.columnProps("profit_loss_ratio"),
            render: (value: number) => <span className={value >= 0 ? "gain" : "loss"}>{formatPercent(value)}</span>,
          },
          {
            title: "操作",
            ...accountPositionsTable.staticColumnProps("actions"),
            align: "center",
            className: "table-operation-column",
            render: (_value, item: Position) => (
              <div className="row-actions">
                <Button size="mini" onClick={() => onEdit(item)}>编辑</Button>
                <Button size="mini" status="danger" onClick={() => onDelete(item)}>删除</Button>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}

export function PositionSnapshotModal({ account, position, onClose, onSaved, setNotice }: { account: AccountSummary; position: Position | null; onClose: () => void; onSaved: (overview: AccountDataOverview) => Promise<void>; setNotice: (notice: string) => void }) {
  const [form, setForm] = useState(() => position ? positionToForm(position, account) : emptyPositionForm(account));
  const [saving, setSaving] = useState(false);
  const canSave = form.code.trim() && form.snapshot_time && form.quantity.trim() && form.current_price.trim();
  const quantity = numberOrNull(form.quantity) ?? 0;
  const currentPrice = numberOrNull(form.current_price) ?? 0;
  const averageCost = numberOrNull(form.average_cost);
  const exchangeRate = numberOrNull(form.exchange_rate_to_base);
  const inferredMarket = inferMarketFromCode(form.code);
  const currency = form.currency.trim() || form.normalized_currency.trim() || account.base_currency || "CNY";
  const normalizedCurrency = form.normalized_currency.trim() || currency;
  const marketValue = quantity * currentPrice;
  const normalizedMarketValue = marketValue * (exchangeRate || 1);
  const profitLossRatio = averageCost ? (currentPrice - averageCost) / averageCost : null;

  function updateCode(code: string) {
    const previousMarket = inferMarketFromCode(form.code);
    const previousAssetType = inferAssetTypeFromCode(form.code, form.asset_type);
    const nextMarket = inferMarketFromCode(code);
    const selectedMarket = normalizePositionMarket(form.market);
    const shouldUpdateMarket = !selectedMarket || selectedMarket === previousMarket || (!previousMarket && selectedMarket === defaultPositionMarket(account));
    const shouldUpdateType = !form.asset_type.trim() || form.asset_type === previousAssetType;
    setForm({
      ...form,
      code,
      market: shouldUpdateMarket ? (nextMarket || form.market) : form.market,
      asset_type: shouldUpdateType ? inferAssetTypeFromCode(code, form.asset_type) : form.asset_type,
    });
  }

  async function save() {
    if (!canSave) return;
    setSaving(true);
    try {
      const result = await api.saveAccountPosition(account.account_id, positionFormToPayload(form, position));
      await onSaved(result.overview);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "持仓快照保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      className="position-edit-drawer"
      width={860}
      visible
      title={position ? "编辑持仓快照" : "新增持仓快照"}
      footer={(
        <div className="modal-actions">
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={save} disabled={saving || !canSave} loading={saving}>保存持仓</Button>
        </div>
      )}
      onCancel={onClose}
    >
      <div className="stack">
        <p className="metadata-note">{account.display_name || account.account_id}</p>
        <Form layout="vertical" className="account-form-grid arco-form-grid position-form-grid compact-position-form">
          <Form.Item label="标的代码" required><Input autoFocus value={form.code} placeholder="例如 US.AAPL / FUND.006479" onChange={updateCode} /></Form.Item>
          <Form.Item label="标的名称"><Input value={form.name} placeholder="可不填，默认使用代码" onChange={(value) => setForm({ ...form, name: value })} /></Form.Item>
          <Form.Item label="数量" required><Input type="number" value={form.quantity} onChange={(value) => setForm({ ...form, quantity: value })} /></Form.Item>
          <Form.Item label="当前价格" required><Input type="number" value={form.current_price} onChange={(value) => setForm({ ...form, current_price: value })} /></Form.Item>
          <Form.Item label="平均成本"><Input type="number" value={form.average_cost} placeholder="可选，用于计算盈亏" onChange={(value) => setForm({ ...form, average_cost: value })} /></Form.Item>
        </Form>

        <section className="position-auto-preview">
          <div>
            <strong>自动计算预览</strong>
            <small>保存后仓位会按账户总资产重新计算。</small>
          </div>
          <Descriptions
            column={2}
            data={[
              { label: "预计市值", value: formatMoney(marketValue, currency) },
              { label: "预计盈亏", value: profitLossRatio == null ? "成本价为空，保存为 0%" : formatPercent(profitLossRatio) },
              { label: "账户币种", value: normalizedCurrency },
              { label: "市场", value: marketName(form.market || inferredMarket) },
              { label: "折算市值", value: exchangeRate ? formatMoney(normalizedMarketValue, normalizedCurrency) : "未填汇率时按原币市值" },
              { label: "仓位", value: "保存后自动重算" },
            ]}
          />
        </section>

        <details className="position-advanced-options" open={Boolean(position)}>
          <summary>高级选项</summary>
          <Form layout="vertical" className="account-form-grid arco-form-grid position-form-grid">
            <Form.Item label="市场">
              <StyledSelect
                value={normalizePositionMarket(form.market) || inferredMarket || defaultPositionMarket(account)}
                ariaLabel="选择持仓市场"
                options={positionMarketOptions}
                onChange={(value) => setForm({ ...form, market: value })}
              />
            </Form.Item>
            <Form.Item label="类型"><StyledSelect value={form.asset_type} ariaLabel="选择资产类型" options={assetTypeOptions} onChange={(value) => setForm({ ...form, asset_type: value })} /></Form.Item>
            <Form.Item label="原币币种"><Input value={form.currency} onChange={(value) => setForm({ ...form, currency: value.toUpperCase() })} /></Form.Item>
            <Form.Item label="折算币种"><Input value={form.normalized_currency} onChange={(value) => setForm({ ...form, normalized_currency: value.toUpperCase() })} /></Form.Item>
            <Form.Item label="汇率"><Input type="number" value={form.exchange_rate_to_base} placeholder="可选，原币 -> 折算币种" onChange={(value) => setForm({ ...form, exchange_rate_to_base: value })} /></Form.Item>
            <Form.Item label="仓位类型"><StyledSelect value={form.position_layer} ariaLabel="选择仓位类型" options={layers.filter((item) => item !== "全部").map((item) => ({ value: item, label: item }))} onChange={(value) => setForm({ ...form, position_layer: value })} /></Form.Item>
            <Form.Item label="快照时间" required><Input type="datetime-local" value={form.snapshot_time} onChange={(value) => setForm({ ...form, snapshot_time: value })} /></Form.Item>
          </Form>
        </details>
      </div>
    </Drawer>
  );
}

type DealForm = {
  deal_id: string;
  order_id: string;
  code: string;
  side: string;
  price: string;
  quantity: string;
  deal_time: string;
  market: string;
};

export function emptyDealForm(account: AccountSummary): DealForm {
  return {
    deal_id: "",
    order_id: "",
    code: "",
    side: "BUY",
    price: "",
    quantity: "",
    deal_time: toDatetimeLocal(new Date().toISOString()),
    market: account.markets?.[0] ?? "",
  };
}

export function dealToForm(deal: AccountDeal): DealForm {
  return {
    deal_id: deal.deal_id,
    order_id: deal.order_id || "",
    code: deal.code,
    side: deal.side || "BUY",
    price: String(deal.price ?? ""),
    quantity: String(deal.quantity ?? ""),
    deal_time: deal.deal_time ? toDatetimeLocal(deal.deal_time) : "",
    market: deal.market || "",
  };
}

export function dealFormToPayload(form: DealForm, original?: AccountDeal | null): DealPayload {
  return {
    original_deal_id: original?.deal_id,
    deal_id: form.deal_id.trim(),
    order_id: form.order_id.trim(),
    code: form.code.trim(),
    side: form.side.trim(),
    price: numberOrNull(form.price) ?? 0,
    quantity: numberOrNull(form.quantity) ?? 0,
    deal_time: form.deal_time || null,
    market: form.market.trim(),
  };
}

export function DealModal({ account, deal, onClose, onSaved, setNotice }: { account: AccountSummary; deal: AccountDeal | null; onClose: () => void; onSaved: (overview: AccountDataOverview) => Promise<void>; setNotice: (notice: string) => void }) {
  const [form, setForm] = useState(() => deal ? dealToForm(deal) : emptyDealForm(account));
  const [saving, setSaving] = useState(false);
  const canSave = form.deal_id.trim() && form.code.trim() && form.price.trim() && form.quantity.trim();

  async function save() {
    if (!canSave) return;
    setSaving(true);
    try {
      const result = await api.saveAccountDeal(account.account_id, dealFormToPayload(form, deal));
      await onSaved(result.overview);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "成交保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      className="deal-edit-drawer"
      width={720}
      visible
      title={deal ? "编辑成交" : "新增成交"}
      footer={(
        <div className="modal-actions">
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={save} disabled={saving || !canSave} loading={saving}>保存成交</Button>
        </div>
      )}
      onCancel={onClose}
    >
      <p className="metadata-note">{account.display_name || account.account_id}</p>
      <Form layout="vertical" className="account-form-grid arco-form-grid">
        <Form.Item label="成交号" required><Input autoFocus value={form.deal_id} onChange={(value) => setForm({ ...form, deal_id: value })} /></Form.Item>
        <Form.Item label="订单号"><Input value={form.order_id} onChange={(value) => setForm({ ...form, order_id: value })} /></Form.Item>
        <Form.Item label="标的代码" required><Input value={form.code} placeholder="例如 US.AAPL" onChange={(value) => setForm({ ...form, code: value })} /></Form.Item>
        <Form.Item label="市场"><Input value={form.market} placeholder="US / HK / CN" onChange={(value) => setForm({ ...form, market: value })} /></Form.Item>
        <Form.Item label="方向"><StyledSelect value={form.side} ariaLabel="选择成交方向" options={[{ value: "BUY", label: "买入" }, { value: "SELL", label: "卖出" }]} onChange={(value) => setForm({ ...form, side: value })} /></Form.Item>
        <Form.Item label="价格" required><Input type="number" value={form.price} onChange={(value) => setForm({ ...form, price: value })} /></Form.Item>
        <Form.Item label="数量" required><Input type="number" value={form.quantity} onChange={(value) => setForm({ ...form, quantity: value })} /></Form.Item>
        <Form.Item label="成交时间"><Input type="datetime-local" value={form.deal_time} onChange={(value) => setForm({ ...form, deal_time: value })} /></Form.Item>
      </Form>
    </Drawer>
  );
}

export function AccountDealsTable({ deals, onEdit, onDelete }: { deals: AccountDeal[]; onEdit: (deal: AccountDeal) => void; onDelete: (deal: AccountDeal) => void }) {
  const dealsTable = useResizableTableColumns({
    deal_time: 190,
    code: 150,
    market: 130,
    side: 120,
    price: 120,
    quantity: 120,
    deal_id: 190,
    order_id: 190,
    actions: 150,
  });
  if (!deals.length) {
    return (
      <div className="stack">
        <Empty title="暂无成交记录" body="导入或新增成交后，画像和复盘会使用这些交易样本。" />
      </div>
    );
  }
  return (
    <div className="table-section">
      <Table
        className="arco-data-table pro-table deal-table"
        rowKey={(item: AccountDeal) => `${item.account_id}-${item.deal_id}`}
        data={deals.slice(0, 80)}
        size="middle"
        hover
        tableLayoutFixed
        showSorterTooltip
        components={dealsTable.components}
        border={{ wrapper: true, headerCell: false, bodyCell: false }}
        pagination={false}
        scroll={{ x: dealsTable.totalTableWidth }}
        columns={[
          { title: "时间", dataIndex: "deal_time", ...dealsTable.columnProps("deal_time"), sorter: (a: AccountDeal, b: AccountDeal) => new Date(a.deal_time ?? "").getTime() - new Date(b.deal_time ?? "").getTime(), render: (value: string) => formatDate(value) },
          {
            title: "标的",
            dataIndex: "code",
            ...dealsTable.columnProps("code"),
            sorter: (a: AccountDeal, b: AccountDeal) => a.code.localeCompare(b.code),
            render: (_value, item: AccountDeal) => <span className="table-main-cell"><strong>{item.code}</strong></span>,
          },
          { title: "市场", dataIndex: "market", ...dealsTable.columnProps("market"), sorter: (a: AccountDeal, b: AccountDeal) => (a.market || "").localeCompare(b.market || ""), render: (value: string) => value || "未知市场" },
          {
            title: "方向",
            dataIndex: "side",
            ...dealsTable.columnProps("side"),
            sorter: (a: AccountDeal, b: AccountDeal) => sideName(a.side).localeCompare(sideName(b.side)),
            render: (value: string) => <Tag color={value.includes("买") || value.toLowerCase().includes("buy") ? "red" : "green"}>{sideName(value)}</Tag>,
          },
          { title: "价格", dataIndex: "price", ...dealsTable.columnProps("price"), sorter: (a: AccountDeal, b: AccountDeal) => a.price - b.price, render: (value: number) => formatPrice(value) },
          { title: "数量", dataIndex: "quantity", ...dealsTable.columnProps("quantity"), sorter: (a: AccountDeal, b: AccountDeal) => a.quantity - b.quantity, render: (value: number) => formatPrice(value) },
          {
            title: "成交号",
            dataIndex: "deal_id",
            ...dealsTable.columnProps("deal_id"),
            render: (value: string) => value,
          },
          { title: "订单号", dataIndex: "order_id", ...dealsTable.columnProps("order_id"), render: (value: string) => value || "无订单号" },
          {
            title: "操作",
            ...dealsTable.staticColumnProps("actions"),
            align: "center",
            className: "table-operation-column",
            render: (_value, item: AccountDeal) => (
              <div className="row-actions">
                <Button size="mini" onClick={() => onEdit(item)}>编辑</Button>
                <Button size="mini" status="danger" onClick={() => onDelete(item)}>删除</Button>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}

export function ImportPreviewPanel({ preview, importing, onConfirm }: { preview: ImportPreview; importing: boolean; onConfirm: () => void }) {
  const importPreviewTable = useResizableTableColumns({
    name: 170,
    code: 140,
    quantity: 120,
    current_price: 120,
    normalized_market_value: 160,
    missing_market_code: 140,
  });
  const dealPreviewTable = useResizableTableColumns({
    deal_id: 160,
    code: 140,
    side: 100,
    price: 120,
    quantity: 120,
    deal_time: 180,
  });
  const deals = preview.deals ?? [];
  const isDealPreview = deals.length > 0 && preview.position_count === 0;
  const buyCount = deals.filter((item) => item.side === "BUY").length;
  const sellCount = deals.filter((item) => item.side === "SELL").length;
  return (
    <div className="import-preview inline-import-preview">
      <div className="summary-grid">
        <Metric label="来源" value={sourceLabel(preview.source_name)} />
        {isDealPreview ? (
          <>
            <Metric label="成交数" value={preview.deal_count} />
            <Metric label="买入" value={buyCount} />
            <Metric label="卖出" value={sellCount} />
          </>
        ) : (
          <>
            <Metric label="持仓数" value={preview.position_count} />
            <Metric label="总资产" value={formatMoney(preview.total_assets)} />
            <Metric label="持仓市值" value={formatMoney(preview.market_value)} />
          </>
        )}
      </div>
      {preview.errors?.length ? <Checklist title="导入错误" items={preview.errors} emptyText="无" /> : null}
      {preview.warnings?.length ? <Checklist title="导入提示" items={preview.warnings} emptyText="无" /> : null}
      {preview.positions.length ? (
        <Table
          className="arco-data-table pro-table import-preview-table"
          rowKey={(item: Position) => `${item.account_id}-${item.code}`}
          data={preview.positions.slice(0, 8)}
          size="middle"
          hover
          tableLayoutFixed
          showSorterTooltip
          components={importPreviewTable.components}
          border={{ wrapper: true, headerCell: false, bodyCell: false }}
          pagination={false}
          scroll={{ x: importPreviewTable.totalTableWidth }}
          columns={[
            {
              title: "标的",
              dataIndex: "name",
              ...importPreviewTable.columnProps("name"),
              sorter: (a: Position, b: Position) => (a.name || a.code).localeCompare(b.name || b.code),
              render: (_value, item: Position) => <span className="table-main-cell"><strong>{item.name || item.code}</strong></span>,
            },
            { title: "代码", dataIndex: "code", ...importPreviewTable.columnProps("code"), sorter: (a: Position, b: Position) => a.code.localeCompare(b.code) },
            { title: "数量", dataIndex: "quantity", ...importPreviewTable.columnProps("quantity"), sorter: (a: Position, b: Position) => a.quantity - b.quantity, render: (value: number) => formatPrice(value) },
            { title: "现价", dataIndex: "current_price", ...importPreviewTable.columnProps("current_price"), sorter: (a: Position, b: Position) => a.current_price - b.current_price, render: (value: number) => formatPrice(value) },
            {
              title: "市值",
              dataIndex: "normalized_market_value",
              ...importPreviewTable.columnProps("normalized_market_value"),
              sorter: (a: Position, b: Position) => a.normalized_market_value - b.normalized_market_value,
              render: (_value, item: Position) => formatMoney(item.normalized_market_value, item.normalized_currency),
            },
            {
              title: "状态",
              dataIndex: "missing_market_code",
              ...importPreviewTable.columnProps("missing_market_code"),
              render: (value: boolean) => <Tag color={value ? "orange" : "green"}>{value ? "需复核代码" : "可识别"}</Tag>,
            },
          ]}
        />
      ) : null}
      {deals.length ? (
        <Table
          className="arco-data-table pro-table import-preview-table"
          rowKey={(item: AccountDeal) => `${item.account_id}-${item.deal_id}`}
          data={deals.slice(0, 8)}
          size="middle"
          hover
          tableLayoutFixed
          components={dealPreviewTable.components}
          border={{ wrapper: true, headerCell: false, bodyCell: false }}
          pagination={false}
          scroll={{ x: dealPreviewTable.totalTableWidth }}
          columns={[
            { title: "成交号", dataIndex: "deal_id", ...dealPreviewTable.columnProps("deal_id") },
            { title: "代码", dataIndex: "code", ...dealPreviewTable.columnProps("code") },
            { title: "方向", dataIndex: "side", ...dealPreviewTable.columnProps("side"), render: (value: string) => value === "SELL" ? "卖出" : "买入" },
            { title: "价格", dataIndex: "price", ...dealPreviewTable.columnProps("price"), render: (value: number) => formatPrice(value) },
            { title: "数量", dataIndex: "quantity", ...dealPreviewTable.columnProps("quantity"), render: (value: number) => formatPrice(value) },
            { title: "成交时间", dataIndex: "deal_time", ...dealPreviewTable.columnProps("deal_time"), render: (value?: string | null) => value ? formatDate(value) : "导入时间" },
          ]}
        />
      ) : null}
      <Button type="primary" onClick={onConfirm} disabled={importing || !preview.can_confirm || !!preview.errors?.length} loading={importing}>确认导入</Button>
    </div>
  );
}

export function AdvancedSettingsPage({ health, setNotice, requestConfirm, onDelete }: { health: HealthStatus | null; setNotice: (notice: string) => void; requestConfirm: (options: ConfirmOptions) => Promise<boolean>; onDelete: () => Promise<void> }) {
  const [aiConfig, setAiConfig] = useState<AIConfigResponse | null>(null);
  const [aiForm, setAiForm] = useState<AIConfigForm>(() => emptyAIConfigForm(health));
  const [loadingAiConfig, setLoadingAiConfig] = useState(false);
  const [savingAiConfig, setSavingAiConfig] = useState(false);
  const [testingAiConfig, setTestingAiConfig] = useState(false);
  const aiConfigured = Boolean(aiConfig?.runtime.enabled && aiConfig.runtime.has_api_key) || Boolean(health?.ai?.configured);
  const selectedProvider = aiConfig?.providers.find((item) => item.provider === aiForm.provider);
  const aiProvider = aiConfig?.runtime.display_name || health?.ai?.display_name || providerName(health?.ai?.provider ?? "local");
  const aiModel = aiConfig?.runtime.model || health?.ai?.model || "local_reasoning";

  useEffect(() => {
    setLoadingAiConfig(true);
    api.aiConfig()
      .then((result) => {
        setAiConfig(result);
        setAiForm(formFromAIRuntime(result.runtime));
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "AI 配置加载失败"))
      .finally(() => setLoadingAiConfig(false));
  }, []);

  function updateProvider(provider: string) {
    const template = aiConfig?.providers.find((item) => item.provider === provider);
    setAiConfig((current) => current && template ? {
      ...current,
      scenes: current.scenes.map((scene) => ({ ...scene, provider, model: template.default_model })),
    } : current);
    setAiForm((current) => ({
      ...current,
      provider,
      display_name: template?.label || current.display_name,
      base_url: template?.default_base_url || current.base_url,
      model: template?.default_model || current.model,
    }));
  }

  async function saveAIConfig() {
    setSavingAiConfig(true);
    try {
      const result = await api.saveAIConfig({ ...aiConfigPayload(aiForm), scenes: aiConfig?.scenes ?? [] });
      setAiConfig(result);
      setAiForm(formFromAIRuntime(result.runtime));
      setNotice("AI 模型配置已保存");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "AI 模型配置保存失败");
    } finally {
      setSavingAiConfig(false);
    }
  }

  async function testAIConfig() {
    setTestingAiConfig(true);
    try {
      const result = await api.testAIConfig(aiConfigPayload(aiForm));
      setNotice(result.status === "success" ? "AI 模型连接可用" : `AI 模型连接失败：${result.message}`);
      setAiConfig((current) => current ? { ...current, runtime: result.runtime } : current);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "AI 模型连接测试失败");
    } finally {
      setTestingAiConfig(false);
    }
  }

  return (
    <div className="stack settings-page">
      <section className="panel settings-hero">
        <div className="settings-hero-copy">
          <span className="section-kicker">AI 模型配置中心</span>
          <h2>{aiConfigured ? `AI 分析已接入 ${aiProvider}` : "尚未接入外部大模型"}</h2>
          <p>{aiConfigured ? "系统会在生成持仓诊断、标的分析和组合报告时调用当前启用的大模型配置。" : "你可以选择主流模型平台，填写 API Key 后直接激活 AI 分析；未配置时系统会使用本地规则降级分析。"}</p>
        </div>
        <div className="settings-hero-status">
          <Tag color={aiConfigured ? "green" : "orange"}>{aiConfigured ? "外部模型已配置" : "本地降级"}</Tag>
          <strong>{aiProvider}</strong>
          <small>{aiModel}</small>
        </div>
      </section>

      <section className="panel ai-runtime-panel">
        <div className="settings-section-head">
          <div>
            <span className="section-kicker">模型服务商</span>
            <h2>选择并激活大模型 API</h2>
          </div>
          <Tag color={aiConfig?.runtime.last_test_status === "success" ? "green" : aiConfigured ? "arcoblue" : "orange"}>
            {aiConfig?.runtime.last_test_status === "success" ? "连接可用" : aiConfigured ? "已保存" : "待配置"}
          </Tag>
        </div>
        <Form layout="vertical" className="ai-runtime-form">
          <Form.Item label="服务商">
            <Select value={aiForm.provider} loading={loadingAiConfig} onChange={(value) => updateProvider(String(value))}>
              {(aiConfig?.providers ?? []).map((item) => (
                <Select.Option key={item.provider} value={item.provider}>{item.label}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item label="启用外部模型">
            <Checkbox checked={aiForm.enabled} onChange={(checked) => setAiForm({ ...aiForm, enabled: checked })}>启用后，AI 分析会调用下方 API 配置</Checkbox>
          </Form.Item>
          <Form.Item label="API Key">
            <Input.Password
              value={aiForm.api_key}
              placeholder={aiConfig?.runtime.masked_api_key ? `已保存：${aiConfig.runtime.masked_api_key}；留空则不修改` : "输入当前服务商的 API Key"}
              onChange={(value) => setAiForm({ ...aiForm, api_key: value })}
            />
          </Form.Item>
          <Form.Item label="Base URL">
            <Input value={aiForm.base_url} placeholder="https://.../v1" onChange={(value) => setAiForm({ ...aiForm, base_url: value })} />
          </Form.Item>
          <Form.Item label="默认模型（连接测试）">
            {selectedProvider?.models.length ? (
              <Select
                value={aiForm.model}
                placeholder="选择当前服务商支持的模型"
                showSearch
                onChange={(value) => setAiForm({ ...aiForm, model: String(value) })}
              >
                {selectedProvider.models.map((model) => (
                  <Select.Option key={model} value={model}>{model}</Select.Option>
                ))}
              </Select>
            ) : (
              <Input
                value={aiForm.model}
                placeholder={selectedProvider?.default_model || "输入自定义接口提供的模型名"}
                onChange={(value) => setAiForm({ ...aiForm, model: value })}
              />
            )}
          </Form.Item>
        </Form>
        {selectedProvider?.help_text ? <p className="metadata-note">{selectedProvider.help_text}</p> : null}
        <div className="ai-scene-models">
          <div className="ai-scene-models-head">
            <strong>各 AI 节点使用的模型</strong>
            <small>六个场景独立保存，互不覆盖。</small>
          </div>
          <div className="ai-scene-model-grid">
            {(aiConfig?.scenes ?? []).map((scene) => (
              <label className="ai-scene-model-field" key={scene.scene}>
                <span>{scene.label}</span>
                <Select
                  value={scene.model}
                  placeholder="选择模型"
                  showSearch
                  onChange={(value) => setAiConfig((current) => current ? {
                    ...current,
                    scenes: current.scenes.map((item) => item.scene === scene.scene ? { ...item, model: String(value), provider: aiForm.provider } : item),
                  } : current)}
                >
                  {(selectedProvider?.models ?? []).map((model) => (
                    <Select.Option key={model} value={model}>{model}</Select.Option>
                  ))}
                </Select>
              </label>
            ))}
          </div>
        </div>
        {aiConfig?.runtime.last_test_message ? <Alert type={aiConfig.runtime.last_test_status === "success" ? "success" : "warning"} content={aiConfig.runtime.last_test_message} /> : null}
        <div className="settings-form-actions">
          <Button onClick={testAIConfig} loading={testingAiConfig} disabled={!aiForm.enabled || !aiForm.base_url || !aiForm.model}>测试连接</Button>
          <Button type="primary" onClick={saveAIConfig} loading={savingAiConfig} disabled={!aiForm.provider || !aiForm.base_url || !aiForm.model}>保存并启用</Button>
        </div>
      </section>

      <DangerDataManagement requestConfirm={requestConfirm} onDelete={onDelete} />
    </div>
  );
}

type AIConfigForm = {
  provider: string;
  display_name: string;
  base_url: string;
  model: string;
  api_key: string;
  enabled: boolean;
};

function emptyAIConfigForm(health: HealthStatus | null): AIConfigForm {
  return {
    provider: health?.ai?.provider || "deepseek",
    display_name: health?.ai?.display_name || providerName(health?.ai?.provider || "deepseek"),
    base_url: "",
    model: health?.ai?.model || "",
    api_key: "",
    enabled: health?.ai?.enabled ?? true,
  };
}

function formFromAIRuntime(runtime: AIRuntimeConfig): AIConfigForm {
  return {
    provider: runtime.provider || "deepseek",
    display_name: runtime.display_name || providerName(runtime.provider),
    base_url: runtime.base_url || "",
    model: runtime.model || "",
    api_key: "",
    enabled: runtime.enabled,
  };
}

function aiConfigPayload(form: AIConfigForm) {
  const payload: Record<string, string | boolean> = {
    provider: form.provider,
    display_name: form.display_name,
    base_url: form.base_url,
    model: form.model,
    enabled: form.enabled,
  };
  if (form.api_key.trim()) payload.api_key = form.api_key.trim();
  return payload;
}

export function DangerDataManagement({ requestConfirm, onDelete }: { requestConfirm: (options: ConfirmOptions) => Promise<boolean>; onDelete: () => Promise<void> }) {
  async function confirmDelete() {
    const confirmed = await requestConfirm({
      title: "删除本地数据",
      body: "该操作会清空本地账户、持仓、建议、提醒和复盘记录。删除后需要重新导入或同步数据。",
      confirmText: "确认删除",
      cancelText: "取消",
      tone: "danger",
    });
    if (confirmed) await onDelete();
  }
  return (
    <section className="panel settings-danger-zone">
      <div className="settings-section-head">
        <div>
          <span className="section-kicker">危险区</span>
          <h2>数据管理</h2>
        </div>
      </div>
      <Alert type="warning" content="删除会清空本地账户、持仓、建议、提醒和复盘记录。这个操作不会修改外部券商账户。" />
      <div className="settings-danger-actions">
        <div>
          <strong>清空本地工作台数据</strong>
          <small>适合需要重新初始化本地环境，或导入了错误账户数据时使用。</small>
        </div>
        <Button status="danger" onClick={confirmDelete}>删除本地数据</Button>
      </div>
    </section>
  );
}

export function ConfirmDialog({ options, onResolve }: { options: ConfirmOptions; onResolve: (confirmed: boolean) => void }) {
  return (
    <Modal
      visible
      className={`confirm-dialog ${options.tone === "danger" ? "danger" : ""}`}
      title={options.title}
      okText={options.confirmText ?? "确认"}
      cancelText={options.cancelText ?? "取消"}
      okButtonProps={{ status: options.tone === "danger" ? "danger" : undefined }}
      onOk={() => onResolve(true)}
      onCancel={() => onResolve(false)}
      simple
    >
      <p>{options.body}</p>
    </Modal>
  );
}

export function Spinner() {
  return <Spin size={14} aria-hidden="true" />;
}

export function Metric({ label, value, action }: { label: string; value: string | number; action?: ReactNode }) {
  const displayValue = typeof value === "number" ? formatCount(value) : value;
  const moneyMatch = typeof displayValue === "string" ? displayValue.match(/^(.+?)\s*([A-Z]{3,4})$/) : null;
  const moneyDigits = moneyMatch ? moneyMatch[1].replace(/[^\d.-]/g, "").length : 0;
  const isLongValue = typeof displayValue === "string" && displayValue.length > 15;
  return (
    <div className={`metric ${action ? "with-action" : ""} ${isLongValue ? "metric-long" : ""}`}>
      <span className="metric-label">
        <small>{label}</small>
        {action ? <span className="metric-actions">{action}</span> : null}
      </span>
      <strong className={moneyMatch ? "metric-money" : ""}>
        {moneyMatch ? (
          <>
            <span className={`metric-money-amount metric-money-amount-length-${Math.min(moneyDigits, 12)}`}>{moneyMatch[1]}</span>
            <small className="metric-money-currency">{moneyMatch[2]}</small>
          </>
        ) : displayValue}
      </strong>
    </div>
  );
}

export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <section className="empty">
      <h2>{title}</h2>
      <ArcoEmpty description={body} />
    </section>
  );
}

export function diagnosisSummary(run: AIWorkflowRun) {
  const explicit = run.output?.summary || "";
  if (explicit) return trimHighlight(explicit);
  const text = run.output?.markdown || run.output?.partial_markdown || "";
  return getReportHighlights(text)[0] || `${workflowStatusLabel(run.status)}，可打开报告查看完整持仓诊断。`;
}

export function latestPortfolioDiagnosisRun(runs: AIWorkflowRun[]) {
  const diagnosisRuns = runs
    .filter((run) => run.workflow_type === "portfolio_diagnosis")
    .sort((a, b) => parseBackendDate(b.created_at).getTime() - parseBackendDate(a.created_at).getTime());
  return diagnosisRuns.find((run) => run.status === "completed") ?? diagnosisRuns[0];
}

export function latestSnapshotTime(dashboard: Dashboard | null, positions: Position[]) {
  const times = [
    dashboard?.sync?.end_time,
    ...positions.map((item) => item.snapshot_time),
    ...(dashboard?.portfolio.accounts ?? []).map((item) => item.snapshot_time || item.last_sync_time || ""),
  ].filter(Boolean) as string[];
  return times.sort((a, b) => parseBackendDate(b).getTime() - parseBackendDate(a).getTime())[0] || null;
}

export function dataSourceNames(accounts: AccountSummary[]) {
  const names = Array.from(new Set(accounts.map((item) => sourceLabel(item.source_name)).filter(Boolean)));
  return names.length ? names.join(" / ") : "本地数据";
}

export function dataQualitySummary(dashboard: Dashboard | null, positions: Position[], latestDiagnosis: AIWorkflowRun | undefined, snapshotTime?: string | null) {
  const stale = dashboard?.freshness?.filter((item) => item.status === "stale").length ?? 0;
  const missing = dashboard?.freshness?.filter((item) => item.status === "missing").length ?? 0;
  const unclassified = positions.filter((item) => !item.position_layer || item.position_layer === "未分层").length;
  const lowConfidence = positions.filter((item) => item.layer_confidence === "低").length;
  const diagnosisTime = latestDiagnosis?.created_at;
  const reportOlderThanSnapshot = Boolean(diagnosisTime && snapshotTime && parseBackendDate(diagnosisTime).getTime() < parseBackendDate(snapshotTime).getTime());
  if (reportOlderThanSnapshot) return { label: "报告基于旧快照", detail: "资产结构已可按最新持仓展示，建议重新生成持仓诊断。", tone: "orange" as const };
  if (stale || missing) return { label: "数据需复核", detail: `${stale} 类数据过期，${missing} 类数据缺失。`, tone: "orange" as const };
  if (unclassified || lowConfidence) return { label: "分类可优化", detail: `${unclassified} 只未分类，${lowConfidence} 只分类置信度偏低。`, tone: "arcoblue" as const };
  return { label: latestDiagnosis ? "报告可用" : "本地规则可用", detail: latestDiagnosis ? "最近报告与当前快照未发现明显时间冲突。" : "尚无 AI 报告，当前展示本地规则体检。", tone: latestDiagnosis ? "green" as const : "arcoblue" as const };
}

export function concentrationSummary(dashboard: Dashboard | null, positions: Position[], themes: Array<{ theme: string; weight: number }>) {
  const sortedWeights = [...positions].map((item) => Math.max(item.position_weight || 0, 0)).sort((a, b) => b - a);
  const top1 = dashboard?.portfolio.max_position_weight ?? sortedWeights[0] ?? 0;
  const top5 = sortedWeights.slice(0, 5).reduce((sum, value) => sum + value, 0);
  const topTheme = themes[0];
  return {
    top1,
    top5,
    themeLabel: topTheme ? `${topTheme.theme} ${formatPercent(topTheme.weight)}` : "暂无",
  };
}

type HomeSummaryCardTone = "info" | "ok" | "watch" | "risk";
type HomeSummaryCardItem = { text: string; reason?: string; code?: string };
type HomeSummaryCard = {
  key: "overall_verdict" | "priority_review";
  label: string;
  tone: HomeSummaryCardTone;
  summary: string;
  items: HomeSummaryCardItem[];
  source: "ai_report" | "local_rules";
};

const HOME_CARD_ORDER: HomeSummaryCard["key"][] = ["overall_verdict", "priority_review"];
const HOME_CARD_LABELS: Record<HomeSummaryCard["key"], string> = {
  overall_verdict: "本次体检结论",
  priority_review: "优先复核",
};

export function aiConclusionPoints(latestDiagnosis: AIWorkflowRun | undefined, dashboard: Dashboard | null, positions: Position[], themes?: Array<{ theme: string; weight: number }>): HomeSummaryCard[] {
  const generatedCards = normalizeHomeSummaryCards(latestDiagnosis?.output?.home_summary_cards);
  if (generatedCards.length === 2) return generatedCards;
  const concentration = concentrationSummary(dashboard, positions, themes ?? themeExposure(latestDiagnosis, positions, dashboard));
  const topReviewItems = priorityReviewItems(positions).slice(0, 3);
  const topName = topReviewItems[0]?.text || positions[0]?.name || positions[0]?.code;
  const hasConcentrationRisk = concentration.top1 > 0.25 || concentration.top5 > 0.65;
  const hasLossRisk = positions.some((item) => item.profit_loss_ratio < -0.15);
  const cashLow = (dashboard?.portfolio.cash_ratio ?? 0) < 0.05;
  const verdictTone: HomeSummaryCardTone = hasConcentrationRisk || hasLossRisk || cashLow ? "risk" : positions.length ? "ok" : "info";
  const verdictSummary = !positions.length
    ? "导入或同步持仓后，首页会显示组合体检结论。"
    : hasConcentrationRisk && topName
      ? `组合偏集中，先复核 ${topName} 等核心暴露。`
      : hasLossRisk
        ? "组合存在较深亏损持仓，先复核亏损理由和复盘记录。"
          : cashLow
            ? "现金缓冲偏低，阶段性复核时先确认流动性安排。"
            : "组合暂无突出预警，保持定期复核即可。";
  return [
    {
      key: "overall_verdict",
      label: HOME_CARD_LABELS.overall_verdict,
      tone: verdictTone,
      summary: verdictSummary,
      items: compactCardItems([
        hasConcentrationRisk ? { text: "集中度复核", reason: `第一大/Top5 权重已进入重点观察区间` } : undefined,
        hasLossRisk ? { text: "亏损复盘", reason: "存在亏损超过 15% 的持仓" } : undefined,
        cashLow ? { text: "流动性检查", reason: "现金缓冲偏低" } : undefined,
      ]),
      source: "local_rules",
    },
    {
      key: "priority_review",
      label: HOME_CARD_LABELS.priority_review,
      tone: topReviewItems.length ? "watch" : "ok",
      summary: topReviewItems.length ? "先看这些标的，原因比仓位数字更重要。" : "暂无需要立即复核的单一标的。",
      items: topReviewItems,
      source: "local_rules",
    },
  ];
}

export function normalizeHomeSummaryCards(cards?: AIWorkflowRun["output"]["home_summary_cards"]): HomeSummaryCard[] {
  const byKey = new Map<HomeSummaryCard["key"], HomeSummaryCard>();
  for (const card of cards ?? []) {
    const key = String(card.key || "") as HomeSummaryCard["key"];
    if (!HOME_CARD_ORDER.includes(key)) continue;
    const summary = cleanHomeCardText(card.summary || card.value || "");
    const items = compactCardItems((card.items ?? []).map((item) => ({
      text: cleanHomeCardText(item.text),
      reason: cleanHomeCardText(item.reason || ""),
      code: cleanHomeCardText(item.code || ""),
    })));
    if (!summary && !items.length) continue;
    byKey.set(key, {
      key,
      label: HOME_CARD_LABELS[key],
      tone: normalizeHomeCardTone(card.tone),
      summary: summary || items[0].text,
      items,
      source: card.source === "local_rules" ? "local_rules" : "ai_report",
    });
  }
  return HOME_CARD_ORDER.map((key) => byKey.get(key)).filter((item): item is HomeSummaryCard => Boolean(item));
}

function normalizeHomeCardTone(value: unknown): HomeSummaryCardTone {
  return value === "ok" || value === "watch" || value === "risk" || value === "info" ? value : "info";
}

function compactCardItems(items: Array<HomeSummaryCardItem | undefined>) {
  return items
    .filter((item): item is HomeSummaryCardItem => Boolean(item?.text))
    .map((item) => ({
      text: cleanHomeCardText(item.text),
      reason: item.reason ? cleanHomeCardText(item.reason) : undefined,
      code: item.code ? cleanHomeCardText(item.code) : undefined,
    }))
    .filter((item) => item.text)
    .slice(0, 3);
}

function priorityReviewItems(positions: Position[]): HomeSummaryCardItem[] {
  return [...positions]
    .map((item) => {
      const reasons = [
        item.position_weight > 0.25 ? `仓位 ${formatPercent(item.position_weight)}，需确认集中暴露` : "",
        item.profit_loss_ratio < -0.15 ? `亏损 ${formatPercent(Math.abs(item.profit_loss_ratio))}，需复核买入理由` : "",
        item.layer_confidence === "低" || item.position_layer === "未分层" ? "分类置信度偏低，影响主题判断" : "",
      ].filter(Boolean);
      const score = item.position_weight * 3 + Math.max(0, -item.profit_loss_ratio) + reasons.length * 0.2;
      return { item, reasons, score };
    })
    .filter((item) => item.reasons.length)
    .sort((a, b) => b.score - a.score)
    .map(({ item, reasons }) => ({ code: item.code, text: item.name || item.code, reason: reasons[0] }));
}

export function cleanHomeCardText(value: string) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text || /calculation_audit|audit_pack|account_weight|total_assets|distribution_checks|tool_args|portfolio_status|main_risk|next_action|opportunity/i.test(text)) return "";
  return text.length > 84 ? `${text.slice(0, 82)}...` : text;
}

export function cleanDiagnosisSummary(value: string) {
  const text = trimHighlight(value || "");
  if (!text || /calculation_audit|audit_pack|warning 状态|权重口径说明|total_assets/i.test(text)) return "";
  return text;
}

export function localRuleSummary(dashboard: Dashboard | null, positions: Position[], concentration: { top1: number; top5: number; themeLabel: string }) {
  if (!positions.length) return "导入或同步持仓后，这里会展示最近一次组合体检结论。";
  return `当前组合包含 ${formatCount(positions.length)} 只持仓，现金比例 ${formatPercent(dashboard?.portfolio.cash_ratio ?? 0)}，最大单票 ${formatPercent(concentration.top1)}，Top5 集中度 ${formatPercent(concentration.top5)}。`;
}

export function riskNotes(dashboard: Dashboard | null, positions: Position[], dataQuality: { label: string; detail: string }) {
  const notes = [dataQuality.detail];
  if ((dashboard?.portfolio.max_position_weight ?? 0) > 0.25) notes.push("最大单票仓位超过 25%，建议优先查看标的详情和 AI 建议。");
  if ((dashboard?.portfolio.cash_ratio ?? 0) < 0.05) notes.push("现金比例较低，阶段性复核时需关注流动性余量。");
  if (positions.some((item) => item.profit_loss_ratio < -0.15)) notes.push("存在亏损超过 15% 的持仓，建议结合买入理由和交易复盘检查。");
  return Array.from(new Set(notes)).slice(0, 4);
}

export function themeExposure(latestDiagnosis: AIWorkflowRun | Position[] | undefined, positionsOrDashboard: Position[] | Dashboard | null, dashboardMaybe?: Dashboard | null) {
  const positions = Array.isArray(latestDiagnosis) ? latestDiagnosis : Array.isArray(positionsOrDashboard) ? positionsOrDashboard : [];
  const dashboard = Array.isArray(latestDiagnosis) ? (positionsOrDashboard as Dashboard | null) : dashboardMaybe ?? null;
  const diagnosis = Array.isArray(latestDiagnosis) ? undefined : latestDiagnosis;
  const reportThemes = themeExposureFromArtifacts(diagnosis?.artifacts);
  if (reportThemes.length) return reportThemes;
  const groups = new Map<string, { theme: string; value: number; count: number }>();
  for (const position of positions) {
    const theme = themeLabel(position);
    const current = groups.get(theme) ?? { theme, value: 0, count: 0 };
    current.value += Math.max(positionMarketValueBase(position, dashboard), 0);
    current.count += 1;
    groups.set(theme, current);
  }
  if ((dashboard?.portfolio.cash_ratio ?? 0) > 0) {
    const baseTotal = dashboard?.portfolio.total_assets ?? 0;
    const cashValue = baseTotal ? baseTotal * (dashboard?.portfolio.cash_ratio ?? 0) : Math.max(dashboard?.portfolio.cash ?? 0, 0);
    const current = groups.get("现金/流动性") ?? { theme: "现金/流动性", value: 0, count: 0 };
    current.value += cashValue;
    groups.set("现金/流动性", current);
  }
  const total = Array.from(groups.values()).reduce((sum, item) => sum + item.value, 0) || 1;
  return Array.from(groups.values()).map((item) => ({ ...item, weight: item.value / total })).sort((a, b) => b.value - a.value);
}

export function themeExposureFromArtifacts(artifacts?: WorkflowArtifact[]) {
  const artifact = artifacts?.find((item) => item.artifact_id === "theme_concentration" || item.title === "行业/主题集中度");
  return (artifact?.data ?? [])
    .map((item) => ({
      theme: String(item.label || "未分类"),
      weight: Number(item.value) || 0,
      value: Number(item.value) || 0,
      count: 0,
    }))
    .filter((item) => item.weight > 0)
    .sort((a, b) => b.weight - a.weight);
}

export function themeLabel(position: Position) {
  const text = `${position.code || ""} ${position.name || ""}`.toUpperCase();
  const assetType = `${position.asset_type || ""}`.toUpperCase();
  if (["QQQ", "SPY", "VOO", "纳斯达克", "NASDAQ", "标普", "S&P"].some((token) => text.includes(token))) return "宽基/成长ETF";
  if (["黄金", "GOLD", "GLD", "白银", "SILVER"].some((token) => text.includes(token))) return "贵金属";
  if (["债券", "BOND", "SHY", "BIL", "TLT", "IEF"].some((token) => text.includes(token))) return "债券/现金管理";
  if (["NVDA", "AMD", "TSM", "MU", "SMH", "SOX", "PLTR", "AI"].some((token) => text.includes(token))) return "AI/半导体";
  if (["TSLA", "NIO", "LI", "XPEV"].some((token) => text.includes(token))) return "新能源车";
  if (assetType.includes("ETF") || text.includes("ETF")) return "ETF/宽基或主题";
  if ((position.code || "").startsWith("HK.")) return "港股资产";
  return "其他";
}

export function currencyExposure(positions: Position[], dashboard: Dashboard | null) {
  const groups = new Map<string, { currency: string; value: number; count: number }>();
  for (const position of positions) {
    const currency = position.normalized_currency || position.raw_currency || dashboard?.portfolio.base_currency || "UNKNOWN";
    const current = groups.get(currency) ?? { currency, value: 0, count: 0 };
    current.value += Math.max(positionMarketValueBase(position, dashboard), 0);
    current.count += 1;
    groups.set(currency, current);
  }
  return Array.from(groups.values()).sort((a, b) => b.value - a.value);
}

export function profitLossDistribution(positions: Position[], dashboard: Dashboard | null) {
  const groups = [
    { label: "盈利", value: 0, count: 0 },
    { label: "亏损", value: 0, count: 0 },
    { label: "持平", value: 0, count: 0 },
  ];
  for (const position of positions) {
    const target = position.profit_loss_ratio > 0.005 ? groups[0] : position.profit_loss_ratio < -0.005 ? groups[1] : groups[2];
    target.value += Math.max(positionMarketValueBase(position, dashboard), 0);
    target.count += 1;
  }
  return groups.filter((item) => item.count > 0 && item.value > 0);
}

export function tradeReviewPieData(tradeReviews: TradeReviewList | null, key: "result_label" | "discipline_label"): PieDatum[] {
  const groups = new Map<string, number>();
  for (const item of tradeReviews?.items ?? []) {
    const label = item[key] || "未分类";
    groups.set(label, (groups.get(label) ?? 0) + 1);
  }
  return Array.from(groups.entries()).map(([label, value]) => ({ id: label, label, value, displayValue: `${formatCount(value)} 笔`, meta: "交易复盘" })).sort((a, b) => b.value - a.value);
}

export function tradeReviewBarData(tradeReviews: TradeReviewList | null, key: "result_label" | "discipline_label"): BarDatum[] {
  const groups = new Map<string, number>();
  for (const item of tradeReviews?.items ?? []) {
    const label = item[key] || "未分类";
    groups.set(label, (groups.get(label) ?? 0) + 1);
  }
  const total = Array.from(groups.values()).reduce((sum, value) => sum + value, 0) || 1;
  return Array.from(groups.entries())
    .map(([label, value]) => ({
      label,
      value,
      displayValue: `${formatPercent(value / total)} · ${formatCount(value)} 笔`,
    }))
    .sort((a, b) => b.value - a.value);
}

export function buildFocusPositions(positions: Position[], cards: DecisionCard[], dashboard: Dashboard | null) {
  const cardPriority = new Map(cards.map((card) => [card.code, cardPriorityScore(card)]));
  return [...positions].sort((a, b) => {
    const left = (a.position_weight || 0) * 3 + Math.max(0, -(a.profit_loss_ratio || 0)) + (cardPriority.get(a.code) ?? 0);
    const right = (b.position_weight || 0) * 3 + Math.max(0, -(b.profit_loss_ratio || 0)) + (cardPriority.get(b.code) ?? 0);
    if (right !== left) return right - left;
    return positionMarketValueBase(b, dashboard) - positionMarketValueBase(a, dashboard);
  });
}

export function cardPriorityScore(card: DecisionCard) {
  const priorityScore = card.priority === "high" || card.priority === "高" ? 0.5 : card.priority === "medium" || card.priority === "中" ? 0.25 : 0;
  const actionScore = card.action_required ? 0.5 : 0;
  return priorityScore + actionScore;
}

export function aiRecommendationFor(code: string, cards: DecisionCard[]) {
  const card = cards.find((item) => item.code === code);
  if (!card) return <span className="muted-text">待生成</span>;
  return <Tag color={card.action_required ? "orange" : "arcoblue"}>{card.recommendation || card.status || "查看建议"}</Tag>;
}

export function scopePositions(positions: Position[], selectedAccount: string) {
  if (selectedAccount === "all") return positions;
  return positions
    .filter((item) => item.account_id === selectedAccount || (item.account_positions ?? []).some((account) => account.account_id === selectedAccount))
    .map((item) => {
      if (item.account_id === selectedAccount) return item;
      const accountPosition = item.account_positions?.find((account) => account.account_id === selectedAccount);
      if (!accountPosition) return item;
      return {
        ...item,
        account_id: selectedAccount,
        quantity: accountPosition.quantity,
        normalized_market_value: accountPosition.market_value,
        position_weight: accountPosition.weight,
        account_count: undefined,
        account_positions: undefined,
      };
    });
}

export function scopeDashboard(dashboard: Dashboard | null, scopedPositions: Position[]): Dashboard | null {
  if (!dashboard) return dashboard;
  const scopedCodes = new Set(scopedPositions.map((item) => item.code));
  const scopedAccounts = new Set(scopedPositions.map((item) => item.account_id));
  const actionCards = dashboard.action_cards.filter((card) => scopedCodes.has(card.code));
  const portfolioAccounts = dashboard.portfolio.accounts.filter((account) => scopedAccounts.has(account.account_id) || dashboard.portfolio.account_id === "all");
  const positionValue = scopedPositions.reduce((sum, item) => sum + Math.max(item.normalized_market_value, 0), 0);
  const maxPositionWeight = Math.max(...scopedPositions.map((item) => item.position_weight), 0);
  return {
    ...dashboard,
    action_cards: actionCards,
    portfolio: {
      ...dashboard.portfolio,
      account_count: dashboard.portfolio.account_id === "all" ? dashboard.portfolio.account_count : Math.max(portfolioAccounts.length, scopedAccounts.size),
      position_count: scopedPositions.length,
      total_position_value: dashboard.portfolio.account_id === "all" ? dashboard.portfolio.total_position_value : positionValue,
      max_position_weight: maxPositionWeight,
      accounts: portfolioAccounts,
    },
    decision_card_state: {
      ...dashboard.decision_card_state,
      total_positions: scopedPositions.length,
      card_count: actionCards.length,
      missing_codes: dashboard.decision_card_state.missing_codes.filter((code) => scopedCodes.has(code)),
      stale_codes: dashboard.decision_card_state.stale_codes.filter((code) => scopedCodes.has(code)),
      legacy_codes: dashboard.decision_card_state.legacy_codes.filter((code) => scopedCodes.has(code)),
      needs_generation: dashboard.decision_card_state.needs_generation && (
        dashboard.decision_card_state.missing_codes.some((code) => scopedCodes.has(code)) ||
        dashboard.decision_card_state.stale_codes.some((code) => scopedCodes.has(code)) ||
        dashboard.decision_card_state.legacy_codes.some((code) => scopedCodes.has(code))
      ),
    },
    empty: scopedPositions.length === 0,
  };
}

export function scopeTradeReviews(tradeReviews: TradeReviewList | null, selectedAccount: string): TradeReviewList | null {
  if (!tradeReviews || selectedAccount === "all") return tradeReviews;
  const items = tradeReviews.items.filter((item) => item.account_id === selectedAccount);
  return {
    ...tradeReviews,
    empty: items.length === 0,
    summary: tradeReviewSummary(items),
    items,
  };
}

export function tradeReviewSummary(items: TradeReview[]) {
  const riskLabels = new Set(["卖飞", "买到短线高位", "买后承压"]);
  const planLabels = new Set(["计划内买入", "计划内卖出"]);
  return {
    trade_count: items.length,
    waiting_count: items.filter((item) => item.result_label === "等待验证").length,
    risk_count: items.filter((item) => riskLabels.has(item.result_label)).length,
    planned_count: items.filter((item) => planLabels.has(item.result_label) || ["已补交易理由", "有建议记录"].includes(item.discipline_label)).length,
    missing_note_count: items.filter((item) => !item.user_note).length,
  };
}

export function layerOverview(positions: Position[], dashboard: Dashboard | null) {
  const groups = new Map<string, { layer: string; count: number; value: number; positions: Position[] }>();
  for (const item of positions) {
    const layer = item.position_layer || "未分层";
    const current = groups.get(layer) ?? { layer, count: 0, value: 0, positions: [] };
    current.count += 1;
    current.value += Math.max(positionMarketValueBase(item, dashboard), 0);
    current.positions.push(item);
    groups.set(layer, current);
  }
  return [...groups.values()]
    .map((item) => ({
      layer: item.layer,
      count: item.count,
      value: item.value,
      names: item.positions
        .sort((a, b) => Math.max(positionMarketValueBase(b, dashboard), 0) - Math.max(positionMarketValueBase(a, dashboard), 0))
        .map((position) => position.name || position.code),
    }))
    .filter((item) => item.count > 0 && item.value > 0)
    .sort((a, b) => {
      const layerOrderA = layers.indexOf(a.layer);
      const layerOrderB = layers.indexOf(b.layer);
      if (layerOrderA !== -1 || layerOrderB !== -1) {
        return (layerOrderA === -1 ? Number.MAX_SAFE_INTEGER : layerOrderA) - (layerOrderB === -1 ? Number.MAX_SAFE_INTEGER : layerOrderB);
      }
      return b.value - a.value;
    });
}

export function accountExposure(accounts: AccountSummary[]) {
  const groups = accounts
    .map((account) => ({
      account_id: account.account_id,
      label: account.display_name || account.account_id,
      source_name: account.source_name,
      value: Math.max(account.display_total_assets ?? account.total_assets, 0),
    }))
    .filter((item) => item.value > 0);
  const total = groups.reduce((sum, item) => sum + item.value, 0) || 1;
  return groups.map((item) => ({ ...item, weight: item.value / total })).sort((a, b) => b.value - a.value);
}

export function marketExposure(positions: Position[], dashboard: Dashboard | null) {
  const groups = new Map<string, { market: string; value: number; count: number }>();
  for (const item of positions) {
    const market = item.market || "UNKNOWN";
    const current = groups.get(market) ?? { market, value: 0, count: 0 };
    current.value += Math.max(positionMarketValueBase(item, dashboard), 0);
    current.count += 1;
    groups.set(market, current);
  }
  const total = Array.from(groups.values()).reduce((sum, item) => sum + Math.max(item.value, 0), 0) || 1;
  return Array.from(groups.values()).map((item) => ({ ...item, weight: item.value / total })).sort((a, b) => b.value - a.value);
}

export function positionMarketValueBase(position: Position, dashboard: Dashboard | null) {
  if (position.account_positions?.length) {
    return position.account_positions.reduce((sum, item) => sum + convertToBase(item.market_value, item.currency, dashboard), 0);
  }
  return convertToBase(position.normalized_market_value, position.normalized_currency, dashboard);
}

export function displayCurrencyOptions(dashboard: Dashboard | null, positions: Position[]) {
  const currencies = new Set<string>();
  const baseCurrency = dashboard?.portfolio.base_currency;
  if (baseCurrency) currencies.add(baseCurrency);
  for (const currency of dashboard?.portfolio.display_currencies ?? []) {
    if (currency) currencies.add(currency);
  }
  for (const currency of Object.keys(dashboard?.portfolio.display_rates ?? {})) {
    if (currency) currencies.add(currency);
  }
  for (const position of positions) {
    if (position.raw_currency) currencies.add(position.raw_currency);
    if (position.normalized_currency) currencies.add(position.normalized_currency);
    for (const accountPosition of position.account_positions ?? []) {
      if (accountPosition.currency) currencies.add(accountPosition.currency);
    }
  }
  const preferredOrder = [baseCurrency, "CNY", "USD", "HKD", "CNH"].filter(Boolean) as string[];
  return Array.from(currencies).sort((a, b) => {
    const left = preferredOrder.indexOf(a);
    const right = preferredOrder.indexOf(b);
    if (left !== -1 || right !== -1) return (left === -1 ? preferredOrder.length : left) - (right === -1 ? preferredOrder.length : right);
    return a.localeCompare(b);
  });
}

export function displayRateFor(dashboard: Dashboard | null, activeCurrency: string) {
  const baseCurrency = dashboard?.portfolio.base_currency || activeCurrency || "CNY";
  if (!activeCurrency || activeCurrency === baseCurrency) return 1;
  return dashboard?.portfolio.display_rates?.[activeCurrency] ?? 1;
}

export function convertToBase(value: number, currency: string | undefined, dashboard: Dashboard | null) {
  const baseCurrency = dashboard?.portfolio.base_currency || currency || "CNY";
  const targetCurrency = currency || baseCurrency;
  if (targetCurrency === baseCurrency) return value;
  const rate = dashboard?.portfolio.display_rates?.[targetCurrency];
  return rate ? value / rate : value;
}

export function marketName(market: string) {
  const names: Record<string, string> = {
    US: "美股",
    HK: "港股",
    CN: "A股",
    SH: "沪市",
    SZ: "深市",
  };
  return names[market] ?? (market || "未识别市场");
}

export function formatMoney(value: number, currency?: string) {
  const amount = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
  const text = currency ? `${amount} ${currency}` : amount;
  return maskAssetText(text);
}

export function convertCurrency(value: number, rate: number) {
  return value * rate;
}

export function currencyNote(baseCurrency: string, displayCurrency: string, displayRate: number, meta?: Dashboard["portfolio"]["display_rate_meta"][string]) {
  if (!baseCurrency || !displayCurrency) return "完成同步后显示账户币种。";
  if (baseCurrency === displayCurrency) return `当前按账户基准币种 ${baseCurrency} 展示。`;
  const source = meta?.source === "frankfurter" ? "Frankfurter" : meta?.source || "汇率源";
  const stale = meta?.is_stale ? " · 使用缓存汇率" : "";
  const fetchedAt = meta?.fetched_at ? ` · ${formatDate(meta.fetched_at)} 更新` : "";
  return `当前按 ${baseCurrency} -> ${displayCurrency} 汇率 ${maskAssetText(displayRate.toFixed(6))} 展示 · ${source}${fetchedAt}${stale}`;
}

export function sourceLabel(source: string) {
  const names: Record<string, string> = {
    futu: "Futu",
    alipay: "支付宝",
    elebank: "Elebank",
    citic_ths: "中信证券",
    manual: "手动账户",
    excel: "Excel",
    file: "文件",
  };
  return names[source] ?? source;
}

export function isFutuAccount(account: AccountSummary | null | undefined) {
  return Boolean(account?.broker_provider === "futu" || account?.source_name === "futu");
}

export function accountSourceKind(account: AccountSummary) {
  return isFutuAccount(account) ? "futu" : "manual";
}

export function accountSourceLabel(account: AccountSummary) {
  return isFutuAccount(account) ? "Futu · OpenD" : "手动导入";
}

export function accountImportCapabilityLabel(account: AccountSummary) {
  return isFutuAccount(account) ? "只读 API" : "Excel / 文件";
}

export function accountName(accounts: AccountSummary[], accountId: string) {
  if (accountId === "all") return "全部账户";
  const account = accounts.find((item) => item.account_id === accountId);
  return account?.display_name || accountId;
}

export function positionCurrencyLabel(position: Position) {
  const accountCurrency = position.normalized_currency || "未标记";
  const rawCurrency = position.raw_currency || "未标记";
  if (rawCurrency === accountCurrency) return `账户币种 ${accountCurrency}，原始币种相同`;
  return `账户币种 ${accountCurrency}，原始币种 ${rawCurrency}`;
}

export function exchangeRateLabel(position: Position) {
  if (!position.raw_currency || position.raw_currency === position.normalized_currency) {
    return `市值口径：按账户币种 ${position.normalized_currency || "未标记"} 展示，原始币种相同。`;
  }
  if (position.exchange_rate_to_base) {
    return `市值口径：原始币种 ${position.raw_currency} 按 ${maskAssetText(position.exchange_rate_to_base.toFixed(6))} 换算为账户币种 ${position.normalized_currency}。`;
  }
  return `市值口径：原始币种为 ${position.raw_currency}，账户币种为 ${position.normalized_currency}；当前同步数据未返回可用汇率。`;
}

export function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatOptionalPercent(value?: number | null) {
  if (value === null || value === undefined) return "待验证";
  return formatPercent(value);
}

export function formatPrice(value?: number | null) {
  if (value === null || value === undefined) return "待验证";
  return maskAssetText(new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 }).format(value));
}

export function formatCount(value: number) {
  return maskAssetText(new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value));
}

export function maskAssetText(text: string) {
  if (!assetMaskEnabled) return text;
  return text.replace(/-?\d[\d,]*(?:\.\d+)?/g, "***");
}

export function sideName(side: string) {
  const upper = side.toUpperCase();
  if (upper.includes("BUY")) return "买入";
  if (upper.includes("SELL")) return "卖出";
  return side || "成交";
}

export function tradeReviewClass(label: string) {
  if (["卖飞", "买到短线高位"].includes(label)) return "risk";
  if (["买后承压", "过早卖出待确认"].includes(label)) return "watch";
  if (["计划内买入", "计划内卖出"].includes(label)) return "planned";
  return "waiting";
}

export function copyIntentTags(tags?: TradeIntentTags): TradeIntentTags {
  return {
    trend: [...(tags?.trend ?? [])],
    market: [...(tags?.market ?? [])],
    fundamental: [...(tags?.fundamental ?? [])],
    emotion: [...(tags?.emotion ?? [])],
  };
}

export function toggleIntentTag(tags: TradeIntentTags, key: keyof TradeIntentTags, tag: string) {
  const current = tags[key] ?? [];
  const next = current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag];
  return { ...tags, [key]: next };
}

export function hasIntent(item: TradeReview) {
  return Boolean(item.user_note || intentTagGroups.some((group) => item.intent_tags?.[group.key]?.length));
}

export function formatDate(value?: string | null) {
  if (!value) return "无";
  return `${parseBackendDate(value).toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" })} 北京时间`;
}

export function workflowStatusLabel(status: AIWorkflowRun["status"]) {
  if (status === "completed") return "已完成";
  if (status === "running" || status === "pending") return "生成中";
  if (status === "failed") return "失败";
  if (status === "cancelled") return "已终止";
  return status;
}

export function parseBackendDate(value: string) {
  const trimmed = value.trim();
  const hasTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(trimmed);
  const normalized = trimmed.includes("T") ? trimmed : trimmed.replace(" ", "T");
  return new Date(hasTimezone ? normalized : `${normalized}Z`);
}

export function noticeClass(notice: string, working = false) {
  if (working || notice.includes("正在")) return "working";
  if (notice.includes("成功") || notice.includes("已生成") || notice.includes("已完成")) return "success";
  if (notice.includes("失败") || notice.includes("错误") || notice.includes("不可用") || notice.includes("未启用") || notice.includes("未导入")) return "error";
  return "";
}

export function providerName(provider: string) {
  const names: Record<string, string> = {
    deepseek: "DeepSeek",
    openai: "OpenAI",
    openrouter: "OpenRouter",
    moonshot: "Moonshot / Kimi",
    qwen: "通义千问 Qwen",
    siliconflow: "SiliconFlow",
    zhipu: "智谱 GLM",
    custom_openai_compatible: "自定义兼容接口",
    local: "本地规则",
    local_fallback: "本地降级",
  };
  return names[provider] ?? provider;
}
