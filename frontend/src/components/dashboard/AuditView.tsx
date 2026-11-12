"use client";

import React, { useState } from "react";
import { AuditEntry, ChainStatus } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate, shortHash, shortId } from "@/lib/api-client";
import { ShieldCheckIcon, SearchIcon, ArrowRightIcon } from "@/components/ui/Icons";

interface AuditViewProps {
  auditEntries: AuditEntry[];
  auditHealth: ChainStatus | null;
  onNavigate: (tab: string) => void;
}

export function AuditView({
  auditEntries,
  auditHealth,
  onNavigate,
}: AuditViewProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedEntry, setSelectedEntry] = useState<AuditEntry | null>(null);

  const filteredEntries = auditEntries.filter((e) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      e.event.toLowerCase().includes(q) ||
      e.actor.toLowerCase().includes(q) ||
      e.subject_id.toLowerCase().includes(q) ||
      e.hash.toLowerCase().includes(q) ||
      String(e.seq).includes(q)
    );
  });

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-[#F1F5F4]">Immutable Audit Trail</h2>
          <p className="text-xs text-[#91A09D]">
            Forward-secure HMAC-SHA256 hash-chain recording every security decision, verdict, and state change.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {auditHealth && (
            <Badge tone={auditHealth.ok ? "emerald" : "rose"} size="md">
              {auditHealth.ok ? "Chain Valid" : "Chain Broken"}
            </Badge>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => onNavigate("integrity")}
            icon={<ArrowRightIcon className="w-3.5 h-3.5 ml-1 order-last" />}
          >
            Integrity Verification
          </Button>
        </div>
      </div>

      {/* Filter and Search */}
      <Card>
        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search audit trail by Event (e.g. payment.captured), Actor, Subject ID, or Sequence..."
            className="w-full px-3 py-2 pl-9 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
          />
          <SearchIcon className="w-4 h-4 text-[#5F716D] absolute left-3 top-2.5" />
        </div>
      </Card>

      {/* Audit Log Table */}
      <Card>
        <CardHeader
          title={`Audit Records (${filteredEntries.length})`}
          subtitle="Cryptographically linked sequence in SQLite audit store"
        />

        {filteredEntries.length === 0 ? (
          <EmptyState
            icon={<ShieldCheckIcon className="w-5 h-5 text-[#16E6A0]" />}
            title="No audit events found"
            description={
              auditEntries.length === 0
                ? "The audit store has no events yet. Any mandate or payment activity will generate permanent records."
                : "No audit events match your search query."
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[#1E2B27] text-[#91A09D] font-mono text-[11px]">
                  <th className="pb-2.5 font-medium">Seq</th>
                  <th className="pb-2.5 font-medium">Timestamp</th>
                  <th className="pb-2.5 font-medium">Event Type</th>
                  <th className="pb-2.5 font-medium">Actor</th>
                  <th className="pb-2.5 font-medium">Subject ID</th>
                  <th className="pb-2.5 font-medium">HMAC-SHA256 Hash</th>
                  <th className="pb-2.5 font-medium text-right">Payload</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E2B27]/60">
                {filteredEntries.map((e) => (
                  <tr
                    key={e.seq}
                    className="hover:bg-[#151F24]/50 transition-colors cursor-pointer"
                    onClick={() => setSelectedEntry(e)}
                  >
                    <td className="py-2.5 font-mono font-semibold text-[#16E6A0]">
                      #{e.seq}
                    </td>
                    <td className="py-2.5 font-mono text-[#5F716D] text-[11px]">
                      {formatDate(e.ts)}
                    </td>
                    <td className="py-2.5">
                      <span className="font-mono text-xs px-2 py-0.5 rounded bg-[#151F24] text-[#F1F5F4] border border-[#1E2B27]">
                        {e.event}
                      </span>
                    </td>
                    <td className="py-2.5 font-mono text-[#91A09D]">
                      {e.actor}
                    </td>
                    <td className="py-2.5 font-mono text-[#22D3EE]">
                      {shortId(e.subject_id)}
                    </td>
                    <td className="py-2.5 font-mono text-[#5F716D] text-[11px]" title={e.hash}>
                      {shortHash(e.hash)}
                    </td>
                    <td className="py-2.5 text-right font-mono text-[11px] text-[#16E6A0]">
                      Inspect →
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Entry Detail Modal */}
      <Modal
        isOpen={selectedEntry !== null}
        onClose={() => setSelectedEntry(null)}
        title={`Audit Record #${selectedEntry?.seq}`}
        description="Tamper-evident log entry payload with previous-hash link"
        maxWidth="lg"
      >
        {selectedEntry && (
          <div className="space-y-4 pt-1">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Event</span>
                <span className="font-mono text-[#16E6A0]">{selectedEntry.event}</span>
              </div>
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Actor</span>
                <span className="font-mono text-[#F1F5F4]">{selectedEntry.actor}</span>
              </div>
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Subject ID</span>
                <span className="font-mono text-[#22D3EE] break-all">{selectedEntry.subject_id}</span>
              </div>
              <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Timestamp</span>
                <span className="font-mono text-[#F1F5F4]">{formatDate(selectedEntry.ts)}</span>
              </div>
            </div>

            {/* Cryptographic Hashes */}
            <div className="p-3.5 rounded-lg bg-[#090D10] border border-[#1E2B27] space-y-2 text-xs">
              <div>
                <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Previous Hash (Prev)</span>
                <code className="text-[11px] text-[#91A09D] break-all block mt-0.5">
                  {selectedEntry.prev_hash || "0000000000000000000000000000000000000000000000000000000000000000"}
                </code>
              </div>
              <div className="pt-2 border-t border-[#1E2B27]">
                <span className="text-[10px] font-mono text-[#16E6A0] uppercase block">Entry Hash (HMAC-SHA256)</span>
                <code className="text-[11px] text-[#F1F5F4] break-all block mt-0.5">
                  {selectedEntry.hash}
                </code>
              </div>
            </div>

            {/* Data Payload */}
            {selectedEntry.data && (
              <div className="space-y-1.5">
                <span className="text-[10px] font-mono uppercase text-[#91A09D]">Canonical Data Payload</span>
                <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] overflow-x-auto max-h-48">
                  <pre className="font-mono text-[11px] text-[#F1F5F4]">
                    {typeof selectedEntry.data === "string"
                      ? selectedEntry.data
                      : JSON.stringify(selectedEntry.data, null, 2)}
                  </pre>
                </div>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <Button size="sm" variant="ghost" onClick={() => setSelectedEntry(null)}>
                Close
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
