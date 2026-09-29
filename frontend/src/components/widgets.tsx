"use client";

import { ReactNode } from "react";
import { LucideIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { GRADE_SHORT, gradeColor, gradeInk } from "@/lib/api";

/** Small headline number. No plot, so no hover layer — the value is the content. */
export function StatTile({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: LucideIcon;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass = {
    default: "text-foreground",
    good: "text-emerald-600",
    warn: "text-amber-600",
    bad: "text-rose-600",
  }[tone];
  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-4">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            {label}
          </p>
          {Icon && <Icon className="size-4 shrink-0 text-muted-foreground/70" />}
        </div>
        <p className={`mt-1.5 font-mono text-2xl font-semibold tabular-nums ${toneClass}`}>
          {value}
        </p>
        {hint && <p className="mt-0.5 text-[11.5px] text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

export function Panel({
  title,
  action,
  className = "",
  children,
}: {
  title: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
          {title}
        </CardTitle>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

/**
 * Grade distribution. Severity is ordinal, so the bars are ordered 0..4 and
 * every bar is directly labelled — identity never rests on colour alone.
 */
export function GradeDistribution({ counts }: { counts: number[] }) {
  const total = counts.reduce((a, b) => a + b, 0) || 1;
  const max = Math.max(...counts, 1);
  return (
    <div className="space-y-2.5">
      {counts.map((count, grade) => (
        <div key={grade} className="flex items-center gap-3" title={`${GRADE_SHORT[grade]}: ${count}`}>
          <span className="w-24 shrink-0 text-xs" style={{ color: gradeInk(grade) }}>
            <span className="mr-1.5 font-mono opacity-60">{grade}</span>
            {GRADE_SHORT[grade]}
          </span>
          <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
            <span
              className="block h-full rounded-full transition-[width] duration-700"
              style={{ width: `${(count / max) * 100}%`, background: gradeColor(grade) }}
            />
          </span>
          <span className="w-16 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">
            {count}
            <span className="ml-1 opacity-60">{Math.round((count / total) * 100)}%</span>
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * 14-day activity. Two series in the same unit (screenings), so one axis;
 * legend present because there are two, and bars carry a hover tooltip.
 */
export function ActivityTrend({
  daily,
}: {
  daily: Array<{ date: string; label: string; total: number; referable: number }>;
}) {
  const max = Math.max(...daily.map((d) => d.total), 1);
  return (
    <div>
      <div className="mb-3 flex items-center gap-4 text-[11.5px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px] bg-indigo-500" /> Screenings
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px] bg-rose-600" /> Referable
        </span>
      </div>
      <div className="flex h-28 items-end gap-1">
        {daily.map((day) => (
          <div
            key={day.date}
            // h-full matters: the bars below size with percentage heights,
            // which only resolve against a parent of definite height.
            className="group relative flex h-full flex-1 flex-col items-center justify-end gap-[2px]"
            title={`${day.label}: ${day.total} screened, ${day.referable} referable`}
          >
            {day.referable > 0 && (
              <span
                className="w-full rounded-t-[4px] bg-rose-600"
                style={{ height: `${(day.referable / max) * 100}%` }}
              />
            )}
            <span
              className="w-full rounded-t-[4px] bg-indigo-500 group-hover:bg-indigo-400"
              style={{
                height: `${((day.total - day.referable) / max) * 100}%`,
                minHeight: day.total > 0 ? 3 : 0,
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[10.5px] text-muted-foreground">
        <span>{daily[0]?.label}</span>
        <span>{daily[daily.length - 1]?.label}</span>
      </div>
    </div>
  );
}

/** Radial gauge for a single headline proportion. */
export function Gauge({
  value,
  grade,
  size = 128,
  caption = "confidence",
}: {
  value: number;
  grade?: number;
  size?: number;
  caption?: string;
}) {
  const color = grade === undefined ? "#4f46e5" : gradeColor(grade);
  const ink = grade === undefined ? "#4f46e5" : gradeInk(grade);
  const r = size / 2 - 9;
  const circ = 2 * Math.PI * r;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth="8" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - Math.max(0, Math.min(1, value)))}
          style={{ transition: "stroke-dashoffset 1s cubic-bezier(.2,.8,.2,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono text-2xl font-semibold tabular-nums" style={{ color: ink }}>
          {Math.round(value * 100)}%
        </span>
        <span className="text-[10px] tracking-wide text-muted-foreground uppercase">
          {caption}
        </span>
      </div>
    </div>
  );
}

/** Per-class probabilities for one screening, each row directly labelled. */
export function ProbabilityBars({
  values,
  predicted,
}: {
  values: number[];
  predicted: number;
}) {
  return (
    <div className="space-y-2.5">
      {values.map((p, grade) => {
        const isPredicted = grade === predicted;
        return (
          <div key={grade} className="flex items-center gap-3">
            <span
              className={`w-28 shrink-0 text-xs ${isPredicted ? "font-semibold" : ""}`}
              style={{ color: isPredicted ? gradeInk(grade) : undefined }}
            >
              <span className="mr-1.5 font-mono opacity-60">{grade}</span>
              {GRADE_SHORT[grade]}
            </span>
            <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full transition-[width] duration-700"
                style={{
                  width: `${Math.max(0, Math.min(1, p)) * 100}%`,
                  background: gradeColor(grade),
                }}
              />
            </span>
            <span className="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">
              {(p * 100).toFixed(0)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Label/value rows for configuration and status panels. */
export function MetaList({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="space-y-2.5">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-3">
          <dt className="text-[12.5px] text-muted-foreground">{label}</dt>
          <dd className="text-right text-[13px] font-medium">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function StatusDot({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`size-2 rounded-full ${ok ? "bg-emerald-500" : "bg-slate-300"}`}
        aria-hidden
      />
      <span className={ok ? "" : "text-muted-foreground"}>{children}</span>
    </span>
  );
}

/** Capacity-style meter used for referral rate and quality pass rate. */
export function RateMeter({
  value,
  label,
  tone = "indigo",
}: {
  value: number;
  label: string;
  tone?: "indigo" | "rose" | "emerald";
}) {
  const pct = Math.round(value * 100);
  const colour = { indigo: "bg-indigo-500", rose: "bg-rose-600", emerald: "bg-emerald-500" }[tone];
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-[12.5px] text-muted-foreground">{label}</span>
        <span className="font-mono text-sm font-semibold tabular-nums">{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-[width] duration-700 ${colour}`}
          style={{ width: `${pct}%` }}
          role="meter"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={label}
        />
      </div>
    </div>
  );
}
