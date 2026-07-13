import type { ReactNode } from "react";
import { Card, Empty as ArcoEmpty, Form, Grid, Tag } from "@arco-design/web-react";

const { Row, Col } = Grid;

export function PageContainer({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`page-container ${className}`.trim()}>{children}</div>;
}

export function MetricCard({ label, value, extra }: { label: string; value: ReactNode; extra?: ReactNode }) {
  return (
    <Card className="metric-card" bordered={false}>
      <div className="metric-card-head">
        <span>{label}</span>
        {extra}
      </div>
      <strong>{value}</strong>
    </Card>
  );
}

export function QueryToolbar({ children }: { children: ReactNode }) {
  return <div className="query-toolbar">{children}</div>;
}

export function FormDrawer({ children }: { children: ReactNode }) {
  return <Form layout="vertical" className="form-drawer-body">{children}</Form>;
}

export function StatusTag({ status, children }: { status?: string; children: ReactNode }) {
  const color = status === "success" || status === "completed" || status === "fresh" ? "green"
    : status === "danger" || status === "failed" || status === "stale" ? "red"
      : status === "warning" || status === "running" || status === "pending" ? "orange"
        : "arcoblue";
  return <Tag color={color}>{children}</Tag>;
}

export function EmptyState({ title, body }: { title: string; body?: string }) {
  return <ArcoEmpty className="empty-state" description={<span>{title}{body ? <small>{body}</small> : null}</span>} />;
}

export function ResponsiveGrid({ children }: { children: ReactNode }) {
  return (
    <Row gutter={[16, 16]} className="responsive-grid">
      {Array.isArray(children) ? children.map((child, index) => (
        <Col key={index} xs={24} sm={12} lg={6}>{child}</Col>
      )) : <Col xs={24}>{children}</Col>}
    </Row>
  );
}
