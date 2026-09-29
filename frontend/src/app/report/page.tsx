"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Download, Printer } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Chat } from "@/components/Chat";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Gauge, MetaList, ProbabilityBars } from "@/components/widgets";
import {
  api,
  formatDate,
  GRADE_SHORT,
  gradeInk,
  ScreeningDetail,
  Status,
} from "@/lib/api";

export default function ReportPage() {
  return (
    <Suspense fallback={<AppShell title="Report"><p className="text-sm text-muted-foreground">Loading…</p></AppShell>}>
      <ReportRoute />
    </Suspense>
  );
}

function ReportRoute() {
  const idParam = useSearchParams().get("id");
  const id = Number(idParam);
  const hasId = Boolean(idParam) && Number.isInteger(id) && id > 0;

  const [detail, setDetail] = useState<ScreeningDetail | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!hasId) return;
    api.screening(id).then(setDetail).catch(() => setNotFound(true));
    api.status().then(setStatus).catch(() => {});
  }, [id, hasId]);

  const error = !hasId ? "No screening selected." : notFound ? "Screening not found." : null;

  return (
    <AppShell
      title={detail ? `Report #${String(detail.id).padStart(6, "0")}` : "Report"}
      subtitle={detail ? detail.patient_name : undefined}
      actions={
        detail && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => window.print()}>
              <Printer className="size-4" /> Print
            </Button>
            <Button asChild size="sm">
              <a href={`/api/screenings/${detail.id}/report.html`} download>
                <Download className="size-4" /> Export
              </a>
            </Button>
          </div>
        )
      }
    >
      {error ? (
        <Card>
          <CardContent className="py-16 text-center">
            <p className="text-[13px] text-muted-foreground">{error}</p>
            <Button asChild variant="link" size="sm">
              <Link href="/history">Back to records</Link>
            </Button>
          </CardContent>
        </Card>
      ) : !detail ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <Report detail={detail} status={status} />
      )}
    </AppShell>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-[12px] font-semibold tracking-[0.12em] text-muted-foreground uppercase">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Report({ detail, status }: { detail: ScreeningDetail; status: Status | null }) {
  const sex = { M: "Male", F: "Female", O: "Other" }[detail.sex ?? ""] ?? "—";
  const threshold = status?.referral_threshold ?? 0.5;

  // Ordinal severity expressed as a single number: the probability-weighted
  // grade. Useful for ranking a camp's patients even when two share a grade.
  const expectedGrade = detail.probabilities.reduce((sum, p, g) => sum + p * g, 0);
  const secondGuess = detail.probabilities
    .map((p, g) => ({ p, g }))
    .sort((a, b) => b.p - a.p)[1];
  const margin = detail.confidence - (secondGuess?.p ?? 0);
  const trend = detail.history.length
    ? detail.grade - detail.history[0].grade
    : null;

  return (
    <div className="space-y-5">
      {/* headline */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-6 pt-6">
          <Gauge value={detail.confidence} grade={detail.grade} size={140} />
          <div className="min-w-56 flex-1">
            <p className="font-mono text-[11px] font-semibold tracking-wide uppercase"
               style={{ color: gradeInk(detail.grade) }}>
              Grade {detail.grade} of 4
            </p>
            <h2 className="mt-1 text-3xl font-semibold tracking-tight"
                style={{ color: gradeInk(detail.grade) }}>
              {detail.label}
            </h2>
            <p className="mt-2 max-w-prose text-[13.5px] text-muted-foreground">{detail.advice}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant={detail.referable ? "destructive" : "secondary"}>
                {detail.referable ? "Referral required" : "No referral"}
              </Badge>
              <Badge variant="outline">
                P(referable) {Math.round(detail.referral_probability * 100)}%
              </Badge>
              <Badge variant="outline">threshold {Math.round(threshold * 100)}%</Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="space-y-5">
          <Section title="Fundus image">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/api/screenings/${detail.id}/image`}
              alt="Fundus photograph"
              className="w-full rounded-lg border"
            />
            <p className="mt-2.5 break-all font-mono text-[10.5px] text-muted-foreground">
              SHA-256 {detail.image_sha256 ?? "—"}
            </p>
          </Section>

          <Section title="Patient">
            <MetaList
              rows={[
                ["Name", detail.patient_name],
                ["Mobile", detail.phone ?? "—"],
                ["Age", detail.age != null ? `${detail.age} years` : "—"],
                ["Sex", sex],
                ["Screened by", detail.operator_username ?? "—"],
                ["Date & time", formatDate(detail.created_at)],
                ["Report ID", <span key="r" className="font-mono text-xs">
                  DRS-{String(detail.id).padStart(6, "0")}
                </span>],
              ]}
            />
          </Section>
        </div>

        <div className="space-y-5">
          <Section title="Classification detail">
            <ProbabilityBars values={detail.probabilities} predicted={detail.grade} />
            <Separator className="my-4" />
            <MetaList
              rows={[
                ["Predicted grade", `${detail.grade} — ${detail.label}`],
                ["Top-class confidence", `${(detail.confidence * 100).toFixed(1)}%`],
                [
                  "Runner-up",
                  secondGuess
                    ? `${GRADE_SHORT[secondGuess.g]} (${(secondGuess.p * 100).toFixed(1)}%)`
                    : "—",
                ],
                ["Decision margin", `${(margin * 100).toFixed(1)} points`],
                ["Expected grade", expectedGrade.toFixed(2)],
                ["P(grade ≥ moderate)", `${(detail.referral_probability * 100).toFixed(1)}%`],
                [
                  "Certainty",
                  margin > 0.4 ? "High" : margin > 0.15 ? "Moderate" : "Low — consider a re-read",
                ],
              ]}
            />
          </Section>

          <Section title="Interpretation">
            <div className="space-y-3 text-[13px] leading-relaxed">
              <p>
                The classifier assigns <strong>{detail.label}</strong> with{" "}
                {(detail.confidence * 100).toFixed(1)}% confidence. Referral is decided on the
                cumulative probability of moderate-or-worse disease
                ({(detail.referral_probability * 100).toFixed(1)}%), not on the top class alone,
                so a spread of probability across severe grades still triggers a referral.
              </p>
              <p className="text-muted-foreground">
                {detail.referable
                  ? "This patient meets the referral threshold and should be seen by an ophthalmologist within the interval stated above."
                  : "This patient falls below the referral threshold. Routine re-screening applies unless symptoms change."}
              </p>
              {margin <= 0.15 && (
                <p className="text-amber-600">
                  The decision margin is narrow — the top two grades are close. A second read or
                  a repeat photograph is advisable.
                </p>
              )}
            </div>
          </Section>

          <Section title="Acquisition &amp; provenance">
            <MetaList
              rows={[
                ["Model architecture", status ? "ResNet-152 (PyTorch)" : "—"],
                ["Model version", <span key="v" className="font-mono text-xs">{detail.model_version}</span>],
                ["Test-time augmentation", "Horizontal-flip average"],
                ["Referral threshold", `P(grade ≥ moderate) ≥ ${Math.round(threshold * 100)}%`],
                ["SMS notification", detail.sms_status ?? "not sent"],
                ["Image integrity", detail.image_sha256 ? "SHA-256 recorded" : "—"],
              ]}
            />
          </Section>
        </div>
      </div>

      {detail.history.length > 0 && (
        <Section title="Prior screenings for this patient">
          <div className="space-y-2">
            {trend !== null && (
              <p className="mb-3 text-[13px]">
                {trend > 0
                  ? `Severity has increased by ${trend} grade${trend > 1 ? "s" : ""} since the previous screening.`
                  : trend < 0
                    ? `Severity has decreased by ${Math.abs(trend)} grade${Math.abs(trend) > 1 ? "s" : ""} since the previous screening.`
                    : "Grade is unchanged since the previous screening."}
              </p>
            )}
            {detail.history.map((h) => (
              <Link
                key={h.id}
                href={`/report?id=${h.id}`}
                className="flex items-center justify-between gap-3 rounded-lg border px-3.5 py-2.5 transition-colors hover:bg-muted/60"
              >
                <span className="font-mono text-[12px] text-muted-foreground">
                  {formatDate(h.created_at)}
                </span>
                <span className="flex items-center gap-3">
                  <span className="text-[12.5px] font-medium" style={{ color: gradeInk(h.grade) }}>
                    {h.label}
                  </span>
                  <span className="font-mono text-[11.5px] text-muted-foreground">
                    {Math.round(h.confidence * 100)}%
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </Section>
      )}

      {status?.chat_available && (
        <Section title="Explain this result">
          <Chat screeningId={detail.id} />
        </Section>
      )}

      <Alert>
        <AlertTitle>AI-assisted screening aid — not a medical diagnosis</AlertTitle>
        <AlertDescription>
          This report is produced automatically from a single fundus photograph by a
          convolutional classifier. It must be confirmed by a qualified ophthalmologist before
          any clinical decision. See docs/MODEL_CARD.md for validated performance and known
          limitations.
        </AlertDescription>
      </Alert>
    </div>
  );
}
