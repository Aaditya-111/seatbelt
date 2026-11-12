"use client";

import React from "react";
import Link from "next/link";
import {
  ShieldIcon,
  ActivityIcon,
  UsersIcon,
  ScaleIcon,
  FileCheckIcon,
  LayersIcon,
  ShieldCheckIcon,
  TerminalIcon,
  LockIcon,
  LogOutIcon,
  KeyIcon,
} from "@/components/ui/Icons";

export type NavTab =
  | "overview"
  | "agents"
  | "policies"
  | "approvals"
  | "transactions"
  | "audit"
  | "integrity"
  | "benchmarks"
  | "providers"
  | "settings"
  | "playground";

interface AppSidebarProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  pendingApprovalsCount: number;
  isAuthenticated: boolean;
  onOpenSignIn: () => void;
  onSignOut: () => void;
  isOpenMobile: boolean;
  onCloseMobile: () => void;
}

export function AppSidebar({
  currentTab,
  onSelectTab,
  pendingApprovalsCount,
  isAuthenticated,
  onOpenSignIn,
  onSignOut,
  isOpenMobile,
  onCloseMobile,
}: AppSidebarProps) {
  const navSections = [
    {
      title: "Overview",
      items: [
        { id: "overview" as NavTab, label: "Overview", icon: <ActivityIcon className="w-4 h-4" /> },
      ],
    },
    {
      title: "Governance",
      items: [
        { id: "agents" as NavTab, label: "Agents", icon: <UsersIcon className="w-4 h-4" /> },
        { id: "policies" as NavTab, label: "Policies", icon: <ScaleIcon className="w-4 h-4" /> },
        {
          id: "approvals" as NavTab,
          label: "Approvals",
          icon: <FileCheckIcon className="w-4 h-4" />,
          badge: pendingApprovalsCount > 0 ? pendingApprovalsCount : undefined,
        },
        { id: "transactions" as NavTab, label: "Transactions", icon: <LayersIcon className="w-4 h-4" /> },
      ],
    },
    {
      title: "Security",
      items: [
        { id: "audit" as NavTab, label: "Audit Trail", icon: <ShieldIcon className="w-4 h-4" /> },
        { id: "integrity" as NavTab, label: "Integrity", icon: <ShieldCheckIcon className="w-4 h-4" /> },
        { id: "benchmarks" as NavTab, label: "Benchmarks", icon: <TerminalIcon className="w-4 h-4" /> },
      ],
    },
    {
      title: "Integrations & Tools",
      items: [
        { id: "providers" as NavTab, label: "Payment Providers", icon: <LockIcon className="w-4 h-4" /> },
        { id: "playground" as NavTab, label: "Agent Playground", icon: <KeyIcon className="w-4 h-4" /> },
        { id: "settings" as NavTab, label: "Developer Settings", icon: <TerminalIcon className="w-4 h-4" /> },
      ],
    },
  ];

  const handleSelect = (tab: NavTab) => {
    onSelectTab(tab);
    onCloseMobile();
  };

  const sidebarContent = (
    <div className="flex flex-col h-full bg-[#0C1216] border-r border-[#1E2B27] w-64 select-none">
      {/* Brand */}
      <div className="p-4 border-b border-[#1E2B27] flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-[#11181D] border border-[#1E2B27] flex items-center justify-center text-[#16E6A0]">
            <ShieldIcon className="w-3.5 h-3.5" />
          </div>
          <div>
            <span className="font-semibold text-xs tracking-tight text-[#F1F5F4] block">
              Seatbelt
            </span>
            <span className="text-[10px] text-[#5F716D] font-mono block -mt-0.5">
              Control Plane
            </span>
          </div>
        </Link>
        <span className="text-[10px] font-mono text-[#5F716D] px-1.5 py-0.5 rounded bg-[#11181D] border border-[#1E2B27]">
          v0.1
        </span>
      </div>

      {/* Nav Items */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {navSections.map((section) => (
          <div key={section.title} className="space-y-1">
            <div className="px-2.5 mb-1.5 text-[10px] font-mono uppercase tracking-wider text-[#5F716D]">
              {section.title}
            </div>
            {section.items.map((item) => {
              const active = currentTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => handleSelect(item.id)}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    active
                      ? "bg-[#151F24] text-[#16E6A0] border border-[#233530]"
                      : "text-[#91A09D] hover:text-[#F1F5F4] hover:bg-[#11181D] border border-transparent"
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <span className={active ? "text-[#16E6A0]" : "text-[#5F716D]"}>
                      {item.icon}
                    </span>
                    <span>{item.label}</span>
                  </div>
                  {item.badge !== undefined && (
                    <span className="font-mono text-[10px] px-1.5 py-0.2 rounded-full bg-[#F59E0B]/20 text-[#FBBF24] border border-[#F59E0B]/30">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </div>

      {/* Session Controls Bottom */}
      <div className="p-3 border-t border-[#1E2B27] bg-[#090D10]/50 space-y-2">
        <div className="px-2 py-1 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                isAuthenticated ? "bg-[#16E6A0] shadow-[0_0_8px_#16e6a0]" : "bg-[#F43F5E]"
              }`}
            />
            <span className="text-[11px] font-mono text-[#91A09D]">
              {isAuthenticated ? "Admin Session" : "Unauthenticated"}
            </span>
          </div>
          {isAuthenticated ? (
            <button
              onClick={onSignOut}
              className="text-[#91A09D] hover:text-[#FB7185] p-1 rounded hover:bg-[#151F24] transition-colors"
              title="Sign Out"
            >
              <LogOutIcon className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button
              onClick={onOpenSignIn}
              className="text-[11px] font-medium text-[#16E6A0] hover:underline"
            >
              Sign In
            </button>
          )}
        </div>
        <div className="px-2 text-[10px] text-[#5F716D] font-mono">
          {isAuthenticated
            ? "30m signed cookie active"
            : "Read-only / agent mode"}
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside className="hidden lg:block h-screen sticky top-0 flex-shrink-0">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer */}
      {isOpenMobile && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black/75 backdrop-blur-xs"
            onClick={onCloseMobile}
            aria-hidden="true"
          />
          <div className="relative z-10 w-64">{sidebarContent}</div>
        </div>
      )}
    </>
  );
}
