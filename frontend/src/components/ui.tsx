"use client";

import { ReactNode, ButtonHTMLAttributes, InputHTMLAttributes, SelectHTMLAttributes } from "react";
import { gradeColor } from "@/lib/api";

export function Panel({
  children,
  className = "",
  hover = false,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div className={`glass ${hover ? "glass-hover" : ""} rounded-2xl ${className}`}>{children}</div>
  );
}

export function PanelTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-5 flex items-center justify-between gap-3">
      <h2 className="text-[13px] font-semibold uppercase tracking-[0.2em] text-ink-dim">
        {children}
      </h2>
      {right}
    </div>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
  loading?: boolean;
};

export function Button({
  variant = "ghost",
  loading = false,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonProps) {
  const base =
    "relative inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-45";
  const styles = {
    primary:
      "text-void bg-[linear-gradient(120deg,#22d3ee,#818cf8)] shadow-[0_0_28px_-6px_#22d3ee] hover:shadow-[0_0_38px_-4px_#22d3ee] hover:brightness-110 disabled:shadow-none",
    ghost:
      "text-ink border border-line bg-surface/60 hover:border-cyan/45 hover:bg-surface-2/70 hover:shadow-[0_0_22px_-8px_#22d3ee]",
    danger:
      "text-bad border border-bad/35 bg-bad/5 hover:bg-bad/15 hover:shadow-[0_0_22px_-8px_#ff4d6d]",
  }[variant];

  return (
    <button className={`${base} ${styles} ${className}`} disabled={disabled || loading} {...rest}>
      {loading && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-[10.5px] font-semibold uppercase tracking-[0.16em] text-ink-faint">
        {label}
      </span>
      <input
        {...rest}
        className="w-full rounded-xl border border-line bg-abyss/80 px-3.5 py-2.5 text-sm text-ink outline-none transition-all placeholder:text-ink-faint focus:border-cyan focus:shadow-[0_0_0_3px_#22d3ee22]"
      />
      {hint && <span className="mt-1 block text-[11px] text-ink-faint">{hint}</span>}
    </label>
  );
}

export function SelectField({
  label,
  children,
  className = "",
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: ReactNode }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-[10.5px] font-semibold uppercase tracking-[0.16em] text-ink-faint">
        {label}
      </span>
      <select
        {...rest}
        className="w-full rounded-xl border border-line bg-abyss/80 px-3.5 py-2.5 text-sm text-ink outline-none transition-all focus:border-cyan focus:shadow-[0_0_0_3px_#22d3ee22]"
      >
        {children}
      </select>
    </label>
  );
}

export function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-3 text-sm text-ink-dim transition-colors hover:text-ink"
    >
      <span
        className={`relative h-5 w-9 shrink-0 rounded-full border transition-all ${
          checked
            ? "border-cyan/60 bg-cyan/25 shadow-[0_0_16px_-4px_#22d3ee]"
            : "border-line bg-abyss"
        }`}
      >
        <span
          className={`absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full transition-all ${
            checked ? "left-[18px] bg-cyan" : "left-[3px] bg-ink-faint"
          }`}
        />
      </span>
      {label}
    </button>
  );
}

export function Banner({
  kind = "info",
  children,
}: {
  kind?: "info" | "warn" | "bad" | "ok";
  children: ReactNode;
}) {
  const styles = {
    info: "border-cyan/30 bg-cyan/8 text-cyan",
    ok: "border-ok/30 bg-ok/8 text-ok",
    warn: "border-warn/30 bg-warn/8 text-warn",
    bad: "border-bad/35 bg-bad/10 text-bad",
  }[kind];
  return (
    <div className={`mb-4 rounded-xl border px-4 py-2.5 text-[13px] ${styles}`}>{children}</div>
  );
}

export function GradeChip({ grade, label }: { grade: number; label: string }) {
  const color = gradeColor(grade);
  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold"
      style={{
        color,
        borderColor: `${color}55`,
        background: `${color}14`,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
      {label}
    </span>
  );
}

/** Radial confidence gauge — the headline number on a result. */
export function ConfidenceRing({
  value,
  grade,
  size = 132,
}: {
  value: number;
  grade: number;
  size?: number;
}) {
  const color = gradeColor(grade);
  const r = size / 2 - 9;
  const circ = 2 * Math.PI * r;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e2a42" strokeWidth="7" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - Math.max(0, Math.min(1, value)))}
          style={{
            transition: "stroke-dashoffset 1s cubic-bezier(.2,.8,.2,1)",
            filter: `drop-shadow(0 0 7px ${color}aa)`,
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono text-3xl font-semibold" style={{ color }}>
          {Math.round(value * 100)}%
        </span>
        <span className="text-[10px] uppercase tracking-[0.16em] text-ink-faint">confidence</span>
      </div>
    </div>
  );
}

export function ProbabilityBars({ values, predicted }: { values: number[]; predicted: number }) {
  return (
    <div className="space-y-2.5">
      {values.map((p, g) => {
        const color = gradeColor(g);
        const isPredicted = g === predicted;
        return (
          <div key={g} className="flex items-center gap-3">
            <span
              className={`w-28 shrink-0 text-xs ${isPredicted ? "font-semibold text-ink" : "text-ink-dim"}`}
            >
              <span className="mr-1.5 font-mono text-ink-faint">{g}</span>
              {["No DR", "Mild", "Moderate", "Severe", "Proliferative"][g]}
            </span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-abyss">
              <span
                className="block h-full rounded-full"
                style={{
                  width: `${Math.max(0, Math.min(1, p)) * 100}%`,
                  background: color,
                  boxShadow: `0 0 10px ${color}99`,
                  transition: "width .8s cubic-bezier(.2,.8,.2,1)",
                }}
              />
            </span>
            <span className="w-11 shrink-0 text-right font-mono text-xs text-ink-dim">
              {(p * 100).toFixed(0)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
