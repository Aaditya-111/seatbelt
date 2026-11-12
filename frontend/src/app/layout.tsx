import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Seatbelt — Payment Governance for AI Agents",
  description:
    "Let AI agents transact within clear boundaries. Seatbelt provides deterministic payment authorization, human approvals, and verifiable audit history.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
