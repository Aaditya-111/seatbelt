"use client";

import React from "react";
import { PaymentRecord, ChainStatus } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { formatMoney, formatDate, shortId } from "@/lib/api-client";
import {
  ShieldCheckIcon,
  LayersIcon,
  ScaleIcon,
  UsersIcon,
  AlertTriangleIcon,
  ArrowRightIcon,
} from "@/components/ui/Icons";

interface OverviewViewProps {
  payments: PaymentRecord[];
  auditHealth: ChainStatus | null;
  onNavigate: (tab: string) => void;
  onOpenIssueMandate: () => void;
}

export function OverviewView({
  payments,
  auditHealth,
  onNavigate,
  onOpenIssueMandate,
}: OverviewViewProps) {
  // Compute real metrics from backend data
  const totalCount = payments.length;
  const capturedCount = payments.filter((p) => p.status === "captured").length;
  const pendingApprovalCount = payments.filter((p) => p.status === "pending_approval").length;
  const awaitingPayerCount = payments.filter((p) => p.status === "awaiting_payer").length;
  const deniedCount = payments.filter((p) => p.status === "denied" || p.status === "rejected").length;

  const totalSpend = payments
    .filter((p) => p.status === "captured")
    .reduce((sum, p) => sum + (parseFloat(String(p.amount)) || 0), 0);

  const uniqueAgents = Array.from(new Set(payments.map((p) => p.agent_id)));
  const recentPayments = payments.slice(0, 6);

  return (
    <div className="space-y-6">
      {/* Top Metric Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Total Transactions */}
        <Card>
          <div className="flex items-center justify-between text-[#91A09D] mb-2">
            <span className="text-[11px] font-mono uppercase tracking-wider">Total Evaluated</span>
            <LayersIcon className="w-4 h-4 text-[#5F716D]" />
          </div>
          <div className="text-2xl font-bold font-mono text-[#F1F5F4]">{totalCount}</div>
          <div className="text-[11px] text-[#91A09D] mt-1">
            {capturedCount} settled · {deniedCount} denied
          </div>
        </Card>

        {/* Total Volume */}
        <Card>
          <div className="flex items-center justify-between text-[#91A09D] mb-2">
            <span className="text-[11px] font-mono uppercase tracking-wider">Settled Volume</span>
            <span className="text-xs font-mono text-[#16E6A0]">USD</span>
          </div>
          <div className="text-2xl font-bold font-mono text-[#16E6A0]">
            {formatMoney(totalSpend, "USD")}
          </div>
          <div className="text-[11px] text-[#91A09D] mt-1">
            Across {capturedCount} captured payments
          </div>
        </Card>

        {/* Pending Approvals */}
        <Card>
          <div className="flex items-center justify-between text-[#91A09D] mb-2">
            <span className="text-[11px] font-mono uppercase tracking-wider">Pending Approvals</span>
            <span
              className={`w-2 h-2 rounded-full ${
                pendingApprovalCount > 0 ? "bg-[#F59E0B] animate-ping" : "bg-[#5F716D]"
              }`}
            />
          </div>
          <div className="text-2xl font-bold font-mono text-[#FBBF24]">
            {pendingApprovalCount}
          </div>
          <div className="text-[11px] text-[#91A09D] mt-1">
            {awaitingPayerCount > 0 ? `${awaitingPayerCount} awaiting PayPal buyer` : "Human queue clear"}
          </div>
        </Card>

        {/* Active Agents */}
        <Card>
          <div className="flex items-center justify-between text-[#91A09D] mb-2">
            <span className="text-[11px] font-mono uppercase tracking-wider">Active Agents</span>
            <UsersIcon className="w-4 h-4 text-[#5F716D]" />
          </div>
          <div className="text-2xl font-bold font-mono text-[#22D3EE]">
            {uniqueAgents.length}
          </div>
          <div className="text-[11px] text-[#91A09D] mt-1">
            Transacting identities
          </div>
        </Card>
      </div>

      {/* Audit Integrity Banner */}
      <Card variant="elevated">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div
              className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 ${
                auditHealth?.ok
                  ? "bg-[#16E6A0]/10 border-[#16E6A0]/30 text-[#16E6A0]"
                  : auditHealth === null
                  ? "bg-[#151F24] border-[#1E2B27] text-[#91A09D]"
                  : "bg-[#F43F5E]/10 border-[#F43F5E]/30 text-[#FB7185]"
              }`}
            >
              <ShieldCheckIcon className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-[#F1F5F4]">
                  Cryptographic Audit Trail Integrity
                </h3>
                {auditHealth && (
                  <Badge
                    tone={auditHealth.ok ? "emerald" : "rose"}
                    size="sm"
                  >
                    {auditHealth.ok ? "Valid HMAC Chain" : "Integrity Failure"}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-[#91A09D] mt-1">
                {auditHealth
                  ? `Verified ${auditHealth.entries} entries up to head sequence #${auditHealth.head_seq ?? 0}. ${
                      auditHealth.checkpoint_ok ? "External checkpoint signature matches." : "No external checkpoint mismatch."
                    }`
                  : "Audit status not checked yet. Open Integrity page to verify."}
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onNavigate("integrity")}
            icon={<ArrowRightIcon className="w-3.5 h-3.5 ml-1 order-last" />}
          >
            Inspect Chain
          </Button>
        </div>
      </Card>

      {/* Middle Grid: Recent Transactions & Policy Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Recent Transactions (8 cols) */}
        <div className="lg:col-span-8">
          <Card>
            <CardHeader
              title="Recent Evaluated Transactions"
              subtitle="Live stream of payments evaluated by the policy engine"
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onNavigate("transactions")}
                  icon={<ArrowRightIcon className="w-3.5 h-3.5 ml-0.5 order-last" />}
                >
                  View All
                </Button>
              }
            />

            {recentPayments.length === 0 ? (
              <EmptyState
                icon={<LayersIcon className="w-5 h-5" />}
                title="No transactions recorded"
                description="The backend database has no payments yet. Submit a test transaction from the Agent Playground or issue an agent mandate."
                action={
                  <Button size="sm" onClick={() => onNavigate("playground")}>
                    Go to Agent Playground
                  </Button>
                }
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#1E2B27] text-[#91A09D] font-mono text-[11px]">
                      <th className="pb-2.5 font-medium">Payment ID</th>
                      <th className="pb-2.5 font-medium">Agent</th>
                      <th className="pb-2.5 font-medium">Payee</th>
                      <th className="pb-2.5 font-medium">Amount</th>
                      <th className="pb-2.5 font-medium">Status</th>
                      <th className="pb-2.5 font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1E2B27]/60">
                    {recentPayments.map((p) => (
                      <tr key={p.payment_id} className="hover:bg-[#151F24]/50 transition-colors">
                        <td className="py-2.5 font-mono text-[#F1F5F4]">
                          {shortId(p.payment_id)}
                        </td>
                        <td className="py-2.5 font-mono text-[#91A09D]">
                          {p.agent_id}
                        </td>
                        <td className="py-2.5 text-[#22D3EE] font-mono">
                          {p.payee}
                        </td>
                        <td className="py-2.5 font-mono font-medium text-[#F1F5F4]">
                          {formatMoney(p.amount, p.currency)}
                        </td>
                        <td className="py-2.5">
                          <Badge status={p.status} size="sm" />
                        </td>
                        <td className="py-2.5 font-mono text-[#5F716D] text-[11px]">
                          {formatDate(p.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        {/* Policy Decision Breakdown & Quick Actions (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          <Card>
            <CardHeader
              title="Decision Distribution"
              subtitle="Verdicts rendered by the policy engine"
            />
            <div className="space-y-3 pt-1">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#16E6A0]" />
                  <span className="text-[#F1F5F4]">Allowed & Settled</span>
                </div>
                <span className="font-mono font-semibold text-[#16E6A0]">{capturedCount}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#FBBF24]" />
                  <span className="text-[#F1F5F4]">Held for Human Review</span>
                </div>
                <span className="font-mono font-semibold text-[#FBBF24]">{pendingApprovalCount}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#FB7185]" />
                  <span className="text-[#F1F5F4]">Denied / Policy Blocked</span>
                </div>
                <span className="font-mono font-semibold text-[#FB7185]">{deniedCount}</span>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-[#1E2B27] space-y-2">
              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start"
                onClick={onOpenIssueMandate}
                icon={<ScaleIcon className="w-3.5 h-3.5 text-[#16E6A0]" />}
              >
                Issue New Agent Mandate
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start"
                onClick={() => onNavigate("benchmarks")}
                icon={<AlertTriangleIcon className="w-3.5 h-3.5 text-[#FBBF24]" />}
              >
                View Adversarial Benchmarks
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
