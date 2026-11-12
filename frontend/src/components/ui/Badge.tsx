import React from "react";
import { PaymentStatus, Verdict } from "@/lib/types";

type BadgeTone = "emerald" | "cyan" | "amber" | "rose" | "neutral";

interface BadgeProps {
  children?: React.ReactNode;
  tone?: BadgeTone;
  status?: PaymentStatus | Verdict | string;
  size?: "sm" | "md";
  className?: string;
}

export function Badge({ children, tone, status, size = "sm", className = "" }: BadgeProps) {
  let resolvedTone: BadgeTone = tone || "neutral";

  if (status) {
    switch (status) {
      case "captured":
      case "allow":
      case "verified":
      case "ok":
      case "online":
        resolvedTone = "emerald";
        break;
      case "pending_approval":
      case "require_approval":
      case "reserved":
        resolvedTone = "amber";
        break;
      case "awaiting_payer":
        resolvedTone = "cyan";
        break;
      case "denied":
      case "rejected":
      case "failed":
      case "offline":
      case "cancelled":
        resolvedTone = "rose";
        break;
      default:
        resolvedTone = "neutral";
    }
  }

  const toneStyles: Record<BadgeTone, string> = {
    emerald: "bg-[#16E6A0]/10 text-[#16E6A0] border-[#16E6A0]/25",
    cyan: "bg-[#22D3EE]/10 text-[#22D3EE] border-[#22D3EE]/25",
    amber: "bg-[#F59E0B]/10 text-[#FBBF24] border-[#F59E0B]/25",
    rose: "bg-[#F43F5E]/10 text-[#FB7185] border-[#F43F5E]/25",
    neutral: "bg-[#151F24] text-[#91A09D] border-[#1E2B27]",
  };

  const dotColors: Record<BadgeTone, string> = {
    emerald: "bg-[#16E6A0]",
    cyan: "bg-[#22D3EE]",
    amber: "bg-[#FBBF24]",
    rose: "bg-[#FB7185]",
    neutral: "bg-[#91A09D]",
  };

  const sizeStyles = {
    sm: "text-[11px] px-2 py-0.5 gap-1.5",
    md: "text-xs px-2.5 py-1 gap-2",
  };

  const displayText = children ?? (status ? status.replace(/_/g, " ") : "");

  return (
    <span
      className={`inline-flex items-center font-mono font-medium tracking-wide uppercase rounded-md border ${toneStyles[resolvedTone]} ${sizeStyles[size]} ${className}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColors[resolvedTone]}`} />
      <span>{displayText}</span>
    </span>
  );
}
