"use client";

import React from "react";
import { RefreshCwIcon } from "@/components/ui/Icons";
import { Button } from "@/components/ui/Button";

interface AppHeaderProps {
  currentTab: string;
  onOpenMobile: () => void;
  health: "checking" | "online" | "offline";
  onRefresh: () => void;
  refreshing: boolean;
}

export function AppHeader({
  currentTab,
  onOpenMobile,
  health,
  onRefresh,
  refreshing,
}: AppHeaderProps) {
  const titles: Record<string, { title: string; subtitle: string }> = {
    overview: { title: "Overview", subtitle: "Real-time security telemetry and transaction metrics" },
    agents: { title: "Agents & Mandates", subtitle: "Registered agent identities and spending permissions" },
    policies: { title: "Policy Engine", subtitle: "Deterministic spending boundaries and approval thresholds" },
    approvals: { title: "Approval Queue", subtitle: "High-value transactions requiring human sign-off" },
    transactions: { title: "Transactions", subtitle: "Searchable ledger of all evaluated agent payments" },
    audit: { title: "Audit Trail", subtitle: "Chronological HMAC-SHA256 hash-chained event history" },
    integrity: { title: "Audit Integrity", subtitle: "Cryptographic chain verification and external checkpoints" },
    benchmarks: { title: "Adversarial Benchmarks", subtitle: "Test coverage across 15 attack vectors and 5 benign checks" },
    providers: { title: "Payment Providers", subtitle: "Configured payment rails and gateway connections" },
    playground: { title: "Agent Playground", subtitle: "Simulate agent payments with mandate bearer tokens" },
    settings: { title: "Developer Settings", subtitle: "Backend configuration, environment, and API references" },
  };

  const current = titles[currentTab] || { title: "Seatbelt Console", subtitle: "Governance Platform" };

  return (
    <header className="h-16 border-b border-[#1E2B27] bg-[#090D10]/80 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between gap-4 sticky top-0 z-30">
      {/* Mobile Menu Button + Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenMobile}
          className="lg:hidden p-1.5 rounded-md text-[#91A09D] hover:text-[#F1F5F4] hover:bg-[#11181D]"
          aria-label="Open sidebar"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <div>
          <h1 className="text-sm font-semibold text-[#F1F5F4] tracking-tight flex items-center gap-2">
            <span>{current.title}</span>
          </h1>
          <p className="text-[11px] text-[#91A09D] hidden sm:block">
            {current.subtitle}
          </p>
        </div>
      </div>

      {/* Right Telemetry Controls */}
      <div className="flex items-center gap-3">
        {/* Backend Health Badge */}
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-[#11181D] border border-[#1E2B27] text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              health === "online"
                ? "bg-[#16E6A0] shadow-[0_0_6px_#16E6A0]"
                : health === "checking"
                ? "bg-[#F59E0B] animate-pulse"
                : "bg-[#F43F5E]"
            }`}
          />
          <span className="font-mono text-[11px] text-[#91A09D]">
            {health === "online" ? "FastAPI Online" : health === "checking" ? "Checking..." : "Backend Offline"}
          </span>
        </div>

        {/* Refresh button */}
        <Button
          variant="outline"
          size="sm"
          onClick={onRefresh}
          loading={refreshing}
          icon={<RefreshCwIcon className="w-3.5 h-3.5 text-[#91A09D]" />}
        >
          <span className="hidden sm:inline">Sync</span>
        </Button>
      </div>
    </header>
  );
}
