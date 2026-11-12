"use client";

import React from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { CheckIcon } from "@/components/ui/Icons";

interface SettingsViewProps {
  isAuthenticated: boolean;
  health: "checking" | "online" | "offline";
}

export function SettingsView({ isAuthenticated, health }: SettingsViewProps) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-[#F1F5F4]">Developer Settings & Security Controls</h2>
        <p className="text-xs text-[#91A09D]">
          Frontend-to-backend proxy configuration, session parameters, and API integration specifications.
        </p>
      </div>

      {/* Gateway Telemetry */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <div className="text-[11px] font-mono text-[#91A09D] uppercase">FastAPI Backend Status</div>
          <div className="text-lg font-bold font-mono text-[#F1F5F4] mt-1 flex items-center gap-2">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                health === "online" ? "bg-[#16E6A0]" : "bg-[#F43F5E]"
              }`}
            />
            <span>{health === "online" ? "Online (8080)" : "Offline"}</span>
          </div>
          <div className="text-[11px] text-[#91A09D] mt-1 font-mono">SEATBELT_BACKEND_URL</div>
        </Card>

        <Card>
          <div className="text-[11px] font-mono text-[#91A09D] uppercase">Admin Session Layer</div>
          <div className="text-lg font-bold font-mono text-[#16E6A0] mt-1">
            {isAuthenticated ? "Signed Cookie Active" : "Unauthenticated"}
          </div>
          <div className="text-[11px] text-[#91A09D] mt-1 font-mono">30-min stateless HMAC</div>
        </Card>

        <Card>
          <div className="text-[11px] font-mono text-[#91A09D] uppercase">Proxy Auth Architecture</div>
          <div className="text-lg font-bold font-mono text-[#22D3EE] mt-1">
            Server Injected
          </div>
          <div className="text-[11px] text-[#91A09D] mt-1 font-mono">x-seatbelt-admin-request</div>
        </Card>
      </div>

      {/* Security Architecture Reference */}
      <Card>
        <CardHeader
          title="Security Invariants & Proxy Guarantees"
          subtitle="Enforced by the Next.js API gateway proxy"
        />

        <div className="space-y-3 text-xs text-[#91A09D]">
          <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] flex items-start gap-2.5">
            <CheckIcon className="w-4 h-4 text-[#16E6A0] shrink-0 mt-0.5" />
            <div>
              <strong className="text-[#F1F5F4] block">Zero Client Credential Exposure:</strong>
              The backend <code className="text-[#16E6A0]">SEATBELT_ADMIN_API_KEY</code> is never sent to the browser, stored in localStorage, or exposed in client bundles.
            </div>
          </div>

          <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] flex items-start gap-2.5">
            <CheckIcon className="w-4 h-4 text-[#16E6A0] shrink-0 mt-0.5" />
            <div>
              <strong className="text-[#F1F5F4] block">Strict SameSite & HttpOnly Cookies:</strong>
              Admin sessions are established by exchanging the key for an HttpOnly, SameSite=Strict cryptographic cookie. The proxy attaches the admin Bearer credential only after validating the signature.
            </div>
          </div>

          <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] flex items-start gap-2.5">
            <CheckIcon className="w-4 h-4 text-[#16E6A0] shrink-0 mt-0.5" />
            <div>
              <strong className="text-[#F1F5F4] block">Independent Agent Mandate Path:</strong>
              Autonomous agents submit transactions with <code className="text-[#16E6A0]">Authorization: Bearer &lt;mandate_token&gt;</code> without administrative headers, ensuring total privilege separation.
            </div>
          </div>
        </div>
      </Card>

      {/* API Reference Cheatsheet */}
      <Card>
        <CardHeader
          title="Core API Endpoints"
          subtitle="Available HTTP routes on the FastAPI service"
        />

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-[#1E2B27] text-[#91A09D] text-[11px]">
                <th className="pb-2.5 font-medium">Method</th>
                <th className="pb-2.5 font-medium">Endpoint</th>
                <th className="pb-2.5 font-medium">Caller</th>
                <th className="pb-2.5 font-medium">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1E2B27]/60">
              <tr>
                <td className="py-2 text-[#16E6A0]">POST</td>
                <td className="py-2 text-[#F1F5F4]">/v1/mandates</td>
                <td className="py-2 text-[#FBBF24]">Admin</td>
                <td className="py-2 text-[#91A09D] font-sans">Issue a signed spending mandate</td>
              </tr>
              <tr>
                <td className="py-2 text-[#22D3EE]">GET</td>
                <td className="py-2 text-[#F1F5F4]">/v1/mandates/&#123;id&#125;</td>
                <td className="py-2 text-[#FBBF24]">Admin</td>
                <td className="py-2 text-[#91A09D] font-sans">Inspect mandate budget state</td>
              </tr>
              <tr>
                <td className="py-2 text-[#16E6A0]">POST</td>
                <td className="py-2 text-[#F1F5F4]">/v1/paypal/payments</td>
                <td className="py-2 text-[#22D3EE]">Agent</td>
                <td className="py-2 text-[#91A09D] font-sans">Submit PayPal payment via mandate</td>
              </tr>
              <tr>
                <td className="py-2 text-[#22D3EE]">GET</td>
                <td className="py-2 text-[#F1F5F4]">/v1/payments</td>
                <td className="py-2 text-[#FBBF24]">Admin</td>
                <td className="py-2 text-[#91A09D] font-sans">List payments with status filters</td>
              </tr>
              <tr>
                <td className="py-2 text-[#16E6A0]">POST</td>
                <td className="py-2 text-[#F1F5F4]">/v1/payments/&#123;id&#125;/approve</td>
                <td className="py-2 text-[#FBBF24]">Admin</td>
                <td className="py-2 text-[#91A09D] font-sans">Human approve held payment</td>
              </tr>
              <tr>
                <td className="py-2 text-[#22D3EE]">GET</td>
                <td className="py-2 text-[#F1F5F4]">/v1/audit/verify</td>
                <td className="py-2 text-[#FBBF24]">Admin</td>
                <td className="py-2 text-[#91A09D] font-sans">Verify HMAC-SHA256 audit chain</td>
              </tr>
              <tr>
                <td className="py-2 text-[#16E6A0]">POST</td>
                <td className="py-2 text-[#F1F5F4]">/v1/audit/checkpoint</td>
                <td className="py-2 text-[#FBBF24]">Admin</td>
                <td className="py-2 text-[#91A09D] font-sans">Create signed rollback checkpoint</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
