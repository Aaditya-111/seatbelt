import React from "react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: React.ReactNode;
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  icon,
  className = "",
  ...props
}: ButtonProps) {
  const baseStyles =
    "inline-flex items-center justify-center font-medium transition-all duration-150 focus:outline-none focus:ring-1 focus:ring-[#16E6A0]/50 disabled:opacity-50 disabled:cursor-not-allowed select-none rounded-md";

  const sizeStyles = {
    sm: "text-xs px-2.5 py-1.5 gap-1.5",
    md: "text-xs px-3.5 py-2 gap-2",
    lg: "text-sm px-4 py-2.5 gap-2.5",
  };

  const variantStyles = {
    primary:
      "bg-[#16E6A0] text-[#090D10] font-semibold hover:bg-[#1FF0AB] active:bg-[#12C78A] shadow-[0_1px_2px_rgba(0,0,0,0.5)]",
    secondary:
      "bg-[#151F24] text-[#F1F5F4] hover:bg-[#1A262D] border border-[#1E2B27] hover:border-[#283F37]",
    outline:
      "bg-transparent text-[#F1F5F4] border border-[#1E2B27] hover:border-[#283F37] hover:bg-[#11181D]",
    ghost:
      "bg-transparent text-[#91A09D] hover:text-[#F1F5F4] hover:bg-[#11181D]",
    danger:
      "bg-[#F43F5E]/10 text-[#FB7185] border border-[#F43F5E]/20 hover:bg-[#F43F5E]/20 active:bg-[#F43F5E]/30",
  };

  return (
    <button
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <svg
          className="animate-spin h-3.5 w-3.5"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      ) : (
        icon
      )}
      {children}
    </button>
  );
}
