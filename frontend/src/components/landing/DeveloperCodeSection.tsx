"use client";

import React, { useState } from "react";
import { CopyIcon, CheckIcon } from "@/components/ui/Icons";

const CODE_EXAMPLES = {
  python: {
    title: "Python Agent Client",
    language: "python",
    code: `import httpx

# 1. Autonomous agent submits payment using signed mandate token
headers = {
    "Authorization": f"Bearer {AGENT_MANDATE_TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "request_id": "req_8f102a9c",
    "payee": "shop-a",
    "amount": "25.00",
    "currency": "USD",
    "description": "Compute cluster reserve hours"
}

# 2. Call Seatbelt Policy Gateway (fail-closed security layer)
response = httpx.post("https://api.seatbelt.network/v1/paypal/payments", json=payload, headers=headers)
result = response.json()

print(f"Status: {result['status']}")      # 'captured' or 'pending_approval'
print(f"Verdict: {result['verdict']}")    # 'allow' or 'require_approval'
print(f"Audit Ref: {result['payment_id']}")`,
  },
  curl: {
    title: "cURL HTTP Request",
    language: "bash",
    code: `# Submit payment with mandated token authentication
curl -X POST https://api.seatbelt.network/v1/paypal/payments \\
  -H "Authorization: Bearer sb_mandate_9a7d8e6f120c43" \\
  -H "Content-Type: application/json" \\
  -d '{
    "request_id": "req_99812401",
    "payee": "shop-a",
    "amount": "45.00",
    "currency": "USD",
    "description": "API Gateway usage tier"
  }'`,
  },
  mandate: {
    title: "Mandate Policy Schema",
    language: "json",
    code: `{
  "agent_id": "agent-orchestrator-prod",
  "currency": "USD",
  "per_payment_limit": "100.00",
  "total_limit": "500.00",
  "approval_threshold": "50.00",
  "allowed_payees": [
    "cloud-infrastructure",
    "shop-a",
    "api-supplier-eu"
  ],
  "ttl_minutes": 1440
}`,
  },
  webhook: {
    title: "PayPal Webhook Receiver",
    language: "python",
    code: `@app.post("/v1/paypal/webhook")
async def paypal_webhook(request: Request):
    """Authenticated via PayPal postback verification & idempotency guard."""
    raw_body = await request.body()
    headers = request.headers

    # Verifies HMAC / Certificate URL before processing
    result = service.handle_paypal_webhook(headers, event, raw_body)
    return JSONResponse(status_code=200, content=result)`,
  },
};

type ExampleKey = keyof typeof CODE_EXAMPLES;

export function DeveloperCodeSection() {
  const [activeTab, setActiveTab] = useState<ExampleKey>("python");
  const [copied, setCopied] = useState(false);

  const activeExample = CODE_EXAMPLES[activeTab];

  const handleCopy = () => {
    navigator.clipboard.writeText(activeExample.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-[#11181D] border border-[#1E2B27] rounded-xl overflow-hidden shadow-2xl">
      {/* Code Header with Tabs */}
      <div className="px-4 py-2.5 border-b border-[#1E2B27] bg-[#0C1216] flex items-center justify-between">
        <div className="flex items-center gap-1">
          {(Object.keys(CODE_EXAMPLES) as ExampleKey[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`text-xs px-3 py-1.5 rounded-md font-mono transition-colors ${
                activeTab === tab
                  ? "bg-[#151F24] text-[#16E6A0] border border-[#1E2B27] font-medium"
                  : "text-[#91A09D] hover:text-[#F1F5F4] hover:bg-[#11181D]"
              }`}
            >
              {CODE_EXAMPLES[tab].title}
            </button>
          ))}
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-[#91A09D] hover:text-[#F1F5F4] px-2.5 py-1 rounded bg-[#151F24] border border-[#1E2B27] transition-colors"
          title="Copy code"
        >
          {copied ? (
            <>
              <CheckIcon className="w-3.5 h-3.5 text-[#16E6A0]" />
              <span className="text-[#16E6A0]">Copied</span>
            </>
          ) : (
            <>
              <CopyIcon className="w-3.5 h-3.5" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Code Block */}
      <div className="p-4 sm:p-6 overflow-x-auto bg-[#090D10]/80">
        <pre className="font-mono text-xs sm:text-[13px] leading-relaxed text-[#F1F5F4]">
          <code>{activeExample.code}</code>
        </pre>
      </div>

      {/* Code Footer */}
      <div className="px-4 py-2 border-t border-[#1E2B27] bg-[#0C1216] flex items-center justify-between text-[11px] font-mono text-[#5F716D]">
        <span>Seatbelt Core API v1</span>
        <span>JSON-RPC & REST Compatible</span>
      </div>
    </div>
  );
}
