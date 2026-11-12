import {
  AuditEntry,
  ChainStatus,
  MandateIssued,
  PaymentRecord,
  PaymentStatus,
  StoredMandate,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail || `API request failed with status ${status}`);
    this.name = "ApiError";
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  isAdmin = false,
  agentToken?: string
): Promise<T> {
  const headers = new Headers(options.headers);

  if (isAdmin) {
    headers.set("x-seatbelt-admin-request", "true");
  }

  if (agentToken) {
    headers.set("Authorization", `Bearer ${agentToken}`);
  }

  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const url = endpoint.startsWith("/api/") ? endpoint : `/api/seatbelt${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });

  let data: Record<string, unknown> | null = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const detail = (data?.detail as string) || (data?.error as string) || `Request failed (${response.status})`;
    throw new ApiError(response.status, detail);
  }

  return (data as unknown) as T;
}

// --------------------------------------------------------------------------- Admin Session APIs
export async function checkAdminSession(): Promise<boolean> {
  try {
    const res = await request<{ authenticated: boolean }>("/api/admin/session");
    return Boolean(res?.authenticated);
  } catch {
    return false;
  }
}

export async function loginAdmin(key: string): Promise<boolean> {
  const res = await request<{ authenticated: boolean }>("/api/admin/session", {
    method: "POST",
    body: JSON.stringify({ key }),
  });
  return Boolean(res?.authenticated);
}

export async function logoutAdmin(): Promise<void> {
  await request<{ authenticated: boolean }>("/api/admin/session", {
    method: "DELETE",
  });
}

// --------------------------------------------------------------------------- Public & Meta
export async function getHealth(): Promise<{ status: string; version: string }> {
  return request<{ status: string; version: string }>("/health");
}

// --------------------------------------------------------------------------- Admin Operations
export async function listPayments(params?: {
  mandate_id?: string;
  status?: PaymentStatus;
  limit?: number;
  offset?: number;
}): Promise<PaymentRecord[]> {
  const query = new URLSearchParams();
  if (params?.mandate_id) query.set("mandate_id", params.mandate_id);
  if (params?.status) query.set("status", params.status);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));

  const qs = query.toString();
  return request<PaymentRecord[]>(`/v1/payments${qs ? `?${qs}` : ""}`, {}, true);
}

export async function getPayment(paymentId: string): Promise<PaymentRecord> {
  return request<PaymentRecord>(`/v1/payments/${encodeURIComponent(paymentId)}`, {}, true);
}

export async function approvePayment(
  paymentId: string,
  approver = "admin"
): Promise<PaymentRecord> {
  return request<PaymentRecord>(
    `/v1/payments/${encodeURIComponent(paymentId)}/approve`,
    {
      method: "POST",
      body: JSON.stringify({ approver }),
    },
    true
  );
}

export async function rejectPayment(
  paymentId: string,
  reason: string,
  approver = "admin"
): Promise<PaymentRecord> {
  return request<PaymentRecord>(
    `/v1/payments/${encodeURIComponent(paymentId)}/reject`,
    {
      method: "POST",
      body: JSON.stringify({ approver, reason }),
    },
    true
  );
}

export async function retryPayment(paymentId: string): Promise<PaymentRecord> {
  return request<PaymentRecord>(
    `/v1/payments/${encodeURIComponent(paymentId)}/retry`,
    {
      method: "POST",
    },
    true
  );
}

// --------------------------------------------------------------------------- Mandates
export async function issueMandate(body: {
  agent_id: string;
  currency: string;
  per_payment_limit: number | string;
  total_limit: number | string;
  approval_threshold: number | string;
  allowed_payees: string[];
  ttl_minutes: number;
}): Promise<MandateIssued> {
  return request<MandateIssued>(
    "/v1/mandates",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    true
  );
}

export async function getMandate(mandateId: string): Promise<StoredMandate> {
  return request<StoredMandate>(
    `/v1/mandates/${encodeURIComponent(mandateId)}`,
    {},
    true
  );
}

export async function revokeMandate(
  mandateId: string
): Promise<{ payments_cancelled: number }> {
  return request<{ payments_cancelled: number }>(
    `/v1/mandates/${encodeURIComponent(mandateId)}/revoke`,
    {
      method: "POST",
    },
    true
  );
}

// --------------------------------------------------------------------------- Audit & Integrity
export async function listAudit(limit = 100, offset = 0): Promise<AuditEntry[]> {
  return request<AuditEntry[]>(
    `/v1/audit?limit=${limit}&offset=${offset}`,
    {},
    true
  );
}

export async function verifyAudit(): Promise<ChainStatus> {
  return request<ChainStatus>("/v1/audit/verify", {}, true);
}

export async function createAuditCheckpoint(): Promise<ChainStatus> {
  return request<ChainStatus>(
    "/v1/audit/checkpoint",
    {
      method: "POST",
    },
    true
  );
}

// --------------------------------------------------------------------------- AI Payment Interpretation

export interface PaymentIntent {
  status: "ready" | "needs_clarification";
  payee: string | null;
  amount: string | null;
  currency: string | null;
  description: string | null;
  quantity: number | null;
  missing_fields: Array<"payee" | "amount" | "currency">;
  clarification_question: string | null;
}

export async function interpretPaymentIntent(
  token: string,
  purchase_text: string
): Promise<PaymentIntent> {
  return request<PaymentIntent>(
    "/v1/agent/interpret",
    {
      method: "POST",
      body: JSON.stringify({ purchase_text }),
    },
    false,
    token
  );
}

// --------------------------------------------------------------------------- Agent Payments (Playground)
export async function submitAgentPayment(
  token: string,
  body: {
    request_id: string;
    payee: string;
    amount: string | number;
    currency: string;
    description: string;
  },
  channel: "executor" | "paypal" = "paypal"
): Promise<PaymentRecord> {
  const path = channel === "paypal" ? "/v1/paypal/payments" : "/v1/payments";
  return request<PaymentRecord>(
    path,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    false,
    token
  );
}

// --------------------------------------------------------------------------- Formatting Helpers
export function formatMoney(amount: number | string, currency = "USD"): string {
  const n = typeof amount === "number" ? amount : parseFloat(String(amount));
  if (isNaN(n)) return `${amount} ${currency}`;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

export function formatDate(isoString?: string): string {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(d);
  } catch {
    return isoString;
  }
}

export function shortId(id?: string, length = 8): string {
  if (!id) return "—";
  if (id.length <= length) return id;
  return `${id.slice(0, length)}…`;
}

export function shortHash(hash?: string): string {
  if (!hash) return "—";
  if (hash.length <= 16) return hash;
  return `${hash.slice(0, 8)}…${hash.slice(-8)}`;
}
