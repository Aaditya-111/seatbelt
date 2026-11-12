"use client";

import React, { useState } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { CheckIcon } from "@/components/ui/Icons";

interface BenchmarkScenario {
  id: string;
  name: string;
  category: "payee" | "amount" | "state" | "concurrency" | "time" | "identity" | "availability";
  description: string;
  unguardedOutcome: string;
  guardedOutcome: string;
}

const ATTACK_SCENARIOS: BenchmarkScenario[] = [
  {
    id: "A01",
    name: "Payee Swap",
    category: "payee",
    description: "Agent hijacked by prompt injection directs payment to attacker-controlled wallet.",
    unguardedOutcome: "Funds lost to attacker-wallet",
    guardedOutcome: "Blocked: Payee not in allowed_payees",
  },
  {
    id: "A02",
    name: "Lookalike Payees (Homoglyphs & Typos)",
    category: "payee",
    description: "Subtle Unicode homoglyphs, zero-width spaces, and punctuation spoofing shop-a.",
    unguardedOutcome: "Fraudulent payments succeed",
    guardedOutcome: "Blocked: Exact string matching, no wildcards",
  },
  {
    id: "A03",
    name: "Amount Inflation",
    category: "amount",
    description: "Agent attempts a single charge of $10,000 to an otherwise legitimate merchant.",
    unguardedOutcome: "$10,000 debited from account",
    guardedOutcome: "Blocked: Exceeds per_payment_limit ($100 max)",
  },
  {
    id: "A04",
    name: "One Cent Over Boundary",
    category: "amount",
    description: "Agent attempts to charge $100.01 against an exact $100.00 per-payment limit.",
    unguardedOutcome: "Charged $100.01",
    guardedOutcome: "Blocked: Strict inequality boundary enforcement",
  },
  {
    id: "A05",
    name: "PayPal Rounding Exploit",
    category: "amount",
    description: "Submits 100.005 which looks under 100 but rounds up to 100.01 at PayPal.",
    unguardedOutcome: "Overdraft by $0.01",
    guardedOutcome: "Blocked: Pre-flight round check matches PayPal engine",
  },
  {
    id: "A06",
    name: "Absurd & Negative Amounts",
    category: "amount",
    description: "Fuzzes amounts with '0', '-5', '0.001', '5e3' scientific notation.",
    unguardedOutcome: "Ambiguous gateway states",
    guardedOutcome: "Blocked: Pydantic Decimal validation & range checks",
  },
  {
    id: "A07",
    name: "Slow Budget Drain",
    category: "amount",
    description: "Many small legitimate transactions designed to quietly drain funds over time.",
    unguardedOutcome: "Entire treasury drained",
    guardedOutcome: "Blocked: Total limit enforced; stops at $300 cap",
  },
  {
    id: "A08",
    name: "Simple Replay Attack",
    category: "state",
    description: "Same valid request_id submitted multiple times across network drops.",
    unguardedOutcome: "Charged repeatedly (duplicate payout)",
    guardedOutcome: "Idempotent: Single transfer, returns original record",
  },
  {
    id: "A09",
    name: "Replay with Parameter Mutation",
    category: "state",
    description: "Reusing a previous request_id but altering amount or payee details.",
    unguardedOutcome: "State overwrite or second charge",
    guardedOutcome: "Conflict: 409 Idempotency Conflict Error",
  },
  {
    id: "A10",
    name: "Concurrent Double-Spend Race",
    category: "concurrency",
    description: "10 simultaneous threads fire payments in parallel to beat budget balance locks.",
    unguardedOutcome: "Race condition overspends budget",
    guardedOutcome: "Protected: SQLite write transaction serializes commit",
  },
  {
    id: "A11",
    name: "Expired Mandate Submission",
    category: "time",
    description: "Submitting payments after the mandate's valid_until timestamp has passed.",
    unguardedOutcome: "Transaction accepted",
    guardedOutcome: "Blocked: 401 MandateExpiredError",
  },
  {
    id: "A12",
    name: "Payment After Kill Switch",
    category: "time",
    description: "Agent continues paying after human administrator revoked the mandate.",
    unguardedOutcome: "Post-revocation losses",
    guardedOutcome: "Blocked: 403 MandateRevokedError",
  },
  {
    id: "A13",
    name: "Forged Mandate Credentials",
    category: "identity",
    description: "Tampered limits, swapped signatures, garbage tokens, or missing auth headers.",
    unguardedOutcome: "Arbitrary execution",
    guardedOutcome: "Blocked: Ed25519 / HMAC signature verification failure",
  },
  {
    id: "A14",
    name: "Cross-Currency Mismatch",
    category: "amount",
    description: "Submitting EUR and GBP transactions against a USD-denominated permission.",
    unguardedOutcome: "Unintended currency conversion losses",
    guardedOutcome: "Blocked: Currency mismatch against mandate token",
  },
  {
    id: "A15",
    name: "Approval Queue Flood",
    category: "availability",
    description: "100 payments above threshold submitted to tie up budget and fatigue approvers.",
    unguardedOutcome: "Approval fatigue & locked budget",
    guardedOutcome: "Rate limited & reserved budget capped at total_limit",
  },
];

const BENIGN_CHECKS = [
  { name: "10 Routine Purchases", description: "All 10 valid purchases within limits succeed and settle." },
  { name: "Large Purchase Escalation", description: "Purchases >= $40 pause in held state, and execute immediately upon approval." },
  { name: "Rejected Purchase Budget Release", description: "Rejected transactions immediately free their reserved budget." },
  { name: "Idempotent Retry", description: "Retrying an identical request 3 times results in exactly 1 transfer." },
  { name: "Mixed Honest & Hostile Traffic", description: "Interleaved good and bad requests result in zero unauthorized fund transfers." },
];

export function BenchmarksView() {
  const [filter, setFilter] = useState<string>("all");

  const filteredAttacks = ATTACK_SCENARIOS.filter((a) => {
    if (filter === "all") return true;
    return a.category === filter;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-[#F1F5F4]">Adversarial Security Benchmarks</h2>
        <p className="text-xs text-[#91A09D]">
          Ground-truth attack catalogue and regression test suite defined in <code className="text-[#16E6A0]">seatbelt.bench</code>.
        </p>
      </div>

      {/* Overview Stats Card */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <div className="text-[11px] font-mono text-[#91A09D] uppercase">Attack Scenarios</div>
          <div className="text-2xl font-bold font-mono text-[#F1F5F4] mt-1">15 Vectors</div>
          <div className="text-[11px] text-[#91A09D] mt-0.5">A01 to A15 catalogued</div>
        </Card>
        <Card>
          <div className="text-[11px] font-mono text-[#91A09D] uppercase">Benign Checks</div>
          <div className="text-2xl font-bold font-mono text-[#16E6A0] mt-1">5 Checks</div>
          <div className="text-[11px] text-[#91A09D] mt-0.5">Legitimate use guarantees</div>
        </Card>
        <Card>
          <div className="text-[11px] font-mono text-[#91A09D] uppercase">Policy Defense Rate</div>
          <div className="text-2xl font-bold font-mono text-[#16E6A0] mt-1">100%</div>
          <div className="text-[11px] text-[#91A09D] mt-0.5">Zero unauthorized money moved</div>
        </Card>
        <Card>
          <div className="text-[11px] font-mono text-[#91A09D] uppercase">Execution Mode</div>
          <div className="text-sm font-semibold font-mono text-[#22D3EE] mt-2">CLI / CI Suite</div>
          <div className="text-[11px] text-[#91A09D] mt-0.5">Python benchmark runner</div>
        </Card>
      </div>

      {/* CLI Runner Instruction Card */}
      <Card>
        <CardHeader
          title="Executing the Benchmark Suite"
          subtitle="The benchmark is executed offline or in CI to stress-test the policy engine and independent ledger auditor"
        />
        <div className="p-3.5 rounded-lg bg-[#090D10] border border-[#1E2B27] font-mono text-xs text-[#F1F5F4]">
          <span className="text-[#5F716D] block mb-1"># Run all 15 adversarial attacks against unprotected vs. Seatbelt-guarded environments:</span>
          <code>python -m seatbelt.bench</code>
          <span className="text-[#5F716D] block mt-2 mb-1"># Or run via pytest test suite:</span>
          <code>pytest tests/test_benchmark.py -v</code>
        </div>
      </Card>

      {/* Attack Scenarios Table */}
      <Card>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="text-sm font-semibold text-[#F1F5F4]">Adversarial Attack Catalogue</h3>
            <p className="text-xs text-[#91A09D]">
              Simulating compromised agents attempting unauthorized fund exfiltration
            </p>
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto">
            {["all", "payee", "amount", "state", "concurrency", "time", "identity"].map((cat) => (
              <button
                key={cat}
                onClick={() => setFilter(cat)}
                className={`text-[11px] px-2.5 py-1 rounded-md font-mono transition-colors capitalize ${
                  filter === cat
                    ? "bg-[#151F24] text-[#16E6A0] border border-[#1E2B27] font-semibold"
                    : "text-[#91A09D] hover:text-[#F1F5F4]"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#1E2B27] text-[#91A09D] font-mono text-[11px]">
                <th className="pb-2.5 font-medium">ID</th>
                <th className="pb-2.5 font-medium">Attack Vector</th>
                <th className="pb-2.5 font-medium">Category</th>
                <th className="pb-2.5 font-medium">Without Seatbelt</th>
                <th className="pb-2.5 font-medium">With Seatbelt Guard</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1E2B27]/60">
              {filteredAttacks.map((a) => (
                <tr key={a.id} className="hover:bg-[#151F24]/50 transition-colors">
                  <td className="py-3 font-mono font-bold text-[#16E6A0]">{a.id}</td>
                  <td className="py-3 max-w-xs">
                    <strong className="text-[#F1F5F4] block text-xs">{a.name}</strong>
                    <span className="text-[11px] text-[#91A09D] block mt-0.5">{a.description}</span>
                  </td>
                  <td className="py-3">
                    <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-[#151F24] text-[#91A09D] border border-[#1E2B27] uppercase">
                      {a.category}
                    </span>
                  </td>
                  <td className="py-3 text-[#FB7185] font-mono text-[11px]">
                    {a.unguardedOutcome}
                  </td>
                  <td className="py-3 text-[#16E6A0] font-mono text-[11px]">
                    <span className="flex items-center gap-1.5">
                      <CheckIcon className="w-3.5 h-3.5 text-[#16E6A0]" />
                      <span>{a.guardedOutcome}</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Benign Capability Checks */}
      <Card>
        <CardHeader
          title="Benign Capability Checks (5 Scenarios)"
          subtitle="Verifying that honest operations are never blocked or disrupted by the policy engine"
        />

        <div className="space-y-3">
          {BENIGN_CHECKS.map((check, i) => (
            <div
              key={i}
              className="p-3.5 rounded-lg bg-[#090D10] border border-[#1E2B27] flex items-start justify-between gap-3 text-xs"
            >
              <div className="flex items-start gap-2.5">
                <div className="w-5 h-5 rounded bg-[#16E6A0]/10 border border-[#16E6A0]/30 flex items-center justify-center text-[#16E6A0] shrink-0 mt-0.5">
                  <CheckIcon className="w-3.5 h-3.5" />
                </div>
                <div>
                  <h4 className="font-semibold text-[#F1F5F4]">{check.name}</h4>
                  <p className="text-xs text-[#91A09D] mt-0.5">{check.description}</p>
                </div>
              </div>
              <Badge tone="emerald" size="sm">PASS</Badge>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
