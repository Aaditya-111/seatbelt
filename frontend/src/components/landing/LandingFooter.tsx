import React from "react";
import Link from "next/link";
import { ShieldIcon } from "@/components/ui/Icons";

export function LandingFooter() {
  return (
    <footer className="border-t border-[#1E2B27] bg-[#090D10] py-12 px-4 sm:px-6 lg:px-8 text-xs text-[#91A09D]">
      <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-8 mb-12">
        {/* Col 1 */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-[#11181D] border border-[#1E2B27] flex items-center justify-center text-[#16E6A0]">
              <ShieldIcon className="w-3.5 h-3.5" />
            </div>
            <span className="font-semibold text-sm text-[#F1F5F4] tracking-tight">Seatbelt</span>
          </div>
          <p className="text-xs leading-relaxed text-[#91A09D]">
            Payment security and policy governance infrastructure for autonomous AI agents. Give agents the ability to transact while keeping humans firmly in control.
          </p>
        </div>

        {/* Col 2 */}
        <div>
          <h4 className="font-mono text-[11px] uppercase tracking-wider text-[#F1F5F4] mb-3">
            Platform
          </h4>
          <ul className="space-y-2">
            <li>
              <a href="#platform" className="hover:text-[#F1F5F4] transition-colors">
                Policy Enforcement Engine
              </a>
            </li>
            <li>
              <a href="#how-it-works" className="hover:text-[#F1F5F4] transition-colors">
                Agent Mandate Authorization
              </a>
            </li>
            <li>
              <a href="#capabilities" className="hover:text-[#F1F5F4] transition-colors">
                Human Approval Workflows
              </a>
            </li>
            <li>
              <Link href="/dashboard" className="hover:text-[#F1F5F4] transition-colors">
                Governance Console
              </Link>
            </li>
          </ul>
        </div>

        {/* Col 3 */}
        <div>
          <h4 className="font-mono text-[11px] uppercase tracking-wider text-[#F1F5F4] mb-3">
            Security & Audit
          </h4>
          <ul className="space-y-2">
            <li>
              <a href="#security" className="hover:text-[#F1F5F4] transition-colors">
                HMAC Hash-Chain Audit Log
              </a>
            </li>
            <li>
              <a href="#security" className="hover:text-[#F1F5F4] transition-colors">
                External Checkpoint Signatures
              </a>
            </li>
            <li>
              <Link href="/dashboard" className="hover:text-[#F1F5F4] transition-colors">
                Adversarial Benchmarks (A01–A15)
              </Link>
            </li>
            <li>
              <a href="#architecture" className="hover:text-[#F1F5F4] transition-colors">
                Fail-Closed Architecture
              </a>
            </li>
          </ul>
        </div>

        {/* Col 4 */}
        <div>
          <h4 className="font-mono text-[11px] uppercase tracking-wider text-[#F1F5F4] mb-3">
            Developer Resources
          </h4>
          <ul className="space-y-2">
            <li>
              <a href="#developers" className="hover:text-[#F1F5F4] transition-colors">
                REST & JSON-RPC API
              </a>
            </li>
            <li>
              <Link href="/dashboard" className="hover:text-[#F1F5F4] transition-colors">
                Agent Playground Simulator
              </Link>
            </li>
            <li>
              <a href="https://github.com" target="_blank" rel="noreferrer" className="hover:text-[#F1F5F4] transition-colors">
                Documentation & Specs
              </a>
            </li>
          </ul>
        </div>
      </div>

      <div className="max-w-7xl mx-auto pt-6 border-t border-[#1E2B27]/60 flex flex-col sm:flex-row items-center justify-between gap-4 text-[11px] text-[#5F716D]">
        <div>© 2026 Seatbelt Infrastructure Inc. All rights reserved.</div>
        <div className="flex items-center gap-6">
          <span>Enterprise Developer Infrastructure</span>
          <span className="w-1 h-1 rounded-full bg-[#1E2B27]" />
          <span>Stateless Signed Admin Sessions</span>
        </div>
      </div>
    </footer>
  );
}
