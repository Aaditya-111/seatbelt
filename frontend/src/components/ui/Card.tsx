import React from "react";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "elevated" | "interactive";
}

export function Card({
  children,
  variant = "default",
  className = "",
  ...props
}: CardProps) {
  const variantStyles = {
    default: "bg-[#11181D] border border-[#1E2B27]",
    elevated: "bg-[#151F24] border border-[#233530] shadow-lg shadow-black/40",
    interactive:
      "bg-[#11181D] border border-[#1E2B27] hover:border-[#283F37] hover:bg-[#131D23] transition-colors cursor-pointer",
  };

  return (
    <div className={`rounded-lg p-5 ${variantStyles[variant]} ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
  className = "",
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex items-start justify-between gap-4 mb-4 ${className}`}>
      <div>
        <h3 className="text-sm font-semibold text-[#F1F5F4] tracking-tight">{title}</h3>
        {subtitle && <p className="text-xs text-[#91A09D] mt-1">{subtitle}</p>}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  );
}
