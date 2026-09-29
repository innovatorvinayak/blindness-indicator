"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, ImageOff, TriangleAlert, Upload } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Chat } from "@/components/Chat";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Gauge, ProbabilityBars } from "@/components/widgets";
import {
  api,
  ApiError,
  FundusRejection,
  gradeInk,
  QualityCheck,
  ScreenResult,
  Status,
} from "@/lib/api";

export default function ScreenPage() {
  return (
    <AppShell title="New screening" subtitle="Grade a fundus photograph">
      <Screening />
    </AppShell>
  );
}

function Screening() {
  const [status, setStatus] = useState<Status | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [quality, setQuality] = useState<QualityCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [dragging, setDragging] = useState(false);

  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [sendSms, setSendSms] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejection, setRejection] = useState<FundusRejection | null>(null);
  const [result, setResult] = useState<ScreenResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => {});
  }, []);
  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  async function pick(next: File | null) {
    if (!next) return;
    setFile(next);
    setResult(null);
    setError(null);
    setRejection(null);
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old);
      return URL.createObjectURL(next);
    });

    setChecking(true);
    setQuality(null);
    try {
      setQuality(await api.qualityCheck(next));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not read that image.");
    } finally {
      setChecking(false);
    }
  }

  async function analyse(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setRejection(null);
    try {
      const form = new FormData();
      form.append("image", file);
      form.append("full_name", fullName);
      form.append("phone", phone);
      form.append("age", age);
      form.append("sex", sex);
      form.append("send_sms", String(sendSms));
      setResult(await api.screen(form));
    } catch (err) {
      const rejected = err instanceof ApiError ? err.fundusRejection : null;
      if (rejected) setRejection(rejected);
      else setError(err instanceof ApiError ? err.message : "Screening failed.");
    } finally {
      setBusy(false);
    }
  }

  const notAFundus = quality && !quality.fundus.is_fundus;
  const ready = Boolean(file && fullName.trim() && status?.model_ready && !busy && !notAFundus);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <Card>
        <CardHeader>
          <CardTitle className="text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
            Patient &amp; image
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={analyse} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="name">Patient name</Label>
              <Input id="name" required value={fullName} placeholder="Full name"
                     onChange={(e) => setFullName(e.target.value)} />
            </div>

            <div className="grid grid-cols-[1.5fr_0.7fr_0.8fr] gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="phone">Mobile</Label>
                <Input id="phone" type="tel" value={phone} placeholder="98765 43210"
                       onChange={(e) => setPhone(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="age">Age</Label>
                <Input id="age" type="number" min={1} max={129} value={age}
                       onChange={(e) => setAge(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sex">Sex</Label>
                <Select value={sex} onValueChange={setSex}>
                  <SelectTrigger id="sex"><SelectValue placeholder="—" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="M">Male</SelectItem>
                    <SelectItem value="F">Female</SelectItem>
                    <SelectItem value="O">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Switch id="sms" checked={sendSms} onCheckedChange={setSendSms} />
              <Label htmlFor="sms" className="font-normal">Send SMS report to patient</Label>
            </div>

            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                pick(e.dataTransfer.files?.[0] ?? null);
              }}
              onClick={() => inputRef.current?.click()}
              className={`flex min-h-56 cursor-pointer items-center justify-center overflow-hidden rounded-xl border-2 border-dashed transition-colors ${
                dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
              }`}
            >
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview} alt="Fundus preview" className="max-h-72 w-full object-contain" />
              ) : (
                <div className="px-6 py-10 text-center">
                  <Upload className="mx-auto mb-2 size-6 text-muted-foreground/60" />
                  <p className="text-[13px] font-medium">Drop a fundus photograph here</p>
                  <p className="mt-0.5 text-[11.5px] text-muted-foreground">or click to browse</p>
                </div>
              )}
              <input ref={inputRef} type="file" accept="image/*" className="hidden"
                     onChange={(e) => pick(e.target.files?.[0] ?? null)} />
            </div>

            {file && (
              <div className="flex items-start justify-between gap-3 text-[12px]">
                <span className="truncate font-mono text-muted-foreground">{file.name}</span>
                {checking ? (
                  <span className="shrink-0 text-muted-foreground">Checking image…</span>
                ) : quality ? (
                  quality.fundus.is_fundus ? (
                    <span className="flex shrink-0 items-center gap-1 text-emerald-600">
                      <CheckCircle2 className="size-3.5" />
                      {quality.warnings.length === 0
                        ? "Fundus confirmed"
                        : quality.warnings.join(" · ")}
                    </span>
                  ) : (
                    <span className="flex shrink-0 items-center gap-1 text-destructive">
                      <ImageOff className="size-3.5" /> Not a retina
                    </span>
                  )
                ) : null}
              </div>
            )}

            {notAFundus && <NotAFundus reasons={quality!.fundus.reasons} score={quality!.fundus.score} />}
            {rejection && <NotAFundus reasons={rejection.reasons} score={rejection.check.score} />}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" className="w-full" disabled={!ready}>
              {busy ? "Analysing…" : "Analyse"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className={busy ? "scanning" : ""}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
            Result
          </CardTitle>
          {result && (
            <Button asChild variant="ghost" size="sm">
              <Link href={`/report?id=${result.screening_id}`}>Full report →</Link>
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {!result ? (
            <div className="flex min-h-[380px] flex-col items-center justify-center text-center">
              <p className="text-[13px] text-muted-foreground">
                {busy ? "Running inference…" : "Awaiting image"}
              </p>
              <p className="mt-1.5 max-w-xs text-[11.5px] text-muted-foreground/80">
                {busy
                  ? "The image and its mirror are both scored, then averaged."
                  : "Add patient details and a fundus photograph, then press Analyse."}
              </p>
            </div>
          ) : (
            <div className="rise space-y-5">
              <div className="flex items-center gap-5">
                <Gauge value={result.confidence} grade={result.grade} />
                <div className="min-w-0">
                  <p className="font-mono text-[11px] font-semibold tracking-wide uppercase"
                     style={{ color: gradeInk(result.grade) }}>
                    Grade {result.grade}
                  </p>
                  <h3 className="mt-0.5 text-2xl font-semibold tracking-tight"
                      style={{ color: gradeInk(result.grade) }}>
                    {result.label}
                  </h3>
                  <p className="mt-2 text-[13px] text-muted-foreground">{result.advice}</p>
                </div>
              </div>

              <Alert variant={result.referable ? "destructive" : "default"}>
                <AlertTitle>
                  {result.referable ? "Refer to an ophthalmologist" : "No referral required"}
                </AlertTitle>
                <AlertDescription>
                  P(referable) {Math.round(result.referral_probability * 100)}%
                </AlertDescription>
              </Alert>

              <ProbabilityBars values={result.probabilities} predicted={result.grade} />

              {result.warnings.length > 0 && (
                <p className="flex items-start gap-1.5 text-[11.5px] text-amber-600">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                  {result.warnings.join(" · ")}
                </p>
              )}

              <div className="flex flex-wrap gap-x-4 gap-y-1 border-t pt-3 font-mono text-[11px] text-muted-foreground">
                <span>#{String(result.screening_id).padStart(6, "0")}</span>
                <span>{result.model_version}</span>
                {result.sms_status && <span>sms: {result.sms_status}</span>}
              </div>

              {status?.chat_available && (
                <div className="border-t pt-4">
                  <p className="mb-3 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                    Explain this result
                  </p>
                  <Chat screeningId={result.screening_id} />
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Shown when the uploaded image isn't a retina — with the actual reasons. */
function NotAFundus({ reasons, score }: { reasons: string[]; score: number }) {
  return (
    <Alert variant="destructive">
      <ImageOff className="size-4" />
      <AlertTitle>This is not a retinal photograph</AlertTitle>
      <AlertDescription>
        <p>It was not graded, because grading a non-retinal image would produce a
          confident-looking result that means nothing.</p>
        <ul className="mt-1.5 list-disc space-y-1 pl-4">
          {reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
        <p className="mt-1.5 font-mono text-[11px] opacity-70">
          fundus score {score.toFixed(2)} — upload a fundus camera image instead.
        </p>
      </AlertDescription>
    </Alert>
  );
}
