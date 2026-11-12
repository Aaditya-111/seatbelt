"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { loginAdmin } from "@/lib/api-client";
import { DeveloperCodeSection } from "@/components/landing/DeveloperCodeSection";
import { InteractivePipeline } from "@/components/landing/InteractivePipeline";

const wallTiles = Array.from({ length: 104 }, (_, i) => i);
const floorTiles = Array.from({ length: 48 }, (_, i) => i);

function Shield() {
  return (
    <div className="cyber-shield-wrap" aria-label="Seatbelt security shield">
      <div className="cyber-shield-aura" />
      <div className="cyber-shield">
        <svg viewBox="0 0 320 370" fill="none" role="img" aria-label="Shield with checkmark">
          <defs>
            <linearGradient id="shieldEdge" x1="50" y1="20" x2="270" y2="350" gradientUnits="userSpaceOnUse">
              <stop stopColor="#B5FFE3" />
              <stop offset=".25" stopColor="#00EFA6" />
              <stop offset=".65" stopColor="#087D59" />
              <stop offset="1" stopColor="#53FFC5" />
            </linearGradient>
            <linearGradient id="shieldFace" x1="70" y1="35" x2="245" y2="330" gradientUnits="userSpaceOnUse">
              <stop stopColor="#173D35" />
              <stop offset=".48" stopColor="#071D19" />
              <stop offset="1" stopColor="#020B09" />
            </linearGradient>
            <filter id="shieldGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="7" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <path
            d="M160 8 296 62v105c0 91-54 158-136 194C78 325 24 258 24 167V62L160 8Z"
            fill="#03110E"
            stroke="#00A979"
            strokeWidth="13"
          />
          <path
            d="M160 22 281 70v96c0 82-47 143-121 178-74-35-121-96-121-178V70l121-48Z"
            fill="url(#shieldFace)"
            stroke="url(#shieldEdge)"
            strokeWidth="8"
          />
          <path
            d="M160 37 267 80v85c0 71-39 124-107 158-68-34-107-87-107-158V80l107-43Z"
            stroke="#4AFFC1"
            strokeOpacity=".3"
            strokeWidth="2"
          />
          <path
            d="m93 185 46 46 93-103"
            stroke="#00EFA6"
            strokeWidth="21"
            strokeLinecap="round"
            strokeLinejoin="round"
            filter="url(#shieldGlow)"
          />
          <path
            d="m93 185 46 46 93-103"
            stroke="#D8FFF1"
            strokeWidth="8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <div className="cyber-platform">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="cyber-brand">
      <span className="cyber-brand-icon">
        <svg viewBox="0 0 40 44" fill="none" aria-hidden="true">
          <path
            d="M20 2 37 9v12c0 10-7 17-17 21C10 38 3 31 3 21V9l17-7Z"
            stroke="currentColor"
            strokeWidth="3"
          />
          <path
            d="m11 22 6 6 12-14"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span>SEATBELT</span>
    </Link>
  );
}

export default function Home() {
  const router = useRouter();
  const [signInOpen, setSignInOpen] = useState(false);
  const [adminKey, setAdminKey] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState("");

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!adminKey.trim()) return;
    setLoginLoading(true);
    setLoginError("");

    try {
      const ok = await loginAdmin(adminKey.trim());
      if (ok) {
        setSignInOpen(false);
        router.push("/dashboard");
      } else {
        setLoginError("Invalid admin API key.");
      }
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setLoginLoading(false);
    }
  };

  return (
    <main className="cyber-landing">
      {/* 3D Scene Background */}
      <div className="cyber-scene" aria-hidden="true">
        <div className="cyber-wall">
          {wallTiles.map((tile) => (
            <div className="cyber-hex" key={tile}>
              <span />
            </div>
          ))}
        </div>
        <div className="cyber-floor">
          {floorTiles.map((tile) => (
            <div className="cyber-floor-hex" key={tile}>
              <span />
            </div>
          ))}
        </div>
        <div className="cyber-light cyber-light-one" />
        <div className="cyber-light cyber-light-two" />
        <div className="cyber-vignette" />
      </div>

      {/* Navigation Header */}
      <header className="cyber-header">
        <Brand />
        <nav className="cyber-nav" aria-label="Main navigation">
          <a href="#platform">Product</a>
          <a href="#security">Security</a>
          <a href="#developers">Developers</a>
          <a href="#about">About</a>
          <button
            onClick={() => setSignInOpen(true)}
            className="text-xs text-[#aebfb6] hover:text-[#00efa6] transition-colors cursor-pointer"
            style={{ background: "transparent", border: 0, padding: 0 }}
          >
            Sign in
          </button>
        </nav>
        <Link href="/dashboard" className="cyber-console">
          Open Console <span>→</span>
        </Link>
      </header>

      {/* Hero Section */}
      <section className="cyber-hero" id="platform">
        <div className="cyber-copy">
          <div className="cyber-eyebrow">
            <span />
            PAYMENT GOVERNANCE FOR AI AGENTS
          </div>

          <h1>
            Let AI agents
            <br />
            transact.
            <br />
            <span>Not run wild.</span>
          </h1>

          <p className="cyber-description">
            Deterministic controls for autonomous commerce.
          </p>

          <ul className="cyber-benefits">
            <li>
              <span>✓</span>Policy-first decision engine
            </li>
            <li>
              <span>✓</span>Mandate-based authorization
            </li>
            <li>
              <span>✓</span>Tamper-evident audit trail
            </li>
          </ul>

          <div className="cyber-actions">
            <Link href="/dashboard" className="cyber-primary">
              Open Control Plane <span>→</span>
            </Link>
            <a href="#how-it-works" className="cyber-secondary">
              Learn More
            </a>
          </div>
        </div>

        <div className="cyber-art">
          <Shield />
        </div>
      </section>

      {/* Feature Bar */}
      <section className="cyber-feature-bar" id="security">
        <div className="cyber-feature">
          <span className="cyber-feature-icon">⬡</span>
          <div>
            <strong>Policy-first</strong>
            <span>Authorization</span>
          </div>
        </div>
        <div className="cyber-feature">
          <span className="cyber-feature-icon">♙</span>
          <div>
            <strong>Tamper-evident</strong>
            <span>Audit Trail</span>
          </div>
        </div>
        <div className="cyber-feature">
          <span className="cyber-paypal-icon">P</span>
          <div>
            <strong>Secure PayPal</strong>
            <span>Execution</span>
          </div>
        </div>
      </section>

      {/* Below Section: How it Works & Core Steps */}
      <section className="cyber-below" id="how-it-works">
        <div className="cyber-section-label">HOW IT WORKS</div>
        <h2>
          Keep humans firmly in control of <span>every transaction.</span>
        </h2>
        <p>
          Seatbelt enforces cryptographic spending mandates, evaluates deterministic limits,
          escalates high-value payments to human approvers, and records immutable audit records.
        </p>

        <div className="cyber-steps">
          <article>
            <span>01 / MANDATE BOUNDARY</span>
            <h3>Identity &amp; Spending Caps</h3>
            <p>
              Agents receive signed Ed25519 mandate tokens declaring per-payment limits,
              lifetime budget caps, and strict payee allowlists.
            </p>
          </article>

          <article>
            <span>02 / DETERMINISTIC ENGINE</span>
            <h3>Pre-flight Policy Evaluation</h3>
            <p>
              Transactions undergo immediate boundary validation. Payments under threshold clear
              instantly; transactions above threshold hold for admin review.
            </p>
          </article>

          <article>
            <span>03 / TAMPER-EVIDENT TRAIL</span>
            <h3>HMAC Hash Chaining</h3>
            <p>
              Every decision, event, and state change is cryptographically linked with HMAC-SHA256
              digests and out-of-band rollback checkpoints.
            </p>
          </article>
        </div>

        {/* Live Simulator Section */}
        <div style={{ marginTop: "70px" }}>
          <div className="cyber-section-label">INTERACTIVE POLICY SIMULATOR</div>
          <h2 style={{ fontSize: "28px", margin: "14px 0 24px" }}>
            Experience <span>Seatbelt</span> in action
          </h2>
          <InteractivePipeline />
        </div>

        {/* Developer Integration Code Section */}
        <div style={{ marginTop: "70px" }} id="developers">
          <div className="cyber-section-label">DEVELOPER INTEGRATION</div>
          <h2 style={{ fontSize: "28px", margin: "14px 0 24px" }}>
            API-first infrastructure for <span>autonomous agents</span>
          </h2>
          <DeveloperCodeSection />
        </div>
      </section>

      {/* Footer */}
      <footer className="cyber-footer" id="about">
        <Brand />
        <span>SEATBELT · AUTONOMOUS PAYMENT GOVERNANCE INFRASTRUCTURE</span>
        <Link href="/dashboard" style={{ color: "var(--emerald)", textDecoration: "none" }}>
          Open Console →
        </Link>
      </footer>

      {/* Admin Sign-In Modal */}
      {signInOpen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0,0,0,0.85)",
            backdropFilter: "blur(6px)",
            padding: "20px",
          }}
        >
          <div
            style={{
              width: "100%",
              maxWidth: "420px",
              background: "#071711",
              border: "1px solid rgba(0, 239, 166, 0.3)",
              borderRadius: "14px",
              padding: "28px",
              boxShadow: "0 20px 60px rgba(0, 239, 166, 0.15)",
              color: "#f1f8f5",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "18px" }}>
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "#00efa6" }}>
                Admin Authentication
              </h3>
              <button
                onClick={() => setSignInOpen(false)}
                style={{
                  background: "transparent",
                  border: 0,
                  color: "#9eafa6",
                  fontSize: "18px",
                  cursor: "pointer",
                }}
              >
                ✕
              </button>
            </div>

            <p style={{ margin: "0 0 18px", fontSize: "12px", color: "#a5b5ad", lineHeight: 1.6 }}>
              Enter your <code style={{ color: "#00efa6" }}>SEATBELT_ADMIN_API_KEY</code> to open an authenticated 30-minute session.
            </p>

            {loginError && (
              <div
                style={{
                  padding: "10px 14px",
                  borderRadius: "6px",
                  background: "rgba(244, 63, 94, 0.15)",
                  border: "1px solid rgba(244, 63, 94, 0.3)",
                  color: "#fb7185",
                  fontSize: "12px",
                  marginBottom: "14px",
                }}
              >
                {loginError}
              </div>
            )}

            <form onSubmit={handleSignIn}>
              <div style={{ marginBottom: "18px" }}>
                <label
                  style={{
                    display: "block",
                    fontSize: "10px",
                    fontWeight: 700,
                    letterSpacing: "1px",
                    color: "#8fa399",
                    marginBottom: "8px",
                  }}
                >
                  ADMIN API KEY
                </label>
                <input
                  type="password"
                  value={adminKey}
                  onChange={(e) => setAdminKey(e.target.value)}
                  placeholder="Paste admin API key..."
                  style={{
                    width: "100%",
                    padding: "10px 12px",
                    background: "#030c08",
                    border: "1px solid rgba(0, 239, 166, 0.25)",
                    borderRadius: "6px",
                    color: "#f1f8f5",
                    fontSize: "12px",
                    fontFamily: "monospace",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                  required
                  autoFocus
                />
              </div>

              <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  onClick={() => setSignInOpen(false)}
                  style={{
                    padding: "8px 14px",
                    borderRadius: "6px",
                    background: "transparent",
                    border: "1px solid rgba(255,255,255,0.15)",
                    color: "#a5b5ad",
                    fontSize: "12px",
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loginLoading}
                  style={{
                    padding: "8px 18px",
                    borderRadius: "6px",
                    background: "linear-gradient(110deg, #00efa6, #39ffc0)",
                    border: 0,
                    color: "#00180f",
                    fontWeight: 700,
                    fontSize: "12px",
                    cursor: "pointer",
                    boxShadow: "0 0 16px rgba(0, 239, 166, 0.3)",
                  }}
                >
                  {loginLoading ? "Verifying..." : "Sign In & Open"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
