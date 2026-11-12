"use client";

import React, { useState } from "react";
import { PaymentRecord } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { approvePayment, rejectPayment, formatMoney, shortId } from "@/lib/api-client";
import { FileCheckIcon, CheckIcon, XIcon } from "@/components/ui/Icons";

interface ApprovalsViewProps {
  payments: PaymentRecord[];
  onRefresh: () => void;
}

export function ApprovalsView({ payments, onRefresh }: ApprovalsViewProps) {
  // Only payments with status === "pending_approval" belong in the human approval queue!
  // 'awaiting_payer' is the PayPal buyer flow and is NOT an admin approval request.
  const approvalItems = payments.filter((p) => p.status === "pending_approval");
  const awaitingPayerItems = payments.filter((p) => p.status === "awaiting_payer");

  // State for confirm modal
  const [selectedPayment, setSelectedPayment] = useState<PaymentRecord | null>(null);
  const [actionType, setActionType] = useState<"approve" | "reject" | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState("");

  const openApproveModal = (payment: PaymentRecord) => {
    setSelectedPayment(payment);
    setActionType("approve");
    setActionError("");
  };

  const openRejectModal = (payment: PaymentRecord) => {
    setSelectedPayment(payment);
    setActionType("reject");
    setRejectReason("High risk or outside intended scope");
    setActionError("");
  };

  const closeModal = () => {
    setSelectedPayment(null);
    setActionType(null);
    setActionError("");
  };

  const handleExecuteAction = async () => {
    if (!selectedPayment || !actionType) return;
    setActionLoading(true);
    setActionError("");

    try {
      if (actionType === "approve") {
        await approvePayment(selectedPayment.payment_id, "admin");
      } else {
        await rejectPayment(selectedPayment.payment_id, rejectReason, "admin");
      }
      closeModal();
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-[#F1F5F4]">Human Approval Queue</h2>
          <p className="text-xs text-[#91A09D]">
            Review payments that exceeded mandate approval thresholds before funds are committed.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={approvalItems.length > 0 ? "amber" : "neutral"} size="md">
            {approvalItems.length} Pending Review
          </Badge>
        </div>
      </div>

      {/* Main Approval Queue */}
      <Card>
        <CardHeader
          title="Transactions Awaiting Administrator Decision"
          subtitle="Policy engine held these transactions because amounts met or exceeded approval thresholds"
        />

        {approvalItems.length === 0 ? (
          <EmptyState
            icon={<FileCheckIcon className="w-5 h-5 text-[#16E6A0]" />}
            title="Approval queue is clear"
            description="No agent payments are currently waiting for human approval. Any payment exceeding an agent's approval_threshold will appear here."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[#1E2B27] text-[#91A09D] font-mono text-[11px]">
                  <th className="pb-2.5 font-medium">Payment ID</th>
                  <th className="pb-2.5 font-medium">Agent</th>
                  <th className="pb-2.5 font-medium">Payee</th>
                  <th className="pb-2.5 font-medium">Requested Amount</th>
                  <th className="pb-2.5 font-medium">Policy Reason</th>
                  <th className="pb-2.5 font-medium text-right">Decision</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2B27]/60">
                {approvalItems.map((p) => {
                  const reasonText = p.reasons?.map((r) => r.message).join("; ") || "Exceeds approval threshold";
                  return (
                    <tr key={p.payment_id} className="hover:bg-[#151F24]/50 transition-colors">
                      <td className="py-3 font-mono font-medium text-[#F1F5F4]">
                        {shortId(p.payment_id)}
                      </td>
                      <td className="py-3 font-mono text-[#91A09D]">
                        {p.agent_id}
                      </td>
                      <td className="py-3 font-mono text-[#22D3EE]">
                        {p.payee}
                      </td>
                      <td className="py-3 font-mono font-semibold text-[#F1F5F4]">
                        {formatMoney(p.amount, p.currency)}
                      </td>
                      <td className="py-3 text-xs text-[#91A09D] max-w-xs">
                        <span className="text-[#FBBF24] font-medium block">Approval Required</span>
                        <span className="text-[11px] text-[#5F716D] block line-clamp-1">{reasonText}</span>
                      </td>
                      <td className="py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            size="sm"
                            variant="primary"
                            onClick={() => openApproveModal(p)}
                            icon={<CheckIcon className="w-3.5 h-3.5" />}
                          >
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            onClick={() => openRejectModal(p)}
                            icon={<XIcon className="w-3.5 h-3.5" />}
                          >
                            Reject
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Distinction section: Awaiting Payer (PayPal Buyer Flow) */}
      {awaitingPayerItems.length > 0 && (
        <Card>
          <CardHeader
            title="Transactions Awaiting Payer (PayPal Buyer Authorization)"
            subtitle="These payments were approved by policy but require the buyer/payer to log in to PayPal. They are NOT admin approval requests."
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[#1E2B27] text-[#91A09D] font-mono text-[11px]">
                  <th className="pb-2.5 font-medium">Payment ID</th>
                  <th className="pb-2.5 font-medium">Agent</th>
                  <th className="pb-2.5 font-medium">Payee</th>
                  <th className="pb-2.5 font-medium">Amount</th>
                  <th className="pb-2.5 font-medium">PayPal Order ID</th>
                  <th className="pb-2.5 font-medium">Buyer Link</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2B27]/60">
                {awaitingPayerItems.map((p) => (
                  <tr key={p.payment_id} className="hover:bg-[#151F24]/50">
                    <td className="py-2.5 font-mono text-[#F1F5F4]">{shortId(p.payment_id)}</td>
                    <td className="py-2.5 font-mono text-[#91A09D]">{p.agent_id}</td>
                    <td className="py-2.5 font-mono text-[#22D3EE]">{p.payee}</td>
                    <td className="py-2.5 font-mono font-medium text-[#F1F5F4]">
                      {formatMoney(p.amount, p.currency)}
                    </td>
                    <td className="py-2.5 font-mono text-[#5F716D]">
                      {p.paypal_order_id ?? "—"}
                    </td>
                    <td className="py-2.5">
                      {p.paypal_approve_url ? (
                        <a
                          href={p.paypal_approve_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[#22D3EE] hover:underline font-mono text-[11px]"
                        >
                          Complete in PayPal ↗
                        </a>
                      ) : (
                        <span className="text-[#5F716D] font-mono">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Confirmation Modal */}
      <Modal
        isOpen={selectedPayment !== null}
        onClose={closeModal}
        title={actionType === "approve" ? "Confirm Payment Approval" : "Confirm Payment Rejection"}
        description={
          actionType === "approve"
            ? "Authorizing this transaction will commit the funds and proceed with provider execution."
            : "Rejecting this transaction will deny authorization, cancel reservations, and log the rejection reason."
        }
      >
        {selectedPayment && (
          <div className="space-y-4 pt-2">
            {actionError && (
              <div className="p-3 rounded-md bg-[#F43F5E]/10 border border-[#F43F5E]/20 text-[#FB7185] text-xs">
                {actionError}
              </div>
            )}

            <div className="p-3.5 rounded-lg bg-[#090D10] border border-[#1E2B27] space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-[#91A09D]">Payment ID:</span>
                <span className="font-mono text-[#F1F5F4]">{selectedPayment.payment_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#91A09D]">Agent:</span>
                <span className="font-mono text-[#F1F5F4]">{selectedPayment.agent_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#91A09D]">Payee:</span>
                <span className="font-mono text-[#22D3EE]">{selectedPayment.payee}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#91A09D]">Amount:</span>
                <span className="font-mono font-semibold text-[#16E6A0]">
                  {formatMoney(selectedPayment.amount, selectedPayment.currency)}
                </span>
              </div>
              {selectedPayment.description && (
                <div className="pt-2 border-t border-[#1E2B27] text-[#91A09D]">
                  Description: <span className="text-[#F1F5F4]">{selectedPayment.description}</span>
                </div>
              )}
            </div>

            {actionType === "reject" && (
              <div>
                <label className="block text-xs font-mono uppercase text-[#91A09D] mb-1.5">
                  Rejection Reason (Audit Trail Record)
                </label>
                <textarea
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] focus:outline-none focus:border-[#FB7185]"
                  required
                />
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <Button variant="ghost" size="sm" onClick={closeModal}>
                Cancel
              </Button>
              <Button
                variant={actionType === "approve" ? "primary" : "danger"}
                size="sm"
                onClick={handleExecuteAction}
                loading={actionLoading}
              >
                {actionType === "approve" ? "Authorize & Capture" : "Confirm Rejection"}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
