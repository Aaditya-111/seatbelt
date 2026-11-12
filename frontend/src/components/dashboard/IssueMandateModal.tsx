"use client";

import React, { useState } from "react";
import { MandateIssued } from "@/lib/types";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { issueMandate, formatMoney } from "@/lib/api-client";
import { CopyIcon, CheckIcon } from "@/components/ui/Icons";

interface IssueMandateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onMandateIssued?: (issued: MandateIssued) => void;
}

export function IssueMandateModal({
  isOpen,
  onClose,
  onMandateIssued,
}: IssueMandateModalProps) {
  const [agentId, setAgentId] = useState("agent:dev-agent-01");
  const [currency, setCurrency] = useState("USD");
  const [perPaymentLimit, setPerPaymentLimit] = useState("50.00");
  const [totalLimit, setTotalLimit] = useState("200.00");
  const [approvalThreshold, setApprovalThreshold] = useState("25.00");
  const [payees, setPayees] = useState("shop-a, shop-b");
  const [ttlMinutes, setTtlMinutes] = useState(60);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [issuedResult, setIssuedResult] = useState<MandateIssued | null>(null);
  const [tokenCopied, setTokenCopied] = useState(false);

  const handleReset = () => {
    setIssuedResult(null);
    setError("");
    setTokenCopied(false);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const allowedPayeesArray = payees
        .split(",")
        .map((p) => p.trim().toLowerCase())
        .filter(Boolean);

      if (allowedPayeesArray.length === 0) {
        throw new Error("At least one allowed payee is required.");
      }

      const result = await issueMandate({
        agent_id: agentId.trim(),
        currency: currency.trim().toUpperCase(),
        per_payment_limit: perPaymentLimit.trim(),
        total_limit: totalLimit.trim(),
        approval_threshold: approvalThreshold.trim(),
        allowed_payees: allowedPayeesArray,
        ttl_minutes: Number(ttlMinutes),
      });

      setIssuedResult(result);
      onMandateIssued?.(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to issue mandate.");
    } finally {
      setLoading(false);
    }
  };

  const copyToken = () => {
    if (!issuedResult) return;
    navigator.clipboard.writeText(issuedResult.token);
    setTokenCopied(true);
    setTimeout(() => setTokenCopied(false), 2000);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={issuedResult ? "Mandate Token Issued" : "Issue New Agent Mandate"}
      description={
        issuedResult
          ? "Copy the signed mandate token below. The agent uses this token as Bearer authorization."
          : "Define deterministic spending limits, allowed merchants, and approval thresholds for an agent."
      }
      maxWidth="lg"
    >
      {issuedResult ? (
        <div className="space-y-4 pt-2">
          {/* Success Banner */}
          <div className="p-3.5 rounded-lg bg-[#16E6A0]/10 border border-[#16E6A0]/25 text-[#16E6A0] text-xs">
            <strong>Mandate Created & Cryptographically Signed</strong>
            <p className="mt-1 text-[11px] text-[#91A09D]">
              Mandate ID: <span className="font-mono text-[#F1F5F4]">{issuedResult.mandate.mandate_id}</span>
            </p>
          </div>

          {/* Token Box */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[11px] font-mono uppercase text-[#91A09D]">
                Mandate Token (Send as Authorization: Bearer &lt;token&gt;)
              </label>
              <button
                onClick={copyToken}
                className="flex items-center gap-1 text-[11px] text-[#16E6A0] hover:underline font-mono"
              >
                {tokenCopied ? (
                  <>
                    <CheckIcon className="w-3.5 h-3.5" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <CopyIcon className="w-3.5 h-3.5" />
                    <span>Copy Token</span>
                  </>
                )}
              </button>
            </div>
            <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] max-h-32 overflow-y-auto break-all font-mono text-xs text-[#F1F5F4]">
              {issuedResult.token}
            </div>
          </div>

          {/* Mandate Summary Grid */}
          <div className="grid grid-cols-2 gap-3 text-xs p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
            <div>
              <span className="text-[#5F716D] block">Agent Identity</span>
              <span className="font-mono text-[#F1F5F4]">{issuedResult.mandate.agent_id}</span>
            </div>
            <div>
              <span className="text-[#5F716D] block">Per-Payment Ceiling</span>
              <span className="font-mono text-[#16E6A0]">
                {formatMoney(issuedResult.mandate.per_payment_limit, issuedResult.mandate.currency)}
              </span>
            </div>
            <div>
              <span className="text-[#5F716D] block">Total Budget Cap</span>
              <span className="font-mono text-[#16E6A0]">
                {formatMoney(issuedResult.mandate.total_limit, issuedResult.mandate.currency)}
              </span>
            </div>
            <div>
              <span className="text-[#5F716D] block">Human Approval Threshold</span>
              <span className="font-mono text-[#FBBF24]">
                {formatMoney(issuedResult.mandate.approval_threshold, issuedResult.mandate.currency)}
              </span>
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <Button size="sm" onClick={handleClose}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          {error && (
            <div className="p-3 rounded-md bg-[#F43F5E]/10 border border-[#F43F5E]/20 text-[#FB7185] text-xs">
              {error}
            </div>
          )}

          {/* Agent ID */}
          <div>
            <label className="block text-[11px] font-mono uppercase text-[#91A09D] mb-1.5">
              Agent Identity
            </label>
            <input
              type="text"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              placeholder="e.g. agent:procurement-bot"
              className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
              required
            />
          </div>

          {/* Limits Grid */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-mono uppercase text-[#91A09D] mb-1.5">
                Per-Payment Limit
              </label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={perPaymentLimit}
                onChange={(e) => setPerPaymentLimit(e.target.value)}
                className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
                required
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono uppercase text-[#91A09D] mb-1.5">
                Total Lifetime Budget
              </label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={totalLimit}
                onChange={(e) => setTotalLimit(e.target.value)}
                className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
                required
              />
            </div>
          </div>

          {/* Threshold & Currency */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-mono uppercase text-[#91A09D] mb-1.5">
                Approval Threshold
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={approvalThreshold}
                onChange={(e) => setApprovalThreshold(e.target.value)}
                className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
                required
              />
              <span className="text-[10px] text-[#5F716D] mt-0.5 block">0 = always require approval</span>
            </div>
            <div>
              <label className="block text-[11px] font-mono uppercase text-[#91A09D] mb-1.5">
                Currency (ISO)
              </label>
              <input
                type="text"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
                required
              />
            </div>
          </div>

          {/* Payees Allowlist */}
          <div>
            <label className="block text-[11px] font-mono uppercase text-[#91A09D] mb-1.5">
              Allowed Payees (Comma-separated)
            </label>
            <input
              type="text"
              value={payees}
              onChange={(e) => setPayees(e.target.value)}
              placeholder="e.g. shop-a, shop-b, cloud-provider"
              className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
              required
            />
          </div>

          {/* TTL Minutes */}
          <div>
            <label className="block text-[11px] font-mono uppercase text-[#91A09D] mb-1.5">
              Validity Window (Minutes, max 1440)
            </label>
            <input
              type="number"
              min="1"
              max="1440"
              value={ttlMinutes}
              onChange={(e) => setTtlMinutes(Number(e.target.value))}
              className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
              required
            />
          </div>

          {/* Form Actions */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#1E2B27]">
            <Button type="button" variant="ghost" size="sm" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit" size="sm" loading={loading}>
              Sign & Issue Mandate
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
