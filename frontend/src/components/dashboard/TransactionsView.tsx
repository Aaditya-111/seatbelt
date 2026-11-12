"use client";

import React, { useState } from "react";
import { PaymentRecord } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { retryPayment, formatMoney, formatDate, shortId } from "@/lib/api-client";
import { LayersIcon, SearchIcon, RefreshCwIcon, ExternalLinkIcon } from "@/components/ui/Icons";

interface TransactionsViewProps {
  payments: PaymentRecord[];
  onRefresh: () => void;
}

export function TransactionsView({ payments, onRefresh }: TransactionsViewProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedTx, setSelectedTx] = useState<PaymentRecord | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryMessage, setRetryMessage] = useState("");

  const filteredPayments = payments.filter((p) => {
    // Status filter
    if (statusFilter !== "all" && p.status !== statusFilter) {
      return false;
    }
    // Search query
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      p.payment_id.toLowerCase().includes(q) ||
      p.request_id.toLowerCase().includes(q) ||
      p.agent_id.toLowerCase().includes(q) ||
      p.payee.toLowerCase().includes(q) ||
      p.description.toLowerCase().includes(q)
    );
  });

  const handleRetry = async (paymentId: string) => {
    setRetrying(true);
    setRetryMessage("");
    try {
      const updated = await retryPayment(paymentId);
      setSelectedTx(updated);
      setRetryMessage("Payment retry initiated successfully.");
      onRefresh();
    } catch (err) {
      setRetryMessage(err instanceof Error ? err.message : "Retry failed.");
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Filter and Search Bar */}
      <Card>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="relative flex-1">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by Payment ID, Request ID, Agent, or Payee..."
              className="w-full px-3 py-2 pl-9 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
            />
            <SearchIcon className="w-4 h-4 text-[#5F716D] absolute left-3 top-2.5" />
          </div>

          <div className="flex items-center gap-2 overflow-x-auto">
            {["all", "captured", "pending_approval", "awaiting_payer", "denied", "rejected", "failed"].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`text-[11px] px-2.5 py-1.5 rounded-md font-mono transition-colors whitespace-nowrap ${
                  statusFilter === st
                    ? "bg-[#151F24] text-[#16E6A0] border border-[#1E2B27] font-semibold"
                    : "text-[#91A09D] hover:text-[#F1F5F4] hover:bg-[#11181D]"
                }`}
              >
                {st.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* Transactions Table */}
      <Card>
        <CardHeader
          title={`Evaluated Transactions (${filteredPayments.length})`}
          subtitle="Complete audit record of agent payment requests"
        />

        {filteredPayments.length === 0 ? (
          <EmptyState
            icon={<LayersIcon className="w-5 h-5" />}
            title="No matching transactions"
            description={
              payments.length === 0
                ? "No payments exist in the store yet. Submit a test transaction from the Agent Playground."
                : "No transactions matched your search or status filter."
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
                  <th className="pb-2.5 font-medium">Channel</th>
                  <th className="pb-2.5 font-medium">Status</th>
                  <th className="pb-2.5 font-medium">Timestamp</th>
                  <th className="pb-2.5 font-medium text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2B27]/60">
                {filteredPayments.map((p) => (
                  <tr
                    key={p.payment_id}
                    className="hover:bg-[#151F24]/50 transition-colors cursor-pointer"
                    onClick={() => setSelectedTx(p)}
                  >
                    <td className="py-2.5 font-mono font-medium text-[#F1F5F4]">
                      {shortId(p.payment_id)}
                    </td>
                    <td className="py-2.5 font-mono text-[#91A09D]">
                      {p.agent_id}
                    </td>
                    <td className="py-2.5 font-mono text-[#22D3EE]">
                      {p.payee}
                    </td>
                    <td className="py-2.5 font-mono font-semibold text-[#F1F5F4]">
                      {formatMoney(p.amount, p.currency)}
                    </td>
                    <td className="py-2.5 font-mono text-[#5F716D] uppercase text-[10px]">
                      {p.payment_channel ?? "executor"}
                    </td>
                    <td className="py-2.5">
                      <Badge status={p.status} size="sm" />
                    </td>
                    <td className="py-2.5 font-mono text-[#5F716D] text-[11px]">
                      {formatDate(p.created_at)}
                    </td>
                    <td className="py-2.5 text-right font-mono text-[11px] text-[#16E6A0]">
                      Inspect →
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Transaction Detail Modal */}
      <Modal
        isOpen={selectedTx !== null}
        onClose={() => {
          setSelectedTx(null);
          setRetryMessage("");
        }}
        title="Transaction Record Details"
        description="Inspect complete policy engine verdict and payment lifecycle metadata"
        maxWidth="lg"
      >
        {selectedTx && (
          <div className="space-y-4 pt-1">
            {retryMessage && (
              <div className="p-3 rounded-md bg-[#16E6A0]/10 border border-[#16E6A0]/20 text-[#16E6A0] text-xs">
                {retryMessage}
              </div>
            )}

            {/* Status and Summary Header */}
            <div className="flex items-center justify-between p-3.5 rounded-lg bg-[#090D10] border border-[#1E2B27]">
              <div>
                <span className="text-[10px] font-mono text-[#91A09D] uppercase block">
                  Amount Requested
                </span>
                <span className="text-xl font-bold font-mono text-[#16E6A0]">
                  {formatMoney(selectedTx.amount, selectedTx.currency)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Badge status={selectedTx.status} size="md" />
              </div>
            </div>

            {/* Core Attributes Grid */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] space-y-1">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Payment ID</span>
                <span className="font-mono text-[#F1F5F4] break-all">{selectedTx.payment_id}</span>
              </div>
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] space-y-1">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Request ID</span>
                <span className="font-mono text-[#F1F5F4] break-all">{selectedTx.request_id}</span>
              </div>
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] space-y-1">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Agent Identity</span>
                <span className="font-mono text-[#F1F5F4]">{selectedTx.agent_id}</span>
              </div>
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] space-y-1">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Payee Merchant</span>
                <span className="font-mono text-[#22D3EE]">{selectedTx.payee}</span>
              </div>
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] space-y-1">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Mandate Token ID</span>
                <span className="font-mono text-[#91A09D]">{selectedTx.mandate_id}</span>
              </div>
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] space-y-1">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Payment Channel</span>
                <span className="font-mono text-[#F1F5F4] uppercase">{selectedTx.payment_channel ?? "executor"}</span>
              </div>
            </div>

            {/* Policy Verdict and Reasons */}
            <div className="p-3.5 rounded-lg bg-[#090D10] border border-[#1E2B27] space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-[#91A09D] uppercase">Policy Verdict</span>
                <Badge status={selectedTx.verdict} size="sm" />
              </div>
              {selectedTx.reasons && selectedTx.reasons.length > 0 ? (
                <div className="space-y-1 pt-1">
                  {selectedTx.reasons.map((r, i) => (
                    <div key={i} className="text-xs flex items-start gap-1.5">
                      <span className="text-[#16E6A0] font-mono">•</span>
                      <span className="text-[#91A09D]">{r.message}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[11px] text-[#5F716D]">No special policy alerts.</div>
              )}
            </div>

            {/* Provider Rail Details (PayPal) */}
            {selectedTx.payment_channel === "paypal" && (
              <div className="p-3.5 rounded-lg bg-[#090D10] border border-[#1E2B27] space-y-2 text-xs">
                <div className="text-[10px] font-mono text-[#91A09D] uppercase">
                  PayPal Rail Metadata
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                  <div>
                    <span className="text-[#5F716D]">Order ID: </span>
                    <span className="text-[#F1F5F4]">{selectedTx.paypal_order_id ?? "—"}</span>
                  </div>
                  <div>
                    <span className="text-[#5F716D]">Capture ID: </span>
                    <span className="text-[#16E6A0]">{selectedTx.paypal_capture_id ?? "—"}</span>
                  </div>
                </div>
                {selectedTx.paypal_approve_url && (
                  <div className="pt-2">
                    <a
                      href={selectedTx.paypal_approve_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs text-[#22D3EE] hover:underline"
                    >
                      <span>Open PayPal Payer Approval</span>
                      <ExternalLinkIcon className="w-3.5 h-3.5" />
                    </a>
                  </div>
                )}
              </div>
            )}

            {/* Failure details if present */}
            {selectedTx.failure && (
              <div className="p-3 rounded-md bg-[#F43F5E]/10 border border-[#F43F5E]/20 text-[#FB7185] text-xs">
                <strong>Failure Details:</strong> {selectedTx.failure}
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex items-center justify-between pt-2">
              <div className="text-[11px] font-mono text-[#5F716D]">
                Recorded: {formatDate(selectedTx.created_at)}
              </div>
              <div className="flex items-center gap-2">
                {selectedTx.status === "failed" && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleRetry(selectedTx.payment_id)}
                    loading={retrying}
                    icon={<RefreshCwIcon className="w-3.5 h-3.5" />}
                  >
                    Retry Payment
                  </Button>
                )}
                <Button size="sm" variant="ghost" onClick={() => setSelectedTx(null)}>
                  Close
                </Button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
