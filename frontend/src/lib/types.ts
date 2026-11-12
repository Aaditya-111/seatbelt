export type PaymentStatus =
  | "denied"
  | "pending_approval"
  | "reserved"
  | "awaiting_payer"
  | "captured"
  | "rejected"
  | "failed"
  | "cancelled";

export type PaymentChannel = "executor" | "paypal";

export type Verdict = "allow" | "require_approval" | "deny";

export type ReasonEffect = "deny" | "approve" | "info";

export type ReasonCode =
  | "within_mandate"
  | "agent_mismatch"
  | "currency_mismatch"
  | "payee_not_allowed"
  | "exceeds_per_payment_limit"
  | "exceeds_total_limit"
  | "mandate_expired"
  | "mandate_not_yet_valid"
  | "above_approval_threshold"
  | "near_budget_limit"
  | "risk_signal";

export interface PolicyReason {
  code: ReasonCode | string;
  effect: ReasonEffect;
  message: string;
}

export interface PaymentRecord {
  payment_id: string;
  mandate_id: string;
  request_id: string;
  agent_id: string;
  payee: string;
  amount: string | number;
  currency: string;
  description: string;
  status: PaymentStatus;
  verdict: Verdict;
  reasons?: PolicyReason[];
  payment_channel?: PaymentChannel;
  paypal_order_id?: string | null;
  paypal_approve_url?: string | null;
  paypal_capture_id?: string | null;
  decided_by?: string | null;
  failure?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Mandate {
  version: number;
  mandate_id: string;
  agent_id: string;
  currency: string;
  per_payment_limit: string | number;
  total_limit: string | number;
  approval_threshold: string | number;
  allowed_payees: string[];
  issued_at: string;
  expires_at: string;
}

export interface StoredMandate {
  mandate: Mandate;
  committed: string | number;
  created_at: string;
  revoked_at?: string | null;
}

export interface MandateIssued {
  mandate: Mandate;
  token: string;
}

export interface AuditEntry {
  seq: number;
  ts: string;
  event: string;
  actor: string;
  subject_id: string;
  data?: Record<string, unknown> | string;
  prev_hash?: string;
  hash: string;
}

export interface ChainStatus {
  ok: boolean;
  entries: number;
  first_bad_seq: number | null;
  reasons?: PolicyReason[];
  head_seq: number | null;
  head_hash: string | null;
  checkpoint_ok: boolean | null;
  checkpoint_seq: number | null;
  checkpoint_error: string | null;
}

export interface AdminSessionState {
  authenticated: boolean;
  checking: boolean;
}
