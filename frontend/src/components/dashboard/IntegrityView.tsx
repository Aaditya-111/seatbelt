"use client";

import React, { useState } from "react";
import { ChainStatus } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { verifyAudit, createAuditCheckpoint } from "@/lib/api-client";
import {
  ShieldCheckIcon,
  RefreshCwIcon,
  LockIcon,
  CheckIcon,
} from "@/components/ui/Icons";

interface IntegrityViewProps {
  auditHealth: ChainStatus | null;
  onRefresh: () => void;
}

export function IntegrityView({ auditHealth, onRefresh }: IntegrityViewProps) {
  const [verifying, setVerifying] = useState(false);
  const [checkpointing, setCheckpointing] = useState(false);
  const [actionMessage, setActionMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const handleVerifyNow = async () => {
    setVerifying(true);
    setActionMessage(null);
    try {
      const status = await verifyAudit();
      if (status.ok) {
        setActionMessage({
          type: "success",
          text: `Verification successful. All ${status.entries} entries in the HMAC hash-chain are cryptographically intact.`,
        });
      } else {
        setActionMessage({
          type: "error",
          text: `Verification failed at sequence #${status.first_bad_seq ?? "unknown"}. Audit log tampering or corruption detected.`,
        });
      }
      onRefresh();
    } catch (err) {
      setActionMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Verification request failed.",
      });
    } finally {
      setVerifying(false);
    }
  };

  const handleCreateCheckpoint = async () => {
    setCheckpointing(true);
    setActionMessage(null);
    try {
      const status = await createAuditCheckpoint();
      setActionMessage({
        type: "success",
        text: `Checkpoint created at sequence #${status.head_seq}. Authenticated state snapshot written to external checkpoint file.`,
      });
      onRefresh();
    } catch (err) {
      setActionMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to create checkpoint.",
      });
    } finally {
      setCheckpointing(false);
    }
  };

  const isHealthy = auditHealth?.ok === true;
  const isBroken = auditHealth?.ok === false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-[#F1F5F4]">Audit Integrity & Cryptographic Checkpoints</h2>
          <p className="text-xs text-[#91A09D]">
            Mathematical verification of the HMAC-SHA256 hash-chain and out-of-band rollback detection.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            size="sm"
            variant="outline"
            onClick={handleCreateCheckpoint}
            loading={checkpointing}
            icon={<LockIcon className="w-3.5 h-3.5 text-[#16E6A0]" />}
          >
            Create External Checkpoint
          </Button>
          <Button
            size="sm"
            variant="primary"
            onClick={handleVerifyNow}
            loading={verifying}
            icon={<RefreshCwIcon className="w-3.5 h-3.5" />}
          >
            Verify Chain Now
          </Button>
        </div>
      </div>

      {actionMessage && (
        <div
          className={`p-3.5 rounded-lg border text-xs flex items-center justify-between ${
            actionMessage.type === "success"
              ? "bg-[#16E6A0]/10 border-[#16E6A0]/25 text-[#16E6A0]"
              : "bg-[#F43F5E]/10 border-[#F43F5E]/25 text-[#FB7185]"
          }`}
        >
          <span>{actionMessage.text}</span>
          <button
            onClick={() => setActionMessage(null)}
            className="text-[11px] underline ml-4 hover:opacity-80"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Status Hero Card */}
      <Card variant="elevated">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex items-start gap-4">
            <div
              className={`w-12 h-12 rounded-xl border flex items-center justify-center shrink-0 ${
                isHealthy
                  ? "bg-[#16E6A0]/10 border-[#16E6A0]/30 text-[#16E6A0]"
                  : isBroken
                  ? "bg-[#F43F5E]/10 border-[#F43F5E]/30 text-[#FB7185]"
                  : "bg-[#151F24] border-[#1E2B27] text-[#91A09D]"
              }`}
            >
              <ShieldCheckIcon className="w-6 h-6" />
            </div>

            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-lg font-semibold text-[#F1F5F4]">
                  {isHealthy
                    ? "Cryptographic Chain Verified Intact"
                    : isBroken
                    ? "Integrity Check Failure"
                    : "Verification Not Yet Executed"}
                </h3>
                <Badge
                  tone={isHealthy ? "emerald" : isBroken ? "rose" : "neutral"}
                  size="md"
                >
                  {isHealthy ? "Healthy" : isBroken ? "Tampered / Broken" : "Unverified"}
                </Badge>
              </div>

              <p className="text-xs text-[#91A09D] mt-1.5 max-w-2xl leading-relaxed">
                {isHealthy
                  ? `Every audit log entry from sequence #1 to head sequence #${auditHealth?.head_seq ?? 0} has been verified against the master HMAC key. No entries have been inserted, modified, or omitted.`
                  : isBroken
                  ? `HMAC signature verification failed at sequence #${auditHealth?.first_bad_seq ?? "unknown"}. Seatbelt policy engine has failed-closed to protect payment security.`
                  : "Click 'Verify Chain Now' to execute the HMAC verification routine against the local database."}
              </p>
            </div>
          </div>
        </div>

        {/* Status Metrics Bar */}
        <div className="mt-6 pt-6 border-t border-[#1E2B27] grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <div className="text-[11px] font-mono text-[#91A09D]">Verified Entries</div>
            <div className="text-xl font-bold font-mono text-[#F1F5F4] mt-1">
              {auditHealth ? auditHealth.entries : "—"}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-mono text-[#91A09D]">Head Sequence</div>
            <div className="text-xl font-bold font-mono text-[#16E6A0] mt-1">
              {auditHealth?.head_seq !== null && auditHealth?.head_seq !== undefined ? `#${auditHealth.head_seq}` : "—"}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-mono text-[#91A09D]">External Checkpoint</div>
            <div className="text-sm font-semibold font-mono text-[#F1F5F4] mt-1">
              {auditHealth?.checkpoint_ok === true ? (
                <span className="text-[#16E6A0]">Matches Chain</span>
              ) : auditHealth?.checkpoint_ok === false ? (
                <span className="text-[#FB7185]">Mismatch / Rollback</span>
              ) : (
                <span className="text-[#5F716D]">No Checkpoint File</span>
              )}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-mono text-[#91A09D]">Checkpoint Seq</div>
            <div className="text-xl font-bold font-mono text-[#22D3EE] mt-1">
              {auditHealth?.checkpoint_seq !== null && auditHealth?.checkpoint_seq !== undefined
                ? `#${auditHealth.checkpoint_seq}`
                : "—"}
            </div>
          </div>
        </div>

        {/* Head Hash display */}
        {auditHealth?.head_hash && (
          <div className="mt-4 pt-4 border-t border-[#1E2B27]/60">
            <span className="text-[10px] font-mono uppercase text-[#5F716D] block">
              Head Hash Digest (SHA-256 HMAC)
            </span>
            <code className="text-[11px] text-[#F1F5F4] font-mono break-all block mt-1 bg-[#090D10] p-2 rounded border border-[#1E2B27]">
              {auditHealth.head_hash}
            </code>
          </div>
        )}
      </Card>

      {/* Security Properties Explanation Card */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader
            title="HMAC Hash-Chaining Properties"
            subtitle="How historical records are protected against tampering"
          />
          <ul className="space-y-3 text-xs text-[#91A09D]">
            <li className="flex items-start gap-2">
              <CheckIcon className="w-4 h-4 text-[#16E6A0] shrink-0 mt-0.5" />
              <span>
                <strong className="text-[#F1F5F4]">HMAC-SHA256 link:</strong> Each entry hash incorporates the previous entry&apos;s digest and all entry fields: <code className="text-[#16E6A0] text-[10px]">[seq, ts, event, actor, subject, data, prev_hash]</code>.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <CheckIcon className="w-4 h-4 text-[#16E6A0] shrink-0 mt-0.5" />
              <span>
                <strong className="text-[#F1F5F4]">Secret-derived key:</strong> An adversary who modifies SQLite directly cannot forge new hashes without the signing key.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <CheckIcon className="w-4 h-4 text-[#16E6A0] shrink-0 mt-0.5" />
              <span>
                <strong className="text-[#F1F5F4]">Chain verification:</strong> The engine iterates sequentially from genesis. If any byte was modified, verification stops immediately at <code className="text-[#FB7185] text-[10px]">first_bad_seq</code>.
              </span>
            </li>
          </ul>
        </Card>

        <Card>
          <CardHeader
            title="External Checkpoint Rollback Protection"
            subtitle="Preventing silent log truncation and rollback attacks"
          />
          <ul className="space-y-3 text-xs text-[#91A09D]">
            <li className="flex items-start gap-2">
              <CheckIcon className="w-4 h-4 text-[#16E6A0] shrink-0 mt-0.5" />
              <span>
                <strong className="text-[#F1F5F4]">Out-of-band file:</strong> Checkpoints are written to an external authenticated file outside the SQLite database.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <CheckIcon className="w-4 h-4 text-[#16E6A0] shrink-0 mt-0.5" />
              <span>
                <strong className="text-[#F1F5F4]">Rollback detection:</strong> If an attacker deletes recent rows from SQLite, the checkpoint sequence will be higher than the database head sequence, raising a fatal integrity alert.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <CheckIcon className="w-4 h-4 text-[#16E6A0] shrink-0 mt-0.5" />
              <span>
                <strong className="text-[#F1F5F4]">Signature verification:</strong> Checkpoint payloads are signed with an HMAC digest to prevent checkpoint file modification.
              </span>
            </li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
