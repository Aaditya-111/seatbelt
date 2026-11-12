"use client";

import React, { useState } from "react";
import { StoredMandate, PaymentRecord } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { getMandate, revokeMandate, formatMoney, formatDate, shortId } from "@/lib/api-client";
import { UsersIcon, SearchIcon, KeyIcon } from "@/components/ui/Icons";

interface AgentsViewProps {
  payments: PaymentRecord[];
  onOpenIssueMandate: () => void;
}

export function AgentsView({ payments, onOpenIssueMandate }: AgentsViewProps) {
  const [lookupId, setLookupId] = useState("");
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState("");
  const [lookedUpMandate, setLookedUpMandate] = useState<StoredMandate | null>(null);

  const [revoking, setRevoking] = useState(false);
  const [revokeMessage, setRevokeMessage] = useState("");

  // Derive known agent IDs and mandate IDs from existing payment records
  const knownAgentMap = new Map<string, { agentId: string; mandateId: string; txCount: number; lastSeen: string }>();
  for (const p of payments) {
    if (!knownAgentMap.has(p.agent_id)) {
      knownAgentMap.set(p.agent_id, {
        agentId: p.agent_id,
        mandateId: p.mandate_id,
        txCount: 1,
        lastSeen: p.created_at,
      });
    } else {
      const entry = knownAgentMap.get(p.agent_id)!;
      entry.txCount += 1;
    }
  }
  const knownAgents = Array.from(knownAgentMap.values());

  const handleLookup = async (e?: React.FormEvent, mandateIdToLookup?: string) => {
    if (e) e.preventDefault();
    const id = (mandateIdToLookup || lookupId).trim();
    if (!id) return;

    setLookupLoading(true);
    setLookupError("");
    setRevokeMessage("");
    try {
      const res = await getMandate(id);
      setLookedUpMandate(res);
      setLookupId(id);
    } catch (err) {
      setLookupError(err instanceof Error ? err.message : "Mandate not found.");
      setLookedUpMandate(null);
    } finally {
      setLookupLoading(false);
    }
  };

  const handleRevoke = async () => {
    if (!lookedUpMandate) return;
    const mandateId = lookedUpMandate.mandate.mandate_id;
    if (!confirm(`Are you sure you want to revoke mandate ${mandateId}? Any reserved payments will be cancelled.`)) {
      return;
    }

    setRevoking(true);
    setRevokeMessage("");
    try {
      const res = await revokeMandate(mandateId);
      setRevokeMessage(`Mandate revoked successfully. ${res.payments_cancelled} pending payments cancelled.`);
      // Refresh lookup
      const updated = await getMandate(mandateId);
      setLookedUpMandate(updated);
    } catch (err) {
      setLookupError(err instanceof Error ? err.message : "Failed to revoke mandate.");
    } finally {
      setRevoking(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-[#F1F5F4]">Agent Mandate Registry</h2>
          <p className="text-xs text-[#91A09D]">
            Inspect individual signed spending mandates, track committed budgets, or issue new authorizations.
          </p>
        </div>
        <Button onClick={onOpenIssueMandate} icon={<KeyIcon className="w-3.5 h-3.5" />}>
          Issue New Mandate
        </Button>
      </div>

      {/* Backend API Notice */}
      <div className="p-3.5 rounded-lg bg-[#11181D] border border-[#1E2B27] text-xs text-[#91A09D] flex items-start gap-2.5">
        <span className="text-[#16E6A0] font-mono text-[11px] mt-0.5">ℹ</span>
        <div>
          <strong className="text-[#F1F5F4] font-medium">Backend Contract Note:</strong> The backend implements direct mandate lookup (<code className="text-[#16E6A0]">GET /v1/mandates/&#123;id&#125;</code>) and mandate issuance (<code className="text-[#16E6A0]">POST /v1/mandates</code>). A global listing endpoint (<code className="text-[#16E6A0]">GET /v1/mandates</code>) is not implemented in the API, so known agents below are aggregated from payment activity.
        </div>
      </div>

      {/* Lookup Mandate Card */}
      <Card>
        <CardHeader
          title="Mandate Inspector"
          subtitle="Query the backend store for a specific mandate by ID"
        />

        <form onSubmit={(e) => handleLookup(e)} className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={lookupId}
              onChange={(e) => setLookupId(e.target.value)}
              placeholder="Enter mandate ID (e.g. 550e8400-e29b-41d4-a716-446655440000)"
              className="w-full px-3 py-2 pl-9 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
            />
            <SearchIcon className="w-4 h-4 text-[#5F716D] absolute left-3 top-2.5" />
          </div>
          <Button type="submit" size="sm" loading={lookupLoading}>
            Inspect
          </Button>
        </form>

        {lookupError && (
          <div className="mt-4 p-3 rounded-md bg-[#F43F5E]/10 border border-[#F43F5E]/20 text-[#FB7185] text-xs">
            {lookupError}
          </div>
        )}

        {revokeMessage && (
          <div className="mt-4 p-3 rounded-md bg-[#16E6A0]/10 border border-[#16E6A0]/20 text-[#16E6A0] text-xs">
            {revokeMessage}
          </div>
        )}

        {/* Looked Up Mandate Detail */}
        {lookedUpMandate && (
          <div className="mt-6 pt-6 border-t border-[#1E2B27] space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-[11px] font-mono text-[#91A09D] uppercase">Agent Identity</span>
                <div className="text-sm font-semibold font-mono text-[#F1F5F4]">
                  {lookedUpMandate.mandate.agent_id}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {lookedUpMandate.revoked_at ? (
                  <Badge tone="rose" size="md">
                    Revoked ({formatDate(lookedUpMandate.revoked_at)})
                  </Badge>
                ) : new Date(lookedUpMandate.mandate.expires_at) < new Date() ? (
                  <Badge tone="amber" size="md">Expired</Badge>
                ) : (
                  <Badge tone="emerald" size="md">Active Mandate</Badge>
                )}

                {!lookedUpMandate.revoked_at && (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={handleRevoke}
                    loading={revoking}
                  >
                    Revoke Mandate
                  </Button>
                )}
              </div>
            </div>

            {/* Grid of Limits */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 rounded-lg bg-[#090D10] border border-[#1E2B27]">
              <div>
                <div className="text-[11px] text-[#91A09D]">Per-Payment Limit</div>
                <div className="text-sm font-semibold font-mono text-[#F1F5F4] mt-1">
                  {formatMoney(lookedUpMandate.mandate.per_payment_limit, lookedUpMandate.mandate.currency)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[#91A09D]">Total Budget</div>
                <div className="text-sm font-semibold font-mono text-[#F1F5F4] mt-1">
                  {formatMoney(lookedUpMandate.mandate.total_limit, lookedUpMandate.mandate.currency)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[#91A09D]">Committed Spend</div>
                <div className="text-sm font-semibold font-mono text-[#22D3EE] mt-1">
                  {formatMoney(lookedUpMandate.committed, lookedUpMandate.mandate.currency)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[#91A09D]">Approval Threshold</div>
                <div className="text-sm font-semibold font-mono text-[#FBBF24] mt-1">
                  {formatMoney(lookedUpMandate.mandate.approval_threshold, lookedUpMandate.mandate.currency)}
                </div>
              </div>
            </div>

            {/* Payee Allowlist & Metadata */}
            <div className="space-y-2">
              <div className="text-xs font-semibold text-[#F1F5F4]">Allowed Payees:</div>
              <div className="flex flex-wrap gap-1.5">
                {lookedUpMandate.mandate.allowed_payees.map((payee) => (
                  <span
                    key={payee}
                    className="font-mono text-xs px-2 py-0.5 rounded bg-[#151F24] text-[#16E6A0] border border-[#1E2B27]"
                  >
                    {payee}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 text-[11px] font-mono text-[#5F716D] pt-2">
              <div>Issued: {formatDate(lookedUpMandate.mandate.issued_at)}</div>
              <div>Expires: {formatDate(lookedUpMandate.mandate.expires_at)}</div>
            </div>
          </div>
        )}
      </Card>

      {/* Known Agents Table */}
      <Card>
        <CardHeader
          title="Known Transacting Agents"
          subtitle="Agents derived from historical payment transactions in the store"
        />

        {knownAgents.length === 0 ? (
          <EmptyState
            icon={<UsersIcon className="w-5 h-5" />}
            title="No agent records in ledger"
            description="No transactions have been submitted yet. Issue a mandate or run a payment in the Agent Playground."
            action={
              <Button size="sm" onClick={onOpenIssueMandate}>
                Issue Mandate
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[#1E2B27] text-[#91A09D] font-mono text-[11px]">
                  <th className="pb-2.5 font-medium">Agent Identity</th>
                  <th className="pb-2.5 font-medium">Last Known Mandate</th>
                  <th className="pb-2.5 font-medium">Evaluations</th>
                  <th className="pb-2.5 font-medium">Last Active</th>
                  <th className="pb-2.5 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2B27]/60">
                {knownAgents.map((a) => (
                  <tr key={a.agentId} className="hover:bg-[#151F24]/50 transition-colors">
                    <td className="py-2.5 font-mono font-medium text-[#F1F5F4]">{a.agentId}</td>
                    <td className="py-2.5 font-mono text-[#91A09D]">{shortId(a.mandateId)}</td>
                    <td className="py-2.5 font-mono text-[#16E6A0]">{a.txCount} tx</td>
                    <td className="py-2.5 font-mono text-[#5F716D] text-[11px]">
                      {formatDate(a.lastSeen)}
                    </td>
                    <td className="py-2.5 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleLookup(undefined, a.mandateId)}
                      >
                        Inspect Mandate
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
