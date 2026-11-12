"use client";

import React from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ScaleIcon } from "@/components/ui/Icons";

export function PoliciesView() {
  const policyRules = [
    {
      name: "Per-Payment Ceiling",
      field: "per_payment_limit",
      type: "Decimal (e.g. $100.00)",
      description: "Strict upper bound for any single transaction. Transactions exceeding this limit are immediately denied.",
      effect: "deny",
    },
    {
      name: "Aggregate Lifetime Budget",
      field: "total_limit & committed",
      type: "Decimal (e.g. $500.00)",
      description: "Total spend cap across all payments for this mandate. When committed spend + requested amount exceeds total limit, transaction is denied.",
      effect: "deny",
    },
    {
      name: "Payee / Merchant Allowlist",
      field: "allowed_payees",
      type: "Exact strings (no wildcards)",
      description: "Only explicitly allowlisted payee identifiers can receive funds. Prevents lookalike domain spoofing and rogue payee swaps.",
      effect: "deny",
    },
    {
      name: "Human Approval Threshold",
      field: "approval_threshold",
      type: "Decimal (e.g. $40.00)",
      description: "Transactions below threshold execute autonomously. Transactions at or above threshold are held in the approval queue for admin review.",
      effect: "require_approval",
    },
    {
      name: "Mandate Expiration Window",
      field: "issued_at & expires_at",
      type: "UTC ISO-8601 Timestamp",
      description: "Finite mandate lifetime (max 24 hours). Payments submitted before valid_from or after expires_at fail authentication.",
      effect: "deny",
    },
    {
      name: "Currency Boundary",
      field: "currency",
      type: "ISO-4217 (e.g. USD)",
      description: "Payments must match the exact currency declared on the mandate token. Multi-currency conversions are disallowed.",
      effect: "deny",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div>
        <h2 className="text-base font-semibold text-[#F1F5F4]">Mandate Policy Architecture</h2>
        <p className="text-xs text-[#91A09D]">
          Deterministic constraints enforced on every agent payment request prior to provider dispatch.
        </p>
      </div>

      {/* Policy Fields Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {policyRules.map((rule) => (
          <Card key={rule.field}>
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded bg-[#151F24] border border-[#1E2B27] flex items-center justify-center text-[#16E6A0]">
                  <ScaleIcon className="w-3.5 h-3.5" />
                </div>
                <h3 className="text-xs font-semibold text-[#F1F5F4]">{rule.name}</h3>
              </div>
              <Badge
                status={rule.effect === "require_approval" ? "require_approval" : "denied"}
                size="sm"
              >
                {rule.effect === "require_approval" ? "Escalates" : "Blocks"}
              </Badge>
            </div>

            <p className="text-xs text-[#91A09D] leading-relaxed mb-3">
              {rule.description}
            </p>

            <div className="pt-2.5 border-t border-[#1E2B27] flex items-center justify-between text-[11px] font-mono">
              <span className="text-[#5F716D]">Schema Field:</span>
              <code className="text-[#22D3EE]">{rule.field}</code>
            </div>
          </Card>
        ))}
      </div>

      {/* Decision Engine Truth Table */}
      <Card>
        <CardHeader
          title="Policy Verdict Decision Matrix"
          subtitle="How Seatbelt determines transaction execution states"
        />

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#1E2B27] text-[#91A09D] font-mono text-[11px]">
                <th className="pb-2.5 font-medium">Evaluation Condition</th>
                <th className="pb-2.5 font-medium">Verdict</th>
                <th className="pb-2.5 font-medium">Payment State</th>
                <th className="pb-2.5 font-medium">Action Required</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1E2B27]/60">
              <tr className="hover:bg-[#151F24]/50">
                <td className="py-2.5 text-[#F1F5F4]">
                  Payee allowed, amount &lt; approval_threshold, budget remaining
                </td>
                <td className="py-2.5">
                  <Badge status="allow" size="sm" />
                </td>
                <td className="py-2.5 font-mono text-[#16E6A0]">captured / reserved</td>
                <td className="py-2.5 text-[#91A09D]">Automatic settlement on payment rail</td>
              </tr>
              <tr className="hover:bg-[#151F24]/50">
                <td className="py-2.5 text-[#F1F5F4]">
                  Payee allowed, amount &ge; approval_threshold, under total limit
                </td>
                <td className="py-2.5">
                  <Badge status="require_approval" size="sm" />
                </td>
                <td className="py-2.5 font-mono text-[#FBBF24]">pending_approval</td>
                <td className="py-2.5 text-[#91A09D]">Held in human approval queue</td>
              </tr>
              <tr className="hover:bg-[#151F24]/50">
                <td className="py-2.5 text-[#F1F5F4]">
                  Payee not on allowlist OR amount &gt; per_payment_limit
                </td>
                <td className="py-2.5">
                  <Badge status="deny" size="sm" />
                </td>
                <td className="py-2.5 font-mono text-[#FB7185]">denied</td>
                <td className="py-2.5 text-[#91A09D]">Immediate block. Zero funds released.</td>
              </tr>
              <tr className="hover:bg-[#151F24]/50">
                <td className="py-2.5 text-[#F1F5F4]">
                  Requested amount exceeds remaining total budget
                </td>
                <td className="py-2.5">
                  <Badge status="deny" size="sm" />
                </td>
                <td className="py-2.5 font-mono text-[#FB7185]">denied</td>
                <td className="py-2.5 text-[#91A09D]">Hard budget ceiling reached</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
