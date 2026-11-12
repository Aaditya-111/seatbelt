"use client";

import React, { useState } from "react";
import Link from "next/link";
import { ShieldIcon, ArrowRightIcon } from "@/components/ui/Icons";
import { Button } from "@/components/ui/Button";

interface LandingNavProps {
  onOpenSignIn?: () => void;
}

export function LandingNav({ onOpenSignIn }: LandingNavProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-[#1E2B27] bg-[#090D10]/85 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-[#11181D] border border-[#1E2B27] group-hover:border-[#16E6A0]/40 flex items-center justify-center text-[#16E6A0] transition-colors">
            <ShieldIcon className="w-4 h-4" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="font-semibold text-sm tracking-tight text-[#F1F5F4]">
              Seatbelt
            </span>
            <span className="text-[10px] uppercase font-mono tracking-wider px-1.5 py-0.5 rounded bg-[#151F24] text-[#91A09D] border border-[#1E2B27]">
              Gov
            </span>
          </div>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-6 text-xs text-[#91A09D]">
          <a href="#platform" className="hover:text-[#F1F5F4] transition-colors">
            Platform
          </a>
          <a href="#how-it-works" className="hover:text-[#F1F5F4] transition-colors">
            How it works
          </a>
          <a href="#capabilities" className="hover:text-[#F1F5F4] transition-colors">
            Capabilities
          </a>
          <a href="#architecture" className="hover:text-[#F1F5F4] transition-colors">
            Architecture
          </a>
          <a href="#security" className="hover:text-[#F1F5F4] transition-colors">
            Security
          </a>
          <a href="#developers" className="hover:text-[#F1F5F4] transition-colors">
            Developers
          </a>
        </nav>

        {/* Action CTAs */}
        <div className="hidden sm:flex items-center gap-3">
          <button
            onClick={onOpenSignIn}
            className="text-xs font-medium text-[#91A09D] hover:text-[#F1F5F4] px-3 py-1.5 rounded-md hover:bg-[#11181D] transition-colors"
          >
            Sign in
          </button>
          <Link href="/dashboard">
            <Button size="sm" icon={<ArrowRightIcon className="w-3.5 h-3.5 ml-0.5 order-last" />}>
              Open Console
            </Button>
          </Link>
        </div>

        {/* Mobile menu button */}
        <div className="sm:hidden flex items-center">
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="text-[#91A09D] p-1.5 rounded-md hover:bg-[#11181D]"
            aria-label="Toggle menu"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              {mobileMenuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="sm:hidden border-b border-[#1E2B27] bg-[#090D10] px-4 pt-2 pb-4 space-y-2 text-xs text-[#91A09D]">
          <a
            href="#platform"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 hover:text-[#F1F5F4]"
          >
            Platform
          </a>
          <a
            href="#how-it-works"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 hover:text-[#F1F5F4]"
          >
            How it works
          </a>
          <a
            href="#capabilities"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 hover:text-[#F1F5F4]"
          >
            Capabilities
          </a>
          <a
            href="#architecture"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 hover:text-[#F1F5F4]"
          >
            Architecture
          </a>
          <a
            href="#security"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 hover:text-[#F1F5F4]"
          >
            Security
          </a>
          <a
            href="#developers"
            onClick={() => setMobileMenuOpen(false)}
            className="block py-2 hover:text-[#F1F5F4]"
          >
            Developers
          </a>
          <div className="pt-2 border-t border-[#1E2B27] flex items-center justify-between">
            <button
              onClick={() => {
                setMobileMenuOpen(false);
                onOpenSignIn?.();
              }}
              className="text-xs text-[#91A09D]"
            >
              Sign in
            </button>
            <Link href="/dashboard" onClick={() => setMobileMenuOpen(false)}>
              <Button size="sm">Open Console</Button>
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
