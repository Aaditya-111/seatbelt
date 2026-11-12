"use client";

import React, { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { ShieldCheckIcon } from "@/components/ui/Icons";

interface Scenario {
  id: string;
  label: string;
  tag: string;
  agent: string;
  payee: string;
  amount: string;
  currency: string;
  verdict: "allow" | "require_approval" | "deny";
  status: string;
  ruleMatched: string;
  policyNotes: string;
  auditHash: string;
  auditSeq: number;
}

const SCENARIOS: Scenario[] = [
  {
    id: "routine",
    label: "Routine Purchase",
    tag: "Passed Automatically",
    agent: "agent:dev-agent-01",
    payee: "shop-a",
    amount: "$25.00",
    currency: "USD",
    verdict: "allow",
    status: "captured",
    ruleMatched: "Within $100 per-payment & under $40 approval threshold",
    policyNotes: "Budget deducted: $25.00. Remaining committed: $275.00 / $300.00.",
    auditHash: "8f2a93c1d4e5f670...b9e1",
    auditSeq: 1042,
  },
  {
    id: "threshold",
    label: "High-Value Purchase",
    tag: "Approval Gate",
    agent: "agent:research-agent",
    payee: "shop-a",
    amount: "$85.00",
    currency: "USD",
    verdict: "require_approval",
    status: "pending_approval",
    ruleMatched: "Exceeds $40.00 approval threshold",
    policyNotes: "Held in human queue. Budget temporarily reserved pending admin action.",
    auditHash: "7b1c4e9f2a0d5831...c3a4",
    auditSeq: 1043,
  },
  {
    id: "untrusted",
    label: "Untrusted Merchant",
    tag: "Policy Violation",
    agent: "agent:dev-agent-01",
    payee: "attacker-wallet",
    amount: "$15.00",
    currency: "USD",
    verdict: "deny",
    status: "denied",
    ruleMatched: "Payee 'attacker-wallet' not in mandate allowlist [shop-a, shop-b]",
    policyNotes: "Transaction rejected at perimeter. Zero funds released.",
    auditHash: "e4a90f12c3b5d871...99d2",
    auditSeq: 1044,
  },
  {
    id: "exceeded",
    label: "Budget Exhaustion",
    tag: "Limit Reached",
    agent: "agent:scraping-bot",
    payee: "shop-b",
    amount: "$350.00",
    currency: "USD",
    verdict: "deny",
    status: "denied",
    ruleMatched: "Exceeds total mandate budget ($300.00 max)",
    policyNotes: "Hard limit enforcement. Agent must request mandate renewal.",
    auditHash: "3f8d2e1c9a0b4576...11e8",
    auditSeq: 1045,
  },
];

export function InteractivePipeline() {
  const [activeId, setActiveId] = useState<string>("routine");
  const active = SCENARIOS.find((s) => s.id === activeId) || SCENARIOS[0];

  return (
    <div className="w-full bg-[#11181D] border border-[#1E2B27] rounded-xl overflow-hidden shadow-2xl">
      {/* Top Header / Scenario Selector */}
      <div className="px-4 py-3 border-b border-[#1E2B27] bg-[#0C1216] flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#16E6A0] animate-pulse" />
          <span className="text-[11px] font-mono text-[#91A09D] uppercase tracking-wider">
            Live Policy Engine Simulator
          </span>
        </div>
        <div className="flex items-center gap-1.5 overflow-x-auto py-1">
          {SCENARIOS.map((sc) => (
            <button
              key={sc.id}
              onClick={() => setActiveId(sc.id)}
              className={`text-[11px] px-2.5 py-1 rounded-md font-medium transition-all ${
                activeId === sc.id
                  ? "bg-[#16E6A0] text-[#090D10] font-semibold"
                  : "bg-[#151F24] text-[#91A09D] hover:text-[#F1F5F4] hover:bg-[#1A262D]"
              }`}
            >
              {sc.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Pipeline Display */}
      <div className="p-5 sm:p-6 space-y-6">
        {/* Step-by-step Flow */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* Node 1: AI Agent */}
          <div className="p-3.5 rounded-lg bg-[#0E151A] border border-[#1E2B27] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#91A09D]">
                  Step 1 · Origin
                </span>
                <span className="text-[10px] font-mono text-[#16E6A0] bg-[#16E6A0]/10 px-1.5 py-0.5 rounded">
                  Mandate Token
                </span>
              </div>
              <div className="text-xs font-semibold text-[#F1F5F4]">{active.agent}</div>
              <div className="text-[11px] text-[#91A09D] mt-1">
                Requested: <strong className="text-[#F1F5F4] font-mono">{active.amount}</strong> to{" "}
                <span className="text-[#22D3EE] font-mono">{active.payee}</span>
              </div>
            </div>
            <div className="mt-3 pt-2 border-t border-[#1E2B27]/60 text-[10px] text-[#5F716D] font-mono">
              Signed Ed25519 Mandate
            </div>
          </div>

          {/* Node 2: Seatbelt Policy Engine */}
          <div className="p-3.5 rounded-lg bg-[#151F24] border border-[#233530] flex flex-col justify-between relative overflow-hidden">
            <div className="absolute top-0 right-0 w-24 h-24 bg-[#16E6A0]/5 rounded-full blur-xl pointer-events-none" />
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#16E6A0]">
                  Step 2 · Policy Check
                </span>
                <Badge status={active.verdict} size="sm" />
              </div>
              <div className="text-xs font-medium text-[#F1F5F4]">{active.ruleMatched}</div>
              <div className="text-[11px] text-[#91A09D] mt-1">{active.policyNotes}</div>
            </div>
            <div className="mt-3 pt-2 border-t border-[#1E2B27] flex items-center justify-between text-[10px] font-mono">
              <span className="text-[#91A09D]">Verdict</span>
              <span className="text-[#F1F5F4] font-semibold uppercase">{active.verdict.replace("_", " ")}</span>
            </div>
          </div>

          {/* Node 3: Execution / Provider */}
          <div className="p-3.5 rounded-lg bg-[#0E151A] border border-[#1E2B27] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#91A09D]">
                  Step 3 · Settlement
                </span>
                <Badge status={active.status} size="sm" />
              </div>
              <div className="text-xs font-semibold text-[#F1F5F4]">
                {active.status === "captured"
                  ? "Captured on Payment Rail"
                  : active.status === "pending_approval"
                  ? "Awaiting Human Sign-Off"
                  : "Blocked at Security Barrier"}
              </div>
              <div className="text-[11px] text-[#91A09D] mt-1">
                {active.status === "captured" && "PayPal order captured & ledger reconciled."}
                {active.status === "pending_approval" && "Dispatched to admin approval queue."}
                {active.status === "denied" && "Transaction rejected. Zero provider API calls."}
              </div>
            </div>
            <div className="mt-3 pt-2 border-t border-[#1E2B27]/60 text-[10px] text-[#5F716D] font-mono">
              Channel: PayPal Orders v2
            </div>
          </div>
        </div>

        {/* Audit Log Banner */}
        <div className="p-3.5 rounded-lg bg-[#0C1216] border border-[#1E2B27] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded bg-[#11181D] border border-[#1E2B27] flex items-center justify-center text-[#16E6A0]">
              <ShieldCheckIcon className="w-3.5 h-3.5" />
            </div>
            <div>
              <span className="text-[#91A09D] text-[11px]">HMAC Hash Chain Record: </span>
              <span className="text-[#F1F5F4] font-mono font-medium">seq #{active.auditSeq}</span>
              <span className="text-[#5F716D] font-mono text-[11px] ml-2">[{active.auditHash}]</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#16E6A0]" />
            <span className="text-[11px] font-mono text-[#91A09D]">Integrity Verified</span>
          </div>
        </div>
      </div>
    </div>
  );
}
