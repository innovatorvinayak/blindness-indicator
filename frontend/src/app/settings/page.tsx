"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api, ApiError, AppSettings } from "@/lib/api";

export default function SettingsPage() {
  const [s, setS] = useState<AppSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.settings().then(setS).catch(() => setError("Could not load settings."));
  }, []);

  function patch(next: Partial<AppSettings>) {
    setS((cur) => (cur ? { ...cur, ...next } : cur));
    setSaved(false);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!s) return;
    setBusy(true);
    setError(null);
    try {
      await api.saveSettings(s);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save settings.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title="Settings" subtitle="Clinic, notifications and assistants">
      {!s ? (
        <p className="text-sm text-muted-foreground">{error ?? "Loading…"}</p>
      ) : (
        <form onSubmit={save} className="max-w-3xl space-y-5">
          {saved && (
            <Alert><AlertDescription>Settings saved.</AlertDescription></Alert>
          )}
          {error && (
            <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>
          )}

          <Card>
            <CardHeader><CardTitle className="text-base">Clinic</CardTitle></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="clinic">Clinic name</Label>
                <Input id="clinic" value={s.clinic_name} required
                       onChange={(e) => patch({ clinic_name: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cc">Default country code</Label>
                <Input id="cc" value={s.default_country_code} required
                       onChange={(e) => patch({ default_country_code: e.target.value })} />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="thr">Referral threshold</Label>
                <Input id="thr" type="number" step="0.01" min="0.01" max="0.99"
                       value={s.referral_threshold} required
                       onChange={(e) => patch({ referral_threshold: Number(e.target.value) })} />
                <p className="text-[11.5px] text-muted-foreground">
                  P(grade ≥ moderate) above which a patient is flagged. Lower catches more true
                  cases at the cost of more false alarms.
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">SMS</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3">
                <Switch id="sms" checked={s.sms_enabled}
                        onCheckedChange={(v) => patch({ sms_enabled: v })} />
                <Label htmlFor="sms" className="font-normal">Send SMS reports</Label>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="tsid">Twilio account SID</Label>
                  <Input id="tsid" value={s.twilio_account_sid}
                         onChange={(e) => patch({ twilio_account_sid: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="ttok">Twilio auth token</Label>
                  <Input id="ttok" type="password" value={s.twilio_auth_token}
                         onChange={(e) => patch({ twilio_auth_token: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="tfrom">Twilio from number</Label>
                  <Input id="tfrom" value={s.twilio_from_number}
                         onChange={(e) => patch({ twilio_from_number: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="f2s">Fast2SMS API key</Label>
                  <Input id="f2s" type="password" value={s.fast2sms_api_key}
                         onChange={(e) => patch({ fast2sms_api_key: e.target.value })} />
                </div>
              </div>
              <p className="text-[11.5px] text-muted-foreground">
                Twilio is used when configured, else Fast2SMS, else messages are logged instead
                of sent. Neither provider is free — Twilio needs a card at signup, Fast2SMS needs
                a ₹100 wallet top-up before its API accepts any request.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Assistants (Ollama)</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3">
                <Switch id="oll" checked={s.ollama_enabled}
                        onCheckedChange={(v) => patch({ ollama_enabled: v })} />
                <Label htmlFor="oll" className="font-normal">Enable the assistants</Label>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="ohost">Ollama host</Label>
                  <Input id="ohost" value={s.ollama_host} required
                         onChange={(e) => patch({ ollama_host: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="omodel">Chat model</Label>
                  <Input id="omodel" value={s.ollama_model} required
                         onChange={(e) => patch({ ollama_model: e.target.value })} />
                </div>
              </div>
              <p className="text-[11.5px] text-muted-foreground">
                The chat assistant explains a result in plain language. An optional vision model
                (<code className="font-mono text-[11px]">ollama pull llava</code>) adds
                descriptive observations to reports — it never decides the grade.
              </p>
            </CardContent>
          </Card>

          <div className="flex items-center gap-4">
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save settings"}
            </Button>
            <p className="text-[11.5px] text-muted-foreground">
              Model path, device and database URL come from environment variables and need an
              API restart.
            </p>
          </div>
        </form>
      )}
    </AppShell>
  );
}
