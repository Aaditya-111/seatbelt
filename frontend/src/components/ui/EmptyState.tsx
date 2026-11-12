import React from "react";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center p-12 border border-dashed border-[#1E2B27] rounded-xl bg-[#090D10]/50 ${className}`}
    >
      {icon && (
        <div className="w-10 h-10 rounded-lg bg-[#11181D] border border-[#1E2B27] flex items-center justify-center text-[#91A09D] mb-4">
          {icon}
        </div>
      )}
      <h4 className="text-sm font-medium text-[#F1F5F4]">{title}</h4>
      <p className="text-xs text-[#91A09D] max-w-sm mt-1.5 leading-relaxed">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
