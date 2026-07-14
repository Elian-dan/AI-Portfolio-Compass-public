import type { ReactNode } from "react";
import { Breadcrumb, Button, Layout, Menu, Select, Space, Tooltip } from "@arco-design/web-react";
import {
  IconCompass,
  IconDashboard,
  IconHome,
  IconMoon,
  IconRobot,
  IconSettings,
  IconStorage,
  IconSun,
} from "@arco-design/web-react/icon";
import type { AccountSummary, WorkspaceMode } from "../api";

const { Header, Sider, Content } = Layout;

const pageIconMap: Record<string, ReactNode> = {
  首页: <IconHome />,
  持仓: <IconCompass />,
  复盘: <IconDashboard />,
  组合诊断: <IconRobot />,
  账户与数据: <IconStorage />,
  AI与高级设置: <IconSettings />,
  标的详情: <IconCompass />,
  工作台: <IconHome />,
};

function pageLabel(label: string) {
  return (
    <span className="page-label">
      <span className="page-label-icon">{pageIconMap[label] || <IconDashboard />}</span>
      <span>{label}</span>
    </span>
  );
}

type ProShellProps = {
  active: string;
  navItems: string[];
  selectedMenuKey: string;
  detailReturnTarget: string;
  accounts: AccountSummary[];
  selectedAccount: string;
  showAccountSwitcher: boolean;
  headerExtra?: ReactNode;
  theme: "light" | "dark";
  children: ReactNode;
  onToggleTheme: () => void;
  onNavigate: (page: string) => void;
  onBack: () => void;
  onAccountChange: (accountId: string) => void;
  workspace: WorkspaceMode;
  switchingWorkspace?: boolean;
  onToggleWorkspace: () => void;
};

export function ProShell({
  active,
  navItems,
  selectedMenuKey,
  detailReturnTarget,
  accounts,
  selectedAccount,
  showAccountSwitcher,
  headerExtra,
  theme,
  children,
  onToggleTheme,
  onNavigate,
  onBack,
  onAccountChange,
  workspace,
  switchingWorkspace = false,
  onToggleWorkspace,
}: ProShellProps) {
  const demoMode = workspace === "demo";
  const crumbs = active === "标的详情"
    ? [{ label: "工作台", target: "首页" }, { label: detailReturnTarget, target: detailReturnTarget }, { label: active }]
    : [{ label: "工作台", target: "首页" }, { label: active }];

  return (
    <Layout className="pro-shell">
      <Sider className="pro-sider" width={216}>
        <div className="pro-brand">
          <strong>AI Portfolio Compass</strong>
          <span>AI持仓罗盘</span>
        </div>
        <Menu
          className="pro-menu"
          selectedKeys={[selectedMenuKey]}
          onClickMenuItem={(key) => onNavigate(String(key))}
        >
          {navItems.map((item) => (
            <Menu.Item key={item}>{pageLabel(item)}</Menu.Item>
          ))}
        </Menu>
      </Sider>
      <Layout className="pro-main">
        <Header className="pro-header">
          <div className="pro-header-main">
            <Breadcrumb className="pro-breadcrumb">
              {crumbs.map((crumb, index) => (
                <Breadcrumb.Item key={`${crumb.label}-${index}`}>
                  {crumb.target && index !== crumbs.length - 1 ? (
                    <Button type="text" size="mini" onClick={() => onNavigate(crumb.target!)}>
                      {pageLabel(crumb.label)}
                    </Button>
                  ) : pageLabel(crumb.label)}
                </Breadcrumb.Item>
              ))}
            </Breadcrumb>
          </div>
          <Space size={12} className="pro-header-actions">
            <Tooltip content={demoMode ? "切换到你的正式数据" : "进入隔离的演示工作区"}>
              <Button
                className={`workspace-mode-toggle ${demoMode ? "is-demo" : "is-formal"}`}
                loading={switchingWorkspace}
                aria-label={demoMode ? "当前为演示模式，点击切换到正式模式" : "当前为正式模式，点击切换到演示模式"}
                onClick={onToggleWorkspace}
              >
                {demoMode ? "演示模式" : "正式模式"}
              </Button>
            </Tooltip>
            {headerExtra}
            {showAccountSwitcher ? (
              <Select
                className="pro-account-select"
                value={selectedAccount}
                onChange={(value) => onAccountChange(String(value))}
                triggerProps={{ autoAlignPopupWidth: false }}
              >
                <Select.Option value="all">全部账户</Select.Option>
                {accounts.map((account) => (
                  <Select.Option key={account.account_id} value={account.account_id}>
                    {account.display_name || account.account_id}
                  </Select.Option>
                ))}
              </Select>
            ) : null}
            {active === "标的详情" ? <Button onClick={onBack}>返回{detailReturnTarget}</Button> : null}
            <Tooltip content={theme === "dark" ? "切换浅色模式" : "切换深色模式"}>
              <Button
                className="pro-theme-toggle"
                type="secondary"
                shape="circle"
                icon={theme === "dark" ? <IconSun /> : <IconMoon />}
                aria-label={theme === "dark" ? "切换浅色模式" : "切换深色模式"}
                onClick={onToggleTheme}
              />
            </Tooltip>
          </Space>
        </Header>
        {demoMode ? <div className="demo-mode-banner">演示模式 · 当前使用的是隔离的虚构数据，不会写入正式知识库</div> : null}
        <Content className="pro-content">
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}
