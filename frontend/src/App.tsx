import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Message } from "@arco-design/web-react";
import { api, AccountSummary, AIAnalysis, AIWorkflowRun, Dashboard, DecisionCard, HealthStatus, NewsItem, Position, Profile, Review, TradeReviewList, WorkspaceMode } from "./api";
import { ProShell } from "./layout/ProShell";
import { PageContainer } from "./components/pro";
import {
  AccountDataPage,
  AdvancedSettingsPage,
  ConfirmDialog,
  CurrencyPill,
  Detail,
  FutuConnectionCard,
  Home,
  Positions,
  ProfilePage,
  ReviewPage,
  displayCurrencyOptions,
  displayRateFor,
  noticeClass,
  scopeDashboard,
  scopePositions,
  scopeTradeReviews,
  setAssetMaskEnabled,
} from "./features/portfolioViews";

const nav = ["首页", "持仓", "复盘", "组合诊断", "账户与数据", "AI与高级设置"];
type AppTheme = "light" | "dark";

type ConfirmOptions = {
  title: string;
  body: string;
  confirmText?: string;
  cancelText?: string;
  tone?: "default" | "danger";
};

function App() {
  const [active, setActive] = useState("首页");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [selectedAccount, setSelectedAccount] = useState("all");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [selectedCode, setSelectedCode] = useState("");
  const [detailReturnTarget, setDetailReturnTarget] = useState("持仓");
  const [detail, setDetail] = useState<{ position: Position; account_positions?: Position[]; cards: DecisionCard[]; news: NewsItem[]; ai_analysis: AIAnalysis | null } | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [tradeReviews, setTradeReviews] = useState<TradeReviewList | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [workflowRuns, setWorkflowRuns] = useState<AIWorkflowRun[]>([]);
  const [profilePageIntent, setProfilePageIntent] = useState<{ kind: "generate" | "open"; runId?: string; requestId: number } | null>(null);
  const [layer, setLayer] = useState("全部");
  const [loading, setLoading] = useState(false);
  const [generatingAi, setGeneratingAi] = useState(false);
  const [refreshingTradeMarketData, setRefreshingTradeMarketData] = useState(false);
  const [notice, setNotice] = useState("");
  const [confirmDialog, setConfirmDialog] = useState<ConfirmOptions | null>(null);
  const confirmResolver = useRef<((value: boolean) => void) | null>(null);
  const [maskAssets, setMaskAssets] = useState(() => localStorage.getItem("mask_assets") === "1");
  const [displayCurrency, setDisplayCurrency] = useState("");
  const [theme, setTheme] = useState<AppTheme>(() => localStorage.getItem("app_theme") === "dark" ? "dark" : "light");
  const [workspace, setWorkspace] = useState<WorkspaceMode>(() => api.workspace());
  const [switchingWorkspace, setSwitchingWorkspace] = useState(false);
  setAssetMaskEnabled(maskAssets);

  const scopedPositions = useMemo(() => scopePositions(positions, selectedAccount), [positions, selectedAccount]);
  const scopedTradeReviews = useMemo(() => scopeTradeReviews(tradeReviews, selectedAccount), [tradeReviews, selectedAccount]);
  const scopedDashboard = useMemo(() => scopeDashboard(dashboard, scopedPositions), [dashboard, scopedPositions]);
  const displayCurrencies = useMemo(() => displayCurrencyOptions(scopedDashboard, scopedPositions), [scopedDashboard, scopedPositions]);
  const baseCurrency = scopedDashboard?.portfolio.base_currency ?? "";
  const activeCurrency = displayCurrency || baseCurrency;
  const displayRate = useMemo(() => displayRateFor(scopedDashboard, activeCurrency), [scopedDashboard, activeCurrency]);
  const emptySystem = Boolean(health?.local_data?.empty && dashboard?.empty && accounts.length === 0 && positions.length === 0);

  async function loadAll() {
    const result = await Promise.allSettled([
      api.health(),
      api.accounts(),
      api.dashboard(selectedAccount),
      api.positions(layer === "全部" ? undefined : layer, selectedAccount),
      api.review(selectedAccount),
      api.tradeReviews(selectedAccount),
      api.profile(selectedAccount),
      api.profileWorkflows(selectedAccount),
    ] as const);
    let [healthData, accountData, dashboardData, positionData, reviewData, tradeReviewData, profileData, workflowData] = result;
    const failedSections: string[] = [];

    if (dashboardData.status === "rejected") {
      dashboardData = await api.dashboard(selectedAccount)
        .then((value) => ({ status: "fulfilled", value }) as PromiseFulfilledResult<Dashboard>)
        .catch((reason) => ({ status: "rejected", reason }) as PromiseRejectedResult);
    }
    if (positionData.status === "rejected") {
      positionData = await api.positions(layer === "全部" ? undefined : layer, selectedAccount)
        .then((value) => ({ status: "fulfilled", value }) as PromiseFulfilledResult<{ items: Position[]; count: number }>)
        .catch((reason) => ({ status: "rejected", reason }) as PromiseRejectedResult);
    }
    if (accountData.status === "rejected") {
      accountData = await api.accounts()
        .then((value) => ({ status: "fulfilled", value }) as PromiseFulfilledResult<{ items: AccountSummary[]; count: number }>)
        .catch((reason) => ({ status: "rejected", reason }) as PromiseRejectedResult);
    }

    if (healthData.status === "fulfilled") setHealth(healthData.value);
    else failedSections.push("健康检查");
    if (accountData.status === "fulfilled") setAccounts(accountData.value.items);
    else failedSections.push("账户");
    if (dashboardData.status === "fulfilled") setDashboard(dashboardData.value);
    else failedSections.push("首页概览");
    if (positionData.status === "fulfilled") {
      setPositions(positionData.value.items);
      if (!selectedCode && positionData.value.items.length) setSelectedCode(positionData.value.items[0].code);
    } else failedSections.push("持仓");
    if (reviewData.status === "fulfilled") setReview(reviewData.value);
    else failedSections.push("复盘");
    if (tradeReviewData.status === "fulfilled") setTradeReviews(tradeReviewData.value);
    else failedSections.push("交易复盘");
    if (profileData.status === "fulfilled") setProfile(profileData.value);
    else failedSections.push("画像");
    if (workflowData.status === "fulfilled") setWorkflowRuns(workflowData.value.items);
    else failedSections.push("诊断报告");

    if (failedSections.length) setNotice(`${failedSections.join("、")}暂时加载失败，已保留可用数据`);
  }

  useEffect(() => {
    loadAll().catch((error) => {
      const message = error instanceof Error ? error.message : "加载失败";
      setNotice(message.includes("暂时加载失败") ? message : `服务未连接：${message}`);
    });
  }, [layer, selectedAccount, workspace]);

  useEffect(() => {
    if (!notice) return;
    const type = noticeClass(notice, false);
    const message = { content: notice, duration: type === "error" ? 6500 : 4200 };
    if (type === "error") Message.error(message);
    else if (type === "success") Message.success(message);
    else if (type === "working") Message.loading(message);
    else Message.info(message);
    const timeout = window.setTimeout(() => setNotice(""), type === "error" ? 6500 : 4200);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  useEffect(() => {
    localStorage.setItem("mask_assets", maskAssets ? "1" : "0");
  }, [maskAssets]);

  useEffect(() => {
    localStorage.setItem("app_theme", theme);
    document.body.dataset.theme = theme;
    if (theme === "dark") document.body.setAttribute("arco-theme", "dark");
    else document.body.removeAttribute("arco-theme");
  }, [theme]);

  useEffect(() => {
    if (!displayCurrency && baseCurrency) setDisplayCurrency(baseCurrency);
    if (displayCurrency && displayCurrencies.length && !displayCurrencies.includes(displayCurrency)) {
      setDisplayCurrency(baseCurrency);
    }
  }, [baseCurrency, displayCurrencies, displayCurrency]);

  useEffect(() => {
    if (!selectedCode) return;
    api.positionDetail(selectedCode, selectedAccount).then(setDetail).catch(() => setDetail(null));
  }, [selectedCode, selectedAccount]);

  function requestConfirm(options: ConfirmOptions) {
    setConfirmDialog(options);
    return new Promise<boolean>((resolve) => {
      confirmResolver.current = resolve;
    });
  }

  function resolveConfirm(value: boolean) {
    confirmResolver.current?.(value);
    confirmResolver.current = null;
    setConfirmDialog(null);
  }

  function toggleWorkspace() {
    const next: WorkspaceMode = workspace === "demo" ? "formal" : "demo";
    setSwitchingWorkspace(true);
    setSelectedAccount("all");
    setSelectedCode("");
    setDetail(null);
    setDashboard(null);
    setPositions([]);
    setAccounts([]);
    api.setWorkspace(next);
    setWorkspace(next);
    setNotice(next === "demo" ? "已进入演示工作区，所有数据均与正式数据隔离" : "已返回正式工作区");
    window.setTimeout(() => setSwitchingWorkspace(false), 450);
  }

  async function refresh() {
    setLoading(true);
    setNotice("正在同步富途数据");
    try {
      const result = await api.manualSync();
      setNotice(`${result.status}：${result.message}`);
      await loadAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "同步失败");
    } finally {
      setLoading(false);
    }
  }

  async function saveLayer(nextLayer: string) {
    if (!detail) return;
    await api.updateLayer(detail.position.code, nextLayer, "用户在工作台手动修正");
    const nextPosition = {
      ...detail.position,
      position_layer: nextLayer,
      layer_source: "manual",
      layer_confidence: "高",
      layer_reason: "用户在工作台手动修正",
    };
    setDetail({
      ...detail,
      position: nextPosition,
      account_positions: detail.account_positions?.map((item) => item.code === detail.position.code ? { ...item, position_layer: nextLayer, layer_source: "manual", layer_confidence: "高", layer_reason: "用户在工作台手动修正" } : item),
    });
    setPositions((items) => items.map((item) => item.code === detail.position.code ? { ...item, position_layer: nextLayer, layer_source: "manual", layer_confidence: "高", layer_reason: "用户在工作台手动修正" } : item));
    setNotice("仓位类型已更新");
  }

  async function refreshTradeReviewMarketData() {
    setRefreshingTradeMarketData(true);
    try {
      const result = await api.refreshTradeReviewMarketData(selectedAccount);
      await loadAll();
      const waitingCount = result.summary?.waiting_count ?? 0;
      setNotice(`复盘行情已刷新，仍待验证 ${waitingCount} 笔`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "复盘行情刷新失败");
    } finally {
      setRefreshingTradeMarketData(false);
    }
  }

  async function generateAiAnalysis() {
    if (!detail) return;
    const consent = await requestConfirm({
      title: "生成 AI 分析",
      body: "将发送该标的的当前持仓、仓位分层、最近 3 天消息面、画像摘要和数据新鲜度给当前启用的大模型生成分析。",
      confirmText: "继续生成",
    });
    if (!consent) {
      setNotice("已取消 AI 分析");
      return;
    }
    setGeneratingAi(true);
    setNotice("正在生成 AI 分析");
    try {
      const result = await api.generateAIAnalysis(detail.position.code, true, selectedAccount);
      setDetail({ ...detail, ai_analysis: result.ai_analysis });
      setNotice(result.ai_analysis.provider === "local" || result.ai_analysis.provider === "local_fallback" ? "未配置可用 AI API，已使用本地规则降级分析" : "AI 分析已生成");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "AI 分析生成失败");
    } finally {
      setGeneratingAi(false);
    }
  }

  const content = useMemo(() => {
    if (active === "首页") return <Home dashboard={scopedDashboard} positions={scopedPositions} tradeReviews={scopedTradeReviews} workflowRuns={workflowRuns} accounts={accounts} selectedAccount={selectedAccount} maskAssets={maskAssets} activeCurrency={activeCurrency} displayRate={displayRate} emptySystem={emptySystem} health={health} onFutuRefresh={async () => { await loadAll(); }} onFutuSync={refresh} onGenerateDiagnosis={() => { setProfilePageIntent({ kind: "generate", requestId: Date.now() }); setActive("组合诊断"); }} onOpenDiagnosisReport={(runId) => { setProfilePageIntent({ kind: "open", runId, requestId: Date.now() }); setActive("组合诊断"); }} onOpenCode={(code) => { setSelectedCode(code); setDetailReturnTarget("首页"); setActive("标的详情"); }} />;
    if (active === "持仓") return <Positions positions={scopedPositions} layer={layer} setLayer={setLayer} accounts={accounts} selectedAccount={selectedAccount} onOpenCode={(code) => { setSelectedCode(code); setDetailReturnTarget("持仓"); setActive("标的详情"); }} />;
    if (active === "复盘") return <ReviewPage review={review} tradeReviews={scopedTradeReviews} selectedAccount={selectedAccount} accounts={accounts} refreshingMarketData={refreshingTradeMarketData} onRefreshMarketData={refreshTradeReviewMarketData} onSaveIntent={async (reviewId, note, tags, plan) => { await api.updateTradeReviewIntent(reviewId, note, tags, plan); await loadAll(); }} />;
    if (active === "组合诊断") return <ProfilePage profile={profile} positions={scopedPositions} selectedAccount={selectedAccount} accounts={accounts} health={health} setNotice={setNotice} requestConfirm={requestConfirm} homeIntent={profilePageIntent} onHomeIntentHandled={() => setProfilePageIntent(null)} onWorkflowRunsChanged={setWorkflowRuns} />;
    if (active === "标的详情") return <Detail detail={detail} selectedAccount={selectedAccount} onSaveLayer={saveLayer} onGenerateAi={generateAiAnalysis} generatingAi={generatingAi} setDetail={setDetail} setNotice={setNotice} />;
    if (active === "账户与数据") return <AccountDataPage accounts={accounts} health={health} emptySystem={emptySystem} onChanged={loadAll} onImported={async () => { await loadAll(); setNotice("账户数据已导入"); }} setNotice={setNotice} requestConfirm={requestConfirm} onRefresh={refresh} onRefreshHealth={loadAll} loading={loading} />;
    return <AdvancedSettingsPage health={health} setNotice={setNotice} requestConfirm={requestConfirm} onDelete={async () => { await api.deleteLocalData(); setNotice("本地数据已删除"); await loadAll(); }} />;
  }, [active, dashboard, scopedDashboard, accounts, selectedAccount, health, positions, scopedPositions, review, scopedTradeReviews, profile, workflowRuns, profilePageIntent, layer, detail, selectedCode, loading, generatingAi, refreshingTradeMarketData, maskAssets, activeCurrency, displayRate, emptySystem]);

  const showPortfolioHeaderControls = ["首页", "持仓", "复盘"].includes(active);

  const headerExtra = showPortfolioHeaderControls ? (
    <>
      <Button className="pro-mask-assets-button" onClick={() => setMaskAssets(!maskAssets)}>{maskAssets ? "显示资产" : "隐藏资产"}</Button>
      <CurrencyPill currencies={displayCurrencies} activeCurrency={activeCurrency} setDisplayCurrency={setDisplayCurrency} />
    </>
  ) : null;

  return (
    <>
      <div className={`app-theme app-theme-${theme}`}>
        <ProShell
          active={active}
          navItems={nav}
          selectedMenuKey={active === "标的详情" ? detailReturnTarget : active}
          detailReturnTarget={detailReturnTarget}
          accounts={accounts}
          selectedAccount={selectedAccount}
          showAccountSwitcher={showPortfolioHeaderControls}
          headerExtra={headerExtra}
          theme={theme}
          onToggleTheme={() => setTheme((current) => current === "dark" ? "light" : "dark")}
          onNavigate={setActive}
          onBack={() => setActive(detailReturnTarget)}
          onAccountChange={setSelectedAccount}
          workspace={workspace}
          switchingWorkspace={switchingWorkspace}
          onToggleWorkspace={toggleWorkspace}
        >
          <PageContainer>{content}</PageContainer>
        </ProShell>
        {confirmDialog ? <ConfirmDialog options={confirmDialog} onResolve={resolveConfirm} /> : null}
      </div>
    </>
  );
}

export default App;
