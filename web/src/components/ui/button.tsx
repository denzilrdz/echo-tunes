import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/cn";

// shadcn/ui-style button (Base UI flavour: plain <button>, our tokens).
export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full font-semibold select-none transition-[background-color,color,opacity,scale] duration-120 ease-out active:scale-[0.97] disabled:opacity-45 disabled:active:scale-100 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-fg hover:brightness-110",
        secondary: "bg-surface-2 text-fg hover:bg-surface-3",
        outline: "border border-border bg-transparent text-fg hover:bg-surface-2",
        ghost: "bg-transparent text-fg-muted hover:bg-surface-2 hover:text-fg",
        danger: "bg-danger text-white hover:brightness-110",
        glass:
          "bg-white/14 text-white backdrop-blur-md hover:bg-white/22 dark:bg-white/10 dark:hover:bg-white/16",
      },
      size: {
        sm: "h-9 px-3.5 text-[13px] [&_svg]:size-4",
        md: "h-11 px-5 text-sm [&_svg]:size-[18px]",
        lg: "h-12 px-6 text-[15px] [&_svg]:size-5",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return (
    <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}

const iconSizes = {
  sm: "size-9 [&_svg]:size-[18px]",
  md: "size-11 [&_svg]:size-5",
  lg: "size-14 [&_svg]:size-6",
  xl: "size-16 [&_svg]:size-7",
} as const;

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  size?: keyof typeof iconSizes;
  variant?: "ghost" | "solid" | "accent" | "glass";
}

/** A round icon-only button with an accessible name (and a tooltip-like title). */
export function IconButton({
  label,
  size = "md",
  variant = "ghost",
  className,
  type = "button",
  title,
  ...props
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={title ?? label}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full transition-[background-color,color,opacity,scale] duration-120 ease-out active:scale-[0.94] disabled:opacity-40 disabled:active:scale-100",
        iconSizes[size],
        variant === "ghost" && "text-fg-muted hover:bg-surface-2 hover:text-fg",
        variant === "solid" && "bg-fg text-bg hover:scale-[1.04]",
        variant === "accent" &&
          "bg-accent text-accent-fg shadow-lg shadow-black/20 hover:scale-[1.04]",
        variant === "glass" && "bg-black/25 text-white backdrop-blur-md hover:bg-black/35",
        className,
      )}
      {...props}
    />
  );
}
