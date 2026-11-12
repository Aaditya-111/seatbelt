"use client";

import React, { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { loginAdmin } from "@/lib/api-client";

interface SignInModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function SignInModal({ isOpen, onClose, onSuccess }: SignInModalProps) {
  const [adminKey, setAdminKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!adminKey.trim()) return;

    setLoading(true);
    setError("");

    try {
      const ok = await loginAdmin(adminKey.trim());
      if (ok) {
        setAdminKey("");
        onSuccess();
        onClose();
      } else {
        setError("Invalid admin API key.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Admin Session Sign-In"
      description="Enter the SEATBELT_ADMIN_API_KEY to authorize administrative actions. A signed 30-minute session cookie will be established."
      maxWidth="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4 pt-2">
        {error && (
          <div className="p-3 rounded-md bg-[#F43F5E]/10 border border-[#F43F5E]/20 text-[#FB7185] text-xs">
            {error}
          </div>
        )}

        <div>
          <label className="block text-xs font-mono uppercase text-[#91A09D] mb-1.5">
            Admin API Key
          </label>
          <input
            type="password"
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
            placeholder="Paste your admin API key..."
            className="w-full px-3 py-2 rounded-md bg-[#090D10] border border-[#1E2B27] text-xs text-[#F1F5F4] font-mono focus:outline-none focus:border-[#16E6A0]"
            required
            autoFocus
          />
          <p className="text-[11px] text-[#5F716D] mt-1.5">
            Your key is verified server-side and never stored in browser storage.
          </p>
        </div>

        <div className="flex items-center justify-end gap-3 pt-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" loading={loading}>
            Establish Session
          </Button>
        </div>
      </form>
    </Modal>
  );
}
