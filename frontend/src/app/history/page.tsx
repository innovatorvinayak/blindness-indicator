"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Download, Search } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, formatDate, gradeInk, ScreeningRow } from "@/lib/api";

export default function HistoryPage() {
  const router = useRouter();
  const [rows, setRows] = useState<ScreeningRow[] | null>(null);
  const [q, setQ] = useState("");
  const [referralsOnly, setReferralsOnly] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await api.screenings(q, referralsOnly));
    } catch {
      setRows([]);
    }
  }, [q, referralsOnly]);

  useEffect(() => {
    const timer = setTimeout(load, 200); // debounce the search box
    return () => clearTimeout(timer);
  }, [load]);

  const referable = rows?.filter((r) => r.referable).length ?? 0;

  return (
    <AppShell
      title="Records"
      subtitle={rows ? `${rows.length} screenings · ${referable} referable` : undefined}
      actions={
        <Button asChild size="sm" variant="outline">
          <a href="/api/screenings/export.csv" download>
            <Download className="size-4" /> Export CSV
          </a>
        </Button>
      }
    >
      <Card>
        <CardContent className="pt-6">
          <div className="mb-4 flex flex-wrap items-center gap-4">
            <div className="relative">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search name or phone…"
                className="w-72 pl-9"
              />
            </div>
            <div className="flex items-center gap-2.5">
              <Switch id="ref" checked={referralsOnly} onCheckedChange={setReferralsOnly} />
              <Label htmlFor="ref" className="font-normal">Referrals only</Label>
            </div>
          </div>

          {rows === null ? (
            <p className="py-16 text-center text-[13px] text-muted-foreground">Loading…</p>
          ) : rows.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-[13px] text-muted-foreground">No screenings match.</p>
              <Button asChild variant="link" size="sm">
                <Link href="/screen">Screen a patient</Link>
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Patient</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Grade</TableHead>
                  <TableHead className="text-right">Confidence</TableHead>
                  <TableHead>Referral</TableHead>
                  <TableHead>SMS</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={row.id}
                    onClick={() => router.push(`/report?id=${row.id}`)}
                    className="cursor-pointer"
                  >
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {formatDate(row.created_at)}
                    </TableCell>
                    <TableCell className="font-medium">{row.patient_name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {row.phone ?? "—"}
                    </TableCell>
                    <TableCell>
                      <span className="text-[12.5px] font-medium" style={{ color: gradeInk(row.grade) }}>
                        {row.label}
                      </span>
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs tabular-nums">
                      {Math.round(row.confidence * 100)}%
                    </TableCell>
                    <TableCell>
                      {row.referable ? (
                        <Badge variant="destructive">Refer</Badge>
                      ) : (
                        <Badge variant="secondary">Clear</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {row.sms_status ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}
