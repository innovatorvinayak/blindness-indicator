"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  Database,
  FileText,
  Gauge,
  ImageOff,
  MessageSquareText,
  ScanEye,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import { Logo, Wordmark } from "@/components/Logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError, GRADE_SHORT, gradeInk } from "@/lib/api";

const SHOWCASE = [
  { src: "/samples/fundus-1.jpg", grade: 0, confidence: 0.94 },
  { src: "/samples/fundus-2.jpg", grade: 2, confidence: 0.81 },
  { src: "/samples/fundus-3.jpg", grade: 4, confidence: 0.88 },
];

const FEATURES = [
  { icon: ScanEye, title: "5-grade severity", body: "ResNet-152 with flip test-time augmentation returns the full probability distribution, not just a label." },
  { icon: ShieldCheck, title: "Referral triage", body: "A tunable P(grade ≥ moderate) threshold decides who needs a specialist, and how soon." },
  { icon: ImageOff, title: "Non-retina rejection", body: "Uploads that aren't fundus photographs are refused before grading, with the reason explained." },
  { icon: BarChart3, title: "Live dashboard", body: "Twenty panels: throughput, severity mix, referral rate, priority queue and system health." },
  { icon: FileText, title: "Lab-grade reports", body: "Decision margin, runner-up class, expected grade and provenance — exportable and printable." },
  { icon: Smartphone, title: "SMS to patients", body: "Twilio or Fast2SMS deliver the result straight to the patient's phone." },
  { icon: MessageSquareText, title: "Explain-my-result chat", body: "A local Ollama assistant answers questions about one specific screening, and nothing else." },
  { icon: Database, title: "Records that last", body: "Every screening archived with its image, hash and history — SQLite, MySQL or Postgres." },
];

const STEPS = [
  { n: "01", title: "Capture", body: "Enter the patient and drop in a fundus photograph. Quality and retina checks run instantly." },
  { n: "02", title: "Analyse", body: "The image and its mirror are both scored, then averaged, in about a second." },
  { n: "03", title: "Act", body: "Get a grade, a referral decision, a full report and an optional SMS to the patient." },
];

export default function LandingPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [clinic, setClinic] = useState<string | null>(null);
  const [shot, setShot] = useState(0);

  // Sign-up state, kept separate so switching tabs doesn't carry a failed
  // sign-in's credentials into the registration form.
  const [mode, setMode] = useState("signin");
  const [newUser, setNewUser] = useState("");
  const [newPass, setNewPass] = useState("");
  const [confirmPass, setConfirmPass] = useState("");
  const [signupCode, setSignupCode] = useState("");
  const [signupEnabled, setSignupEnabled] = useState(false);
  const [needsCode, setNeedsCode] = useState(false);

  useEffect(() => {
    api
      .status()
      .then((s) => {
        setClinic(s.clinic_name);
        setSignupEnabled(s.signup_enabled);
        setNeedsCode(s.signup_requires_code);
        if (s.operator) router.replace("/dashboard");
      })
      .catch(() => {});
  }, [router]);

  useEffect(() => {
    const timer = setInterval(() => setShot((i) => (i + 1) % SHOWCASE.length), 3800);
    return () => clearInterval(timer);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(username, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
      setBusy(false);
    }
  }

  async function register(e: React.FormEvent) {
    e.preventDefault();
    if (newPass !== confirmPass) {
      setError("The two passwords don't match.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.signup(newUser, newPass, signupCode);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the account.");
      setBusy(false);
    }
  }

  function switchMode(next: string) {
    setMode(next);
    setError(null);
  }

  const current = SHOWCASE[shot];

  return (
    <div className="min-h-screen">
      {/* ── hero ─────────────────────────────────────────────── */}
      <div className="aurora grid-paper">
        <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-2.5">
            <Logo size={34} />
            <Wordmark className="text-[17px]" />
          </div>
          <Badge variant="secondary" className="hidden sm:inline-flex">
            {clinic ?? "Diabetic retinopathy screening"}
          </Badge>
        </header>

        <main className="mx-auto grid max-w-6xl items-center gap-12 px-6 pt-6 pb-20 lg:grid-cols-[1.05fr_minmax(360px,0.9fr)] lg:gap-16">
          <section className="rise">
            <Badge className="mb-5 gap-1.5 bg-indigo-600 hover:bg-indigo-600">
              <Activity className="size-3.5" /> AI-assisted eye screening
            </Badge>

            <h1 className="text-4xl leading-[1.08] font-semibold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
              Catch blindness <span className="brand-text">before it starts</span>
            </h1>

            <p className="mt-5 max-w-lg text-[15.5px] leading-relaxed text-slate-600">
              Grade a fundus photograph in about a second, flag who needs a specialist, and keep
              the whole camp&apos;s records in one place. Built for screening where the
              ophthalmologists aren&apos;t.
            </p>

            <dl className="mt-8 grid max-w-lg grid-cols-3 gap-4">
              {[
                ["5", "severity grades"], ["< 1s", "per screening"], ["20", "dashboard panels"],
              ].map(([value, label]) => (
                <div key={label} className="rounded-xl border bg-white/70 p-3.5 backdrop-blur">
                  <dt className="font-mono text-2xl font-semibold text-indigo-600">{value}</dt>
                  <dd className="mt-0.5 text-[11.5px] text-slate-500">{label}</dd>
                </div>
              ))}
            </dl>

            <p className="mt-8 flex items-center gap-2 text-[12px] text-slate-500">
              <CheckCircle2 className="size-4 text-emerald-600" />
              AI-assisted screening aid — every result is confirmed by a qualified ophthalmologist.
            </p>
          </section>

          {/* ── sign-in ────────────────────────────────────── */}
          <section className="rise" style={{ animationDelay: "120ms" }}>
            <Card className={`shadow-xl shadow-indigo-500/5 ${error ? "shake" : ""}`}>
              <CardContent className="pt-6">
                <Tabs value={mode} onValueChange={switchMode}>
                  {signupEnabled && (
                    <TabsList className="mb-5 grid w-full grid-cols-2">
                      <TabsTrigger value="signin">Sign in</TabsTrigger>
                      <TabsTrigger value="signup">Create account</TabsTrigger>
                    </TabsList>
                  )}

                  {error && (
                    <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-[13px] text-rose-700">
                      {error}
                    </div>
                  )}

                  <TabsContent value="signin" className="mt-0">
                    <h2 className="text-lg font-semibold tracking-tight">Operator sign-in</h2>
                    <p className="mt-1 text-[13px] text-slate-500">
                      Restricted to registered screening staff.
                    </p>
                    <form onSubmit={submit} className="mt-5 space-y-4">
                      <div className="space-y-1.5">
                        <Label htmlFor="u">Username</Label>
                        <Input id="u" autoComplete="username" required
                               value={username} onChange={(e) => setUsername(e.target.value)} />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="p">Password</Label>
                        <Input id="p" type="password" autoComplete="current-password" required
                               value={password} onChange={(e) => setPassword(e.target.value)} />
                      </div>
                      <Button type="submit" className="w-full" disabled={busy}>
                        {busy ? "Verifying…" : "Sign in"}
                      </Button>
                    </form>
                    {!signupEnabled && (
                      <p className="mt-5 border-t pt-4 text-[11.5px] text-slate-500">
                        No account yet? An administrator creates one with{" "}
                        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10.5px] text-indigo-700">
                          drscreen add-user
                        </code>{" "}
                        on the server.
                      </p>
                    )}
                  </TabsContent>

                  <TabsContent value="signup" className="mt-0">
                    <h2 className="text-lg font-semibold tracking-tight">Create an operator account</h2>
                    <p className="mt-1 text-[13px] text-slate-500">
                      Operator accounts can read every patient record.
                    </p>
                    <form onSubmit={register} className="mt-5 space-y-4">
                      <div className="space-y-1.5">
                        <Label htmlFor="nu">Username</Label>
                        <Input id="nu" autoComplete="username" required minLength={3}
                               value={newUser} onChange={(e) => setNewUser(e.target.value)} />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="np">Password</Label>
                        <Input id="np" type="password" autoComplete="new-password" required
                               minLength={8} value={newPass}
                               onChange={(e) => setNewPass(e.target.value)} />
                        <p className="text-[11px] text-slate-500">At least 8 characters.</p>
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="cp">Confirm password</Label>
                        <Input id="cp" type="password" autoComplete="new-password" required
                               value={confirmPass}
                               onChange={(e) => setConfirmPass(e.target.value)} />
                      </div>
                      {needsCode && (
                        <div className="space-y-1.5">
                          <Label htmlFor="sc">Sign-up code</Label>
                          <Input id="sc" required value={signupCode}
                                 onChange={(e) => setSignupCode(e.target.value)} />
                          <p className="text-[11px] text-slate-500">
                            Ask your clinic administrator for this code.
                          </p>
                        </div>
                      )}
                      <Button type="submit" className="w-full" disabled={busy}>
                        {busy ? "Creating…" : "Create account & sign in"}
                      </Button>
                    </form>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          </section>
        </main>
      </div>

      {/* ── showcase ─────────────────────────────────────────── */}
      <section className="border-y bg-white">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-6 py-16 lg:grid-cols-2">
          <div className="relative">
            <div className="relative overflow-hidden rounded-2xl border bg-slate-950 shadow-lg">
              {SHOWCASE.map((item, i) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={item.src}
                  src={item.src}
                  alt="Retinal fundus photograph"
                  className="h-[320px] w-full object-cover transition-opacity duration-1000"
                  style={{ opacity: i === shot ? 1 : 0, position: i === shot ? "relative" : "absolute", inset: 0 }}
                />
              ))}
              <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 bg-gradient-to-t from-slate-950/90 to-transparent p-4">
                <div>
                  <p className="text-[10.5px] tracking-wide text-slate-300 uppercase">Predicted</p>
                  <p className="text-lg font-semibold text-white">
                    {GRADE_SHORT[current.grade]}
                  </p>
                </div>
                <span
                  className="rounded-full px-3 py-1 font-mono text-xs font-semibold text-white"
                  style={{ background: gradeInk(current.grade) }}
                >
                  {Math.round(current.confidence * 100)}%
                </span>
              </div>
            </div>
            <div className="mt-3 flex justify-center gap-1.5">
              {SHOWCASE.map((item, i) => (
                <button
                  key={item.src}
                  onClick={() => setShot(i)}
                  aria-label={`Show example ${i + 1}`}
                  className={`h-1.5 rounded-full transition-all ${
                    i === shot ? "w-6 bg-indigo-600" : "w-1.5 bg-slate-300"
                  }`}
                />
              ))}
            </div>
          </div>

          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
              From photograph to referral decision
            </h2>
            <p className="mt-3 text-[14.5px] leading-relaxed text-slate-600">
              Diabetic retinopathy is a leading cause of preventable blindness, and it is silent
              until it isn&apos;t. Most clinics have far more diabetic patients than
              ophthalmologist hours. DRSCREEN does the first pass so specialists spend their time
              on the patients who need them.
            </p>
            <ol className="mt-7 space-y-5">
              {STEPS.map((step) => (
                <li key={step.n} className="flex gap-4">
                  <span className="font-mono text-sm font-semibold text-indigo-600">{step.n}</span>
                  <div>
                    <p className="font-medium text-slate-900">{step.title}</p>
                    <p className="mt-0.5 text-[13.5px] text-slate-600">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* ── features ─────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-center text-2xl font-semibold tracking-tight text-slate-900">
          Everything a screening camp needs
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-[14px] text-slate-600">
          Grading is the easy part. The rest is records, referrals, reports and getting the
          result back to the patient.
        </p>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <Card key={f.title} className="transition-shadow hover:shadow-md">
              <CardContent className="pt-6">
                <span className="inline-flex size-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                  <f.icon className="size-4.5" />
                </span>
                <h3 className="mt-3.5 text-[14px] font-semibold text-slate-900">{f.title}</h3>
                <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-600">{f.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* ── grade scale ──────────────────────────────────────── */}
      <section className="border-t bg-slate-50">
        <div className="mx-auto max-w-6xl px-6 py-14">
          <h2 className="text-center text-[13px] font-semibold tracking-[0.14em] text-slate-500 uppercase">
            The five-point clinical scale
          </h2>
          <div className="mt-7 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {GRADE_SHORT.map((label, grade) => (
              <div key={label} className="rounded-xl border bg-white p-4">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-flex size-6 items-center justify-center rounded-md font-mono text-xs font-bold text-white"
                    style={{ background: gradeInk(grade) }}
                  >
                    {grade}
                  </span>
                  <p className="text-[13px] font-semibold text-slate-900">{label}</p>
                </div>
                <p className="mt-2 text-[11.5px] text-slate-600">
                  {[
                    "Routine re-screening in 12 months.",
                    "Re-screen in 6–12 months; control blood sugar.",
                    "Referable — ophthalmologist within 3 months.",
                    "Urgent referral within 4 weeks.",
                    "Sight-threatening — see a specialist immediately.",
                  ][grade]}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-6 flex items-center justify-center gap-2 text-[11.5px] text-slate-500">
            <Gauge className="size-3.5" />
            Grades 1–4 are ordered by colour lightness so severity stays readable with colour-vision deficiency.
          </p>
        </div>
      </section>

      <footer className="border-t bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8">
          <div className="flex items-center gap-2.5">
            <Logo size={26} />
            <Wordmark className="text-[13px]" />
          </div>
          <p className="flex items-center gap-1.5 text-[11.5px] text-slate-500">
            <Bot className="size-3.5" />
            AI-assisted screening aid — not a diagnostic device.
          </p>
        </div>
      </footer>
    </div>
  );
}
