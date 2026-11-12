"use client";

import React, { useState } from "react";
import { PaymentRecord } from "@/lib/types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { interpretPaymentIntent, submitAgentPayment, formatMoney, formatDate, PaymentIntent } from "@/lib/api-client";
import { ExternalLinkIcon } from "@/components/ui/Icons";

interface PlaygroundViewProps {
  onPaymentSuccess: () => void;
  onOpenIssueMandate: () => void;
}

export function PlaygroundView({
  onPaymentSuccess,
  onOpenIssueMandate,
}: PlaygroundViewProps) {
  const [token, setToken] = useState("");
  const [purchaseText, setPurchaseText] = useState(
    "Buy 1 item from shop-a for 25 USD"
  );
  const [channel, setChannel] = useState<"paypal" | "executor">("paypal");

  const [interpreting, setInterpreting] = useState(false);
  const [intent, setIntent] = useState<PaymentIntent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PaymentRecord | null>(null);

  const handleInterpret = async () => {
    if (!token.trim()) {
      setError("Please provide an agent mandate token. You can issue one from the Agents page.");
      return;
    }

    if (!purchaseText.trim()) {
      setError("Describe what the agent should purchase.");
      return;
    }

    setInterpreting(true);
    setError("");
    setIntent(null);
    setResult(null);

    try {
      const proposal = await interpretPaymentIntent(
        token.trim(),
        purchaseText.trim()
      );
      setIntent(proposal);
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI interpretation failed.");
    } finally {
      setInterpreting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!token.trim()) {
      setError("Please provide a valid agent mandate bearer token.");
      return;
    }

    if (
      !intent ||
      intent.status !== "ready" ||
      !intent.payee ||
      !intent.amount ||
      !intent.currency
    ) {
      setError("Interpret and review a complete payment proposal before confirming.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const payment = await submitAgentPayment(
        token.trim(),
        {
          request_id: `req_${crypto.randomUUID().slice(0, 12)}`,
          payee: intent.payee,
          amount: intent.amount,
          currency: intent.currency,
          description: intent.description?.trim() || purchaseText.trim(),
        },
        channel
      );
      setResult(payment);
      onPaymentSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment submission failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-[#F1F5F4]">Agent Mandate Playground</h2>
        <p className="text-xs text-[#91A09D]">
          Simulate an autonomous agent submitting payment requests using a signed mandate token. Observe real backend policy evaluation in real-time.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: Input Form (6 cols) */}
        <div className="lg:col-span-6 space-y-4">
          <Card>
            <CardHeader
              title="Submit Agent Payment Request"
              subtitle="Uses the agent authentication path: Authorization: Bearer <mandate_token>"
            />

            <form onSubmit={handleSubmit} className="space-y-4 pt-1">
              {error && (
                <div className="p-3 rounded-md bg-[#F43F5E]/10 border border-[#F43F5E]/20 text-[#FB7185] text-xs">
                  {error}
                </div>
              )}

              {/* Mandate Bearer Token */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-[11px] font-mono uppercase text-[#91A09D]">
                    Agent Mandate Token (Required)
                  </label>
                  <button
                    type="button"
                    onClick={onOpenIssueMandate}
                    className="text-[11px] font-mono text-[#16E6A0] hover:underline"
                  >
                    Issue new token ?
                  </button>
                </div>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => {
                    setToken(e.target.value);
                    setIntent(null);
                    setResult(null);
                    setError("");
                  }}
                  placeholder="Paste signed mandate token..."
                  className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
                  required
                />
              </div>

              {/* Payment Channel */}
              <div>
                <label className="block text-[11px] font-mono uppercase text-[#91A09D] mb-1.5">
                  Execution Channel
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setChannel("paypal")}
                    className={`py-2 px-3 rounded-md text-xs font-mono border text-center transition-colors ${
                      channel === "paypal"
                        ? "bg-[#151F24] border-[#16E6A0] text-[#16E6A0] font-semibold"
                        : "bg-[#090D10] border-[#1E2B27] text-[#91A09D] hover:bg-[#11181D]"
                    }`}
                  >
                    PayPal Orders v2
                  </button>
                  <button
                    type="button"
                    onClick={() => setChannel("executor")}
                    className={`py-2 px-3 rounded-md text-xs font-mono border text-center transition-colors ${
                      channel === "executor"
                        ? "bg-[#151F24] border-[#16E6A0] text-[#16E6A0] font-semibold"
                        : "bg-[#090D10] border-[#1E2B27] text-[#91A09D] hover:bg-[#11181D]"
                    }`}
                  >
                    Internal Executor Rail
                  </button>
                </div>
              </div>

              {/* Natural-language purchase request */}
              <div>
                <label className="block text-[11px] font-mono uppercase text-[#91A09D] mb-1.5">
                  Describe the purchase
                </label>
                <textarea
                  value={purchaseText}
                  onChange={(e) => {
                    setPurchaseText(e.target.value);
                    setIntent(null);
                    setResult(null);
                    setError("");
                  }}
                  placeholder="Example: Buy 2 notebooks from shop-a for 18.50 USD total"
                  rows={4}
                  maxLength={2000}
                  className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] focus:outline-none focus:border-[#16E6A0] resize-y"
                  required
                />
                <p className="mt-1 text-[10px] text-[#5F716D]">
                  Local AI interprets the request. It cannot authorize or execute a payment.
                </p>
              </div>

              <Button
                type="button"
                size="md"
                className="w-full"
                loading={interpreting}
                disabled={interpreting || loading || !token.trim() || !purchaseText.trim()}
                onClick={handleInterpret}
              >
                Interpret Purchase Request
              </Button>

              {/* AI proposal / clarification */}
              {intent && (
                <div className="p-4 rounded-lg bg-[#090D10] border border-[#1E2B27] space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-mono uppercase text-[#91A09D]">
                      Local AI Interpretation
                    </span>
                    <Badge
                      status={intent.status === "ready" ? "approved" : "pending"}
                      size="sm"
                    />
                  </div>

                  {intent.status === "needs_clarification" ? (
                    <div className="space-y-2">
                      <p className="text-sm text-[#F1F5F4]">
                        {intent.clarification_question || "More information is required."}
                      </p>
                      <p className="text-[11px] text-[#91A09D]">
                        Edit your purchase request above and interpret it again. No payment has been submitted.
                      </p>
                      {intent.missing_fields.length > 0 && (
                        <p className="text-[10px] font-mono text-[#FBBF24]">
                          Missing or restricted: {intent.missing_fields.join(", ")}
                        </p>
                      )}
                    </div>
                  ) : (
                    <>
                      <div className="grid grid-cols-2 gap-3 text-xs">
                        <div>
                          <span className="block text-[10px] uppercase font-mono text-[#5F716D]">Payee</span>
                          <span className="font-mono text-[#22D3EE]">{intent.payee}</span>
                        </div>
                        <div>
                          <span className="block text-[10px] uppercase font-mono text-[#5F716D]">Amount</span>
                          <span className="font-mono text-[#16E6A0]">
                            {intent.amount} {intent.currency}
                          </span>
                        </div>
                        {intent.quantity !== null && (
                          <div>
                            <span className="block text-[10px] uppercase font-mono text-[#5F716D]">Quantity</span>
                            <span className="font-mono text-[#F1F5F4]">{intent.quantity}</span>
                          </div>
                        )}
                        <div className="col-span-2">
                          <span className="block text-[10px] uppercase font-mono text-[#5F716D]">Description</span>
                          <span className="text-[#F1F5F4]">
                            {intent.description || purchaseText}
                          </span>
                        </div>
                      </div>
                      <div className="p-3 rounded-md border border-[#FBBF24]/20 bg-[#FBBF24]/5 text-[11px] text-[#FBBF24]">
                        Review carefully. This is only a proposal, not a payment authorization.
                        Confirm below to submit it to the existing policy engine.
                      </div>
                    </>
                  )}
                </div>
              )}

              <Button
                type="submit"
                size="md"
                className="w-full"
                loading={loading}
                disabled={
                  loading ||
                  interpreting ||
                  !intent ||
                  intent.status !== "ready" ||
                  !intent.payee ||
                  !intent.amount ||
                  !intent.currency
                }
              >
                Confirm & Submit Payment
              </Button>
            </form>
          </Card>
        </div>

        {/* Right: Live Policy Engine Result (6 cols) */}
        <div className="lg:col-span-6 space-y-4">
          <Card variant="elevated">
            <CardHeader
              title="Policy Engine Response"
              subtitle="Real backend verdict and payment record output"
            />

            {!result ? (
              <div className="p-8 text-center border border-dashed border-[#1E2B27] rounded-lg text-xs text-[#91A09D]">
                Submit a payment from the left panel to observe live policy checks, budget reservation, and provider settlement.
              </div>
            ) : (
              <div className="space-y-4">
                {/* Verdict and Status */}
                <div className="p-4 rounded-lg bg-[#090D10] border border-[#1E2B27] flex items-center justify-between">
                  <div>
                    <span className="text-[10px] font-mono uppercase text-[#5F716D] block">
                      Policy Verdict
                    </span>
                    <span className="text-base font-semibold font-mono text-[#F1F5F4]">
                      {result.verdict.toUpperCase()}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge status={result.status} size="md" />
                  </div>
                </div>

                {/* Amount and Payee */}
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
                    <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Settled Amount</span>
                    <span className="font-mono font-semibold text-[#16E6A0]">
                      {formatMoney(result.amount, result.currency)}
                    </span>
                  </div>
                  <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27]">
                    <span className="text-[10px] font-mono text-[#5F716D] uppercase block">Payee</span>
                    <span className="font-mono text-[#22D3EE]">{result.payee}</span>
                  </div>
                </div>

                {/* Policy Reasons */}
                <div className="p-3.5 rounded-lg bg-[#090D10] border border-[#1E2B27] space-y-2 text-xs">
                  <span className="text-[10px] font-mono text-[#91A09D] uppercase block">
                    Evaluated Rules & Reasons
                  </span>
                  {result.reasons && result.reasons.length > 0 ? (
                    <div className="space-y-1">
                      {result.reasons.map((r, i) => (
                        <div key={i} className="flex items-start gap-1.5 text-xs">
                          <span className="text-[#16E6A0] font-mono">•</span>
                          <span className="text-[#91A09D]">{r.message}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[11px] text-[#5F716D]">No violations detected.</div>
                  )}
                </div>

                {/* PayPal Specific URL */}
                {result.paypal_approve_url && (
                  <div className="p-3.5 rounded-lg bg-[#151F24] border border-[#22D3EE]/30 space-y-2 text-xs">
                    <span className="text-[#22D3EE] font-semibold block">
                      Awaiting Payer Authorization
                    </span>
                    <p className="text-[11px] text-[#91A09D]">
                      This PayPal payment was approved by policy. Complete the checkout approval in PayPal sandbox to finalize capture:
                    </p>
                    <a
                      href={result.paypal_approve_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs text-[#16E6A0] hover:underline font-mono"
                    >
                      <span>Authorize Order at PayPal Sandbox</span>
                      <ExternalLinkIcon className="w-3.5 h-3.5" />
                    </a>
                  </div>
                )}

                {/* IDs */}
                <div className="p-3 rounded-md bg-[#090D10] border border-[#1E2B27] text-[11px] font-mono text-[#5F716D] space-y-1">
                  <div>Payment ID: <span className="text-[#F1F5F4]">{result.payment_id}</span></div>
                  <div>Agent ID: <span className="text-[#F1F5F4]">{result.agent_id}</span></div>
                  <div>Recorded: {formatDate(result.created_at)}</div>
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
