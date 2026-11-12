"use client";

import React, { useState, useEffect, useCallback } from "react";
import { AppSidebar, NavTab } from "@/components/layout/AppSidebar";
import { AppHeader } from "@/components/layout/AppHeader";
import { OverviewView } from "@/components/dashboard/OverviewView";
import { AgentsView } from "@/components/dashboard/AgentsView";
import { PoliciesView } from "@/components/dashboard/PoliciesView";
import { ApprovalsView } from "@/components/dashboard/ApprovalsView";
import { TransactionsView } from "@/components/dashboard/TransactionsView";
import { AuditView } from "@/components/dashboard/AuditView";
import { IntegrityView } from "@/components/dashboard/IntegrityView";
import { BenchmarksView } from "@/components/dashboard/BenchmarksView";
import { ProvidersView } from "@/components/dashboard/ProvidersView";
import { PlaygroundView } from "@/components/dashboard/PlaygroundView";
import { SettingsView } from "@/components/dashboard/SettingsView";
import { IssueMandateModal } from "@/components/dashboard/IssueMandateModal";
import { SignInModal } from "@/components/dashboard/SignInModal";
import {
  PaymentRecord,
  AuditEntry,
  ChainStatus,
} from "@/lib/types";
import {
  checkAdminSession,
  logoutAdmin,
  getHealth,
  listPayments,
  listAudit,
  verifyAudit,
} from "@/lib/api-client";

export default function DashboardPage() {
  const [currentTab, setCurrentTab] = useState<NavTab>("overview");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [health, setHealth] = useState<"checking" | "online" | "offline">("checking");
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Core Data
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
  const [auditHealth, setAuditHealth] = useState<ChainStatus | null>(null);

  const [refreshing, setRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  // Modals
  const [signInOpen, setSignInOpen] = useState(false);
  const [issueMandateOpen, setIssueMandateOpen] = useState(false);

  // Fetch full data after auth check
  const refreshData = useCallback(async () => {
    setRefreshing(true);
    setErrorMessage("");

    try {
      const isAuthed = await checkAdminSession();
      setIsAuthenticated(isAuthed);

      if (isAuthed) {
        const [paymentsRes, auditRes, verifyRes] = await Promise.allSettled([
          listPayments({ limit: 100 }),
          listAudit(100),
          verifyAudit(),
        ]);

        if (paymentsRes.status === "fulfilled") {
          setPayments(Array.isArray(paymentsRes.value) ? paymentsRes.value : []);
        }
        if (auditRes.status === "fulfilled") {
          setAuditEntries(Array.isArray(auditRes.value) ? auditRes.value : []);
        }
        if (verifyRes.status === "fulfilled") {
          setAuditHealth(verifyRes.value);
        }
      } else {
        setPayments([]);
        setAuditEntries([]);
        setAuditHealth(null);
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Error refreshing dashboard data.");
    } finally {
      setRefreshing(false);
    }
  }, []);

  // Initial and reactive effect
  useEffect(() => {
    let active = true;

    async function load() {
      try {
        await getHealth();
        if (active) setHealth("online");
      } catch {
        if (active) setHealth("offline");
      }

      try {
        const isAuthed = await checkAdminSession();
        if (!active) return;
        setIsAuthenticated(isAuthed);

        if (isAuthed) {
          const [paymentsRes, auditRes, verifyRes] = await Promise.allSettled([
            listPayments({ limit: 100 }),
            listAudit(100),
            verifyAudit(),
          ]);

          if (!active) return;
          if (paymentsRes.status === "fulfilled") {
            setPayments(Array.isArray(paymentsRes.value) ? paymentsRes.value : []);
          }
          if (auditRes.status === "fulfilled") {
            setAuditEntries(Array.isArray(auditRes.value) ? auditRes.value : []);
          }
          if (verifyRes.status === "fulfilled") {
            setAuditHealth(verifyRes.value);
          }
        }
      } catch (err) {
        if (active) {
          setErrorMessage(err instanceof Error ? err.message : "Failed to load state.");
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [currentTab]);

  // Periodic health check
  useEffect(() => {
    const timer = setInterval(() => {
      void getHealth()
        .then(() => setHealth("online"))
        .catch(() => setHealth("offline"));
    }, 15000);
    return () => clearInterval(timer);
  }, []);

  const handleSignOut = async () => {
    await logoutAdmin();
    setIsAuthenticated(false);
    setPayments([]);
    setAuditEntries([]);
    setAuditHealth(null);
    setCurrentTab("overview");
  };

  const pendingApprovalsCount = payments.filter((p) => p.status === "pending_approval").length;

  return (
    <div className="seatbelt-dashboard flex min-h-screen bg-[#090D10] text-[#F1F5F4]">
      {/* Sidebar Navigation */}
      <AppSidebar
        currentTab={currentTab}
        onSelectTab={(tab) => setCurrentTab(tab)}
        pendingApprovalsCount={pendingApprovalsCount}
        isAuthenticated={isAuthenticated}
        onOpenSignIn={() => setSignInOpen(true)}
        onSignOut={handleSignOut}
        isOpenMobile={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        <AppHeader
          currentTab={currentTab}
          onOpenMobile={() => setMobileOpen(true)}
          health={health}
          onRefresh={refreshData}
          refreshing={refreshing}
        />

        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {/* Unauthenticated Alert Banner */}
          {!isAuthenticated && currentTab !== "playground" && currentTab !== "benchmarks" && currentTab !== "policies" && (
            <div className="mb-6 p-4 rounded-xl bg-[#11181D] border border-[#1E2B27] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <h4 className="text-xs font-semibold text-[#F1F5F4]">
                  Admin Session Not Established
                </h4>
                <p className="text-xs text-[#91A09D] mt-0.5">
                  Sign in with your configured admin API key to view live payments, inspect the audit trail, and authorize approvals.
                </p>
              </div>
              <button
                onClick={() => setSignInOpen(true)}
                className="text-xs font-semibold text-[#090D10] bg-[#16E6A0] hover:bg-[#1FF0AB] px-3.5 py-1.5 rounded-md transition-colors whitespace-nowrap"
              >
                Sign In as Admin
              </button>
            </div>
          )}

          {errorMessage && (
            <div className="mb-6 p-3.5 rounded-lg bg-[#F43F5E]/10 border border-[#F43F5E]/20 text-[#FB7185] text-xs">
              {errorMessage}
            </div>
          )}

          {/* Tab Views */}
          {currentTab === "overview" && (
            <OverviewView
              payments={payments}
              auditHealth={auditHealth}
              onNavigate={(tab) => setCurrentTab(tab as NavTab)}
              onOpenIssueMandate={() => setIssueMandateOpen(true)}
            />
          )}

          {currentTab === "agents" && (
            <AgentsView
              payments={payments}
              onOpenIssueMandate={() => setIssueMandateOpen(true)}
            />
          )}

          {currentTab === "policies" && <PoliciesView />}

          {currentTab === "approvals" && (
            <ApprovalsView payments={payments} onRefresh={refreshData} />
          )}

          {currentTab === "transactions" && (
            <TransactionsView payments={payments} onRefresh={refreshData} />
          )}

          {currentTab === "audit" && (
            <AuditView
              auditEntries={auditEntries}
              auditHealth={auditHealth}
              onNavigate={(tab) => setCurrentTab(tab as NavTab)}
            />
          )}

          {currentTab === "integrity" && (
            <IntegrityView auditHealth={auditHealth} onRefresh={refreshData} />
          )}

          {currentTab === "benchmarks" && <BenchmarksView />}

          {currentTab === "providers" && <ProvidersView />}

          {currentTab === "playground" && (
            <PlaygroundView
              onPaymentSuccess={refreshData}
              onOpenIssueMandate={() => setIssueMandateOpen(true)}
            />
          )}

          {currentTab === "settings" && (
            <SettingsView isAuthenticated={isAuthenticated} health={health} />
          )}
        </main>
      </div>

      {/* Modals */}
      <SignInModal
        isOpen={signInOpen}
        onClose={() => setSignInOpen(false)}
        onSuccess={() => {
          setIsAuthenticated(true);
          void refreshData();
        }}
      />

      <IssueMandateModal
        isOpen={issueMandateOpen}
        onClose={() => setIssueMandateOpen(false)}
        onMandateIssued={() => {
          void refreshData();
        }}
      />
    </div>
  );
}
