"use client";

import React from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { CheckIcon } from "@/components/ui/Icons";

export function ProvidersView() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-[#F1F5F4]">Payment Provider Integrations</h2>
        <p className="text-xs text-[#91A09D]">
          Payment execution rails connected to the Seatbelt policy engine. Credentials are maintained strictly server-side.
        </p>
      </div>

      {/* Active Provider Card: PayPal */}
      <Card variant="elevated">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-[#1E2B27]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#151F24] border border-[#1E2B27] flex items-center justify-center font-bold text-sm text-[#F1F5F4]">
              PP
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-[#F1F5F4]">PayPal Orders v2</h3>
                <Badge tone="emerald" size="sm">Active Integration</Badge>
              </div>
              <p className="text-xs text-[#91A09D] mt-0.5">
                Full order creation, authorization, webhook postback verification, and order capture.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone="cyan" size="sm">Sandbox Environment</Badge>
          </div>
        </div>

        {/* Integration Details Grid */}
        <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
            <span className="text-[10px] font-mono uppercase text-[#5F716D] block">Environment</span>
            <span className="font-mono text-[#F1F5F4] font-medium">PAYPAL_ENV: sandbox</span>
            <span className="text-[11px] text-[#91A09D] block mt-0.5">Live mode refused by default</span>
          </div>

          <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
            <span className="text-[10px] font-mono uppercase text-[#5F716D] block">Webhook Verification</span>
            <span className="font-mono text-[#16E6A0] font-medium">Cert-URL & Sig Checks</span>
            <span className="text-[11px] text-[#91A09D] block mt-0.5">POST /v1/paypal/webhook</span>
          </div>

          <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
            <span className="text-[10px] font-mono uppercase text-[#5F716D] block">Idempotency & Retries</span>
            <span className="font-mono text-[#22D3EE] font-medium">Max 3 retries</span>
            <span className="text-[11px] text-[#91A09D] block mt-0.5">20s timeout with backoff</span>
          </div>
        </div>

        {/* Provider Capabilities */}
        <div className="mt-4 pt-4 border-t border-[#1E2B27] flex flex-wrap gap-4 text-xs text-[#91A09D]">
          <div className="flex items-center gap-1.5">
            <CheckIcon className="w-3.5 h-3.5 text-[#16E6A0]" />
            <span>Orders API v2</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckIcon className="w-3.5 h-3.5 text-[#16E6A0]" />
            <span>Pre-flight rounding parity</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckIcon className="w-3.5 h-3.5 text-[#16E6A0]" />
            <span>Webhook signature verification</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckIcon className="w-3.5 h-3.5 text-[#16E6A0]" />
            <span>Single-charge idempotency</span>
          </div>
        </div>
      </Card>

      {/* Internal Mock / Executor Provider */}
      <Card>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#151F24] border border-[#1E2B27] flex items-center justify-center font-bold text-sm text-[#91A09D]">
              EX
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-[#F1F5F4]">Internal Ledger Executor</h3>
                <Badge tone="cyan" size="sm">Simulation / Test Rail</Badge>
              </div>
              <p className="text-xs text-[#91A09D] mt-0.5">
                Simulated execution channel used for unit tests and local agent simulations.
              </p>
            </div>
          </div>
          <Badge tone="emerald" size="sm">Available</Badge>
        </div>
      </Card>

      {/* Planned Future Providers (Explicitly labeled as Planned) */}
      <Card>
        <CardHeader
          title="Planned Provider Integrations"
          subtitle="Additional payment networks scheduled for future releases"
        />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 rounded-lg bg-[#090D10] border border-[#1E2B27] space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-[#F1F5F4]">Stripe</span>
              <Badge tone="neutral" size="sm">Planned</Badge>
            </div>
            <p className="text-[11px] text-[#91A09D]">
              PaymentIntents and Treasury APIs for multi-currency agent payouts.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-[#090D10] border border-[#1E2B27] space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-[#F1F5F4]">Adyen</span>
              <Badge tone="neutral" size="sm">Planned</Badge>
            </div>
            <p className="text-[11px] text-[#91A09D]">
              Global merchant acquiring and omnichannel checkout infrastructure.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-[#090D10] border border-[#1E2B27] space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-[#F1F5F4]">Circle (USDC)</span>
              <Badge tone="neutral" size="sm">Planned</Badge>
            </div>
            <p className="text-[11px] text-[#91A09D]">
              Programmable web3 wallets and stablecoin settlement rails for autonomous agents.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
