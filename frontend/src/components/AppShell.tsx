"use client";

import { ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  FileBarChart,
  LayoutDashboard,
  LogOut,
  ScanEye,
  Settings2,
} from "lucide-react";
import { Logo, Wordmark } from "@/components/Logo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { api, Status } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/screen", label: "New screening", icon: ScanEye },
  { href: "/history", label: "Records", icon: FileBarChart },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

/**
 * Chrome for every signed-in page: sidebar nav, page header, the
 * model-status banner, and the auth gate. The API enforces auth too — this
 * redirect is only so an unauthenticated visitor doesn't stare at an empty
 * shell while requests 401.
 */
export function AppShell({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    api
      .status()
      .then((s) => (s.operator ? setStatus(s) : router.replace("/")))
      .catch(() => router.replace("/"));
  }, [router]);

  async function signOut() {
    await api.logout().catch(() => {});
    router.replace("/");
  }

  if (!status) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Logo size={44} scanning />
      </div>
    );
  }

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <Link href="/dashboard" className="flex items-center gap-2.5 px-2 py-1.5">
            <Logo size={30} />
            <Wordmark className="text-[15px] group-data-[collapsible=icon]:hidden" />
          </Link>
        </SidebarHeader>

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Screening</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV.map((item) => {
                  const active =
                    pathname === item.href || pathname.startsWith(`${item.href}/`);
                  return (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
                        <Link href={item.href}>
                          <item.icon />
                          <span>{item.label}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                tooltip={`Signed in as ${status.operator?.username}`}
                className="pointer-events-none"
              >
                <Activity className="text-primary" />
                <span className="truncate">{status.operator?.username}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton onClick={signOut} tooltip="Sign out">
                <LogOut />
                <span>Sign out</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>

      <SidebarInset>
        <header className="print-hide sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b bg-background/85 px-4 py-3 backdrop-blur md:px-6">
          <SidebarTrigger className="-ml-1" />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-semibold tracking-tight">{title}</h1>
            {subtitle && (
              <p className="truncate text-[13px] text-muted-foreground">{subtitle}</p>
            )}
          </div>
          {actions}
        </header>

        <main className="flex-1 space-y-5 p-4 md:p-6">
          {status.model_error && (
            <Alert variant="destructive">
              <AlertTitle>Model weights not loaded — screening is disabled</AlertTitle>
              <AlertDescription>
                Expected at <code className="font-mono text-xs">{status.model_path}</code>. See
                models/README.md, then restart the API.
              </AlertDescription>
            </Alert>
          )}
          {children}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}

export function HeaderButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Button asChild size="sm">
      <Link href={href}>{children}</Link>
    </Button>
  );
}
