"use client";

import React, { useEffect } from "react";
import { XIcon } from "./Icons";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  maxWidth?: "sm" | "md" | "lg" | "xl";
}

export function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  maxWidth = "md",
}: ModalProps) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    if (isOpen) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    }

    return () => {
      document.body.style.overflow = "unset";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const widthStyles = {
    sm: "max-w-sm",
    md: "max-w-md",
    lg: "max-w-lg",
    xl: "max-w-xl",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/75 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Box */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className={`relative w-full ${widthStyles[maxWidth]} bg-[#11181D] border border-[#1E2B27] rounded-xl shadow-2xl p-6 text-[#F1F5F4] z-10 animate-in fade-in zoom-in-95 duration-150`}
      >
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h2 id="modal-title" className="text-base font-semibold text-[#F1F5F4]">
              {title}
            </h2>
            {description && (
              <p className="text-xs text-[#91A09D] mt-1">{description}</p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-[#91A09D] hover:text-[#F1F5F4] p-1 rounded-md hover:bg-[#151F24] transition-colors"
          >
            <XIcon className="w-4 h-4" />
          </button>
        </div>

        <div>{children}</div>
      </div>
    </div>
  );
}
