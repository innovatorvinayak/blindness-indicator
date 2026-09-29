"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BadgeCheck,
  Bot,
  CalendarClock,
  Cpu,
  Eye,
  Gauge as GaugeIcon,
  MessageSquare,
  ScanEye,
  ShieldAlert,
  Signal,
  Users,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ActivityTrend,
  Gauge,
  GradeDistribution,
  MetaList,
  Panel,
  RateMeter,
  StatTile,
  StatusDot,
} from "@/components/widgets";
import { api, DashboardStats, formatDate, gradeInk, ScreeningRow } from "@/lib/api";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.stats().then(setStats).catch(() => setError("Could not load dashboard data."));
  }, []);

  return (
    <AppShell
      title="Overview"
      subtitle={stats ? stats.config.clinic_name : "Screening activity and system health"}
      actions={
        <Button asChild size="sm">
          <Link href="/screen">
            <ScanEye className="size-4" /> New screening
          </Link>
        </Button>
      }
    >
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!stats ? <DashboardSkeleton /> : <Dashboard stats={stats} />}
    </AppShell>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-64 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

function GradePill({ row }: { row: ScreeningRow }) {
  return (
    <span className="text-[12.5px] font-medium" style={{ color: gradeInk(row.grade) }}>
      {row.label}
    </span>
  );
}

function Dashboard({ stats }: { stats: DashboardStats }) {
  const pct = (n: number) => `${Math.round(n * 100)}%`;
  const referralTone = stats.referral_rate > 0.4 ? "bad" : "default";

  return (
    <div className="space-y-5">
      {/* ── 1-8: headline counters ─────────────────────────────── */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Total screenings" value={stats.total} icon={Eye}
                  hint={`${stats.unique_patients} unique patients`} />
        <StatTile label="Referrals flagged" value={stats.referable} icon={ShieldAlert}
                  tone={referralTone} hint={`${pct(stats.referral_rate)} of all screenings`} />
        <StatTile label="Screened today" value={stats.screened_today} icon={CalendarClock}
                  hint={`${stats.screened_week} in the last 7 days`} />
        <StatTile label="Mean confidence" value={pct(stats.mean_confidence)} icon={GaugeIcon}
                  hint={`${stats.low_confidence_count} below 60%`} />
        <StatTile label="Unique patients" value={stats.unique_patients} icon={Users} />
        <StatTile label="Low-confidence results" value={stats.low_confidence_count}
                  icon={AlertTriangle}
                  tone={stats.low_confidence_count > 0 ? "warn" : "good"}
                  hint="Worth a second read" />
        <StatTile label="Rejected uploads" value={stats.rejected_uploads} icon={BadgeCheck}
                  hint="Not a fundus photograph" />
        <StatTile label="SMS delivered" value={stats.sms_sent} icon={Signal}
                  tone={stats.sms_failed > 0 ? "warn" : "default"}
                  hint={`${stats.sms_failed} failed · ${stats.sms_not_sent} not sent`} />
      </section>

      {/* ── 9-12: distribution, trend, rates ───────────────────── */}
      <section className="grid gap-4 lg:grid-cols-3">
        <Panel title="Severity distribution">
          <GradeDistribution counts={stats.grade_counts} />
        </Panel>

        <Panel title="Last 14 days" className="lg:col-span-2">
          <ActivityTrend daily={stats.daily} />
        </Panel>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Panel title="Referral rate">
          <div className="flex items-center gap-5">
            <Gauge value={stats.referral_rate} caption="referable" />
            <div className="min-w-0 flex-1 space-y-3">
              <RateMeter value={stats.referral_rate} label="Flagged for referral" tone="rose" />
              <RateMeter
                value={stats.total ? 1 - stats.low_confidence_count / stats.total : 1}
                label="High-confidence results"
                tone="emerald"
              />
              <p className="text-[11.5px] text-muted-foreground">
                Threshold: P(grade ≥ moderate) ≥ {pct(stats.config.referral_threshold)}
              </p>
            </div>
          </div>
        </Panel>

        {/* ── 13-14: model + assistant health ──────────────────── */}
        <Panel title="Model">
          <MetaList
            rows={[
              ["Status", <StatusDot key="s" ok={stats.model.ready}>
                {stats.model.ready ? "Loaded" : "Not loaded"}
              </StatusDot>],
              ["Architecture", stats.model.architecture ?? "—"],
              ["Version", <span key="v" className="font-mono text-xs">{stats.model.version ?? "—"}</span>],
              ["Device", <span key="d" className="font-mono text-xs">{stats.model.device ?? "—"}</span>],
              ["Test-time aug.", stats.model.tta ? "On (flip average)" : "Off"],
              ["Channel order", <span key="c" className="font-mono text-xs">{stats.model.channel_order ?? "—"}</span>],
            ]}
          />
        </Panel>

        <Panel title="Assistants">
          <MetaList
            rows={[
              ["Chat", <StatusDot key="c" ok={stats.assistant.chat_available}>
                {stats.assistant.chat_available ? "Ready" : "Offline"}
              </StatusDot>],
              ["Chat model", <span key="cm" className="font-mono text-xs">{stats.assistant.chat_model}</span>],
              ["Vision", <StatusDot key="v" ok={stats.assistant.vision_available}>
                {stats.assistant.vision_available ? "Ready" : "Not installed"}
              </StatusDot>],
              ["Vision model", <span key="vm" className="font-mono text-xs">{stats.assistant.vision_model}</span>],
              ["SMS provider", <Badge key="p" variant="secondary">{stats.config.sms_provider}</Badge>],
              ["Last screening", stats.last_screening_at ? formatDate(stats.last_screening_at) : "—"],
            ]}
          />
        </Panel>
      </section>

      {/* ── 15-16: priority queue + recent activity ───────────── */}
      <section className="grid gap-4 lg:grid-cols-5">
        <Panel title="Priority queue" className="lg:col-span-2">
          {stats.severe_queue.length === 0 ? (
            <p className="py-8 text-center text-[13px] text-muted-foreground">
              No severe or proliferative cases. 🎉
            </p>
          ) : (
            <ul className="space-y-2">
              {stats.severe_queue.map((row) => (
                <li key={row.id}>
                  <Link
                    href={`/report?id=${row.id}`}
                    className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5 transition-colors hover:bg-muted/60"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium">
                        {row.patient_name}
                      </span>
                      <span className="block text-[11px] text-muted-foreground">
                        {formatDate(row.created_at)}
                      </span>
                    </span>
                    <GradePill row={row} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="Recent screenings"
          className="lg:col-span-3"
          action={
            <Button asChild variant="ghost" size="sm">
              <Link href="/history">View all</Link>
            </Button>
          }
        >
          {stats.recent.length === 0 ? (
            <p className="py-8 text-center text-[13px] text-muted-foreground">
              Nothing screened yet — start from “New screening”.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Patient</TableHead>
                  <TableHead>Grade</TableHead>
                  <TableHead className="text-right">Conf.</TableHead>
                  <TableHead className="text-right">When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {stats.recent.map((row) => (
                  <TableRow key={row.id} className="cursor-pointer">
                    <TableCell className="font-medium">
                      <Link href={`/report?id=${row.id}`} className="block">
                        {row.patient_name}
                      </Link>
                    </TableCell>
                    <TableCell><GradePill row={row} /></TableCell>
                    <TableCell className="text-right font-mono text-xs tabular-nums">
                      {Math.round(row.confidence * 100)}%
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {formatDate(row.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Panel>
      </section>

      {/* ── 17-20: operations ─────────────────────────────────── */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Panel title="Throughput">
          <MetaList
            rows={[
              ["Today", stats.screened_today],
              ["Last 7 days", stats.screened_week],
              ["Busiest day", stats.busiest_day ?? "—"],
              ["All time", stats.total],
            ]}
          />
        </Panel>

        <Panel title="Notifications">
          <MetaList
            rows={[
              ["Delivered", stats.sms_sent],
              ["Failed", stats.sms_failed],
              ["Not sent", stats.sms_not_sent],
              ["Enabled", stats.config.sms_enabled ? "Yes" : "No"],
            ]}
          />
        </Panel>

        <Panel title="Image intake">
          <MetaList
            rows={[
              ["Accepted", stats.total],
              ["Rejected (not a retina)", stats.rejected_uploads],
              [
                "Acceptance rate",
                pct(
                  stats.total + stats.rejected_uploads
                    ? stats.total / (stats.total + stats.rejected_uploads)
                    : 1,
                ),
              ],
              ["Low confidence", stats.low_confidence_count],
            ]}
          />
        </Panel>

        <Panel title="Quick actions">
          <div className="space-y-2">
            <Button asChild className="w-full justify-start" variant="outline" size="sm">
              <Link href="/screen"><ScanEye className="size-4" /> Screen a patient</Link>
            </Button>
            <Button asChild className="w-full justify-start" variant="outline" size="sm">
              <Link href="/history"><Users className="size-4" /> Browse records</Link>
            </Button>
            <Button asChild className="w-full justify-start" variant="outline" size="sm">
              <a href="/api/screenings/export.csv" download><Cpu className="size-4" /> Export CSV</a>
            </Button>
            <Button asChild className="w-full justify-start" variant="outline" size="sm">
              <Link href="/settings"><MessageSquare className="size-4" /> Configure assistant</Link>
            </Button>
          </div>
        </Panel>
      </section>

      <p className="flex items-center gap-2 pt-1 text-[11.5px] text-muted-foreground">
        <Bot className="size-3.5" />
        AI-assisted screening aid — not a diagnostic device. Every result is confirmed by a
        qualified ophthalmologist.
      </p>
    </div>
  );
}
