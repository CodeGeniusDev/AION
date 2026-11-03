"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  BadgeCheck,
  Bell,
  Building2,
  Check,
  CheckCircle2,
  Info,
  Loader2,
  Mail,
  Moon,
  Palette,
  Save,
  Server,
  Sun,
  Monitor,
  User,
  UserRound,
  X,
} from "lucide-react";
import { getHealth, getSettings, updateSettings } from "@/services/api";
import type { AppSettings, HealthData } from "@/types";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/page-header";
import { SectionCard } from "@/components/ui/section-card";
import { useTheme, type Theme } from "@/components/layout/theme-provider";
import { cn } from "@/utils/cn";

function initialsFrom(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "A";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function slugify(name: string) {
  const cleaned = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return cleaned || "owner";
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 text-sm">
      <dt className="text-muted-text">{label}</dt>
      <dd className="min-w-0 truncate font-medium text-foreground">{value}</dd>
    </div>
  );
}

export function ProfileView() {
  const { setTheme } = useTheme();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [baseline, setBaseline] = useState<AppSettings | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [s, h] = await Promise.all([
        getSettings(),
        getHealth().catch(() => null),
      ]);
      setSettings(s);
      setBaseline(s);
      setHealth(h);
    } catch {
      setLoadError(
        "Could not load profile data — the AION API is not reachable.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));
    setSaved(false);
    setSaveError(null);
  }

  const dirty =
    settings &&
    baseline &&
    JSON.stringify(settings) !== JSON.stringify(baseline);

  const nameTrimmed = settings?.workspace_name?.trim() ?? "";
  const nameError =
    nameTrimmed.length === 0
      ? "Display name cannot be empty."
      : nameTrimmed.length > 60
        ? "Display name cannot exceed 60 characters."
        : undefined;

  async function handleSave() {
    if (!settings || nameError) return;
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateSettings(settings);
      setSettings(updated);
      setBaseline(updated);
      if (
        updated.theme === "light" ||
        updated.theme === "dark" ||
        updated.theme === "system"
      ) {
        setTheme(updated.theme);
      }
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch {
      setSaveError("Saving failed. Is the AION API running?");
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    if (baseline) {
      setSettings(baseline);
      setSaved(false);
      setSaveError(null);
    }
  }

  if (loading) {
    return (
      <>
        <PageHeader
          eyebrow="Your account"
          title="Profile"
          description="Workspace identity, account details and preferences."
        />
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="size-6 animate-spin text-primary" />
        </div>
      </>
    );
  }

  const displayName = settings?.workspace_name ?? "AION Workspace";
  const username = slugify(displayName);

  return (
    <>
      <PageHeader
        eyebrow="Your account"
        title="Profile"
        description="Workspace identity, account details and preferences."
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={handleCancel}
              disabled={!dirty || saving}
              aria-label="Cancel changes">
              <X className="mr-2 size-4" /> Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={!dirty || saving || Boolean(nameError)}
              aria-label="Save profile changes">
              {saving ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : saved ? (
                <Check className="mr-2 size-4" />
              ) : (
                <Save className="mr-2 size-4" />
              )}
              {saving ? "Saving…" : saved ? "Saved" : "Save changes"}
            </Button>
          </div>
        }
      />

      <div className="space-y-6 p-4 sm:p-6 lg:p-7">
        {loadError ? (
          <div className="flex items-center gap-2 rounded-2xl border border-destructive bg-soft-peach/40 px-4 py-3 text-sm text-destructive">
            <Info className="size-4 shrink-0" /> {loadError}
          </div>
        ) : null}

        {saved ? (
          <div className="flex items-center gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="size-4 shrink-0" /> Profile and preferences
            saved successfully.
          </div>
        ) : null}

        {saveError ? (
          <div className="flex items-center gap-2 rounded-2xl border border-destructive bg-soft-peach/40 px-4 py-3 text-sm text-destructive">
            <X className="size-4 shrink-0" /> {saveError}
          </div>
        ) : null}

        {/* Section 1: Profile Overview */}
        <section
          aria-label="Profile overview"
          className="flex flex-col items-start gap-5 rounded-[24px] border bg-surface p-6 sm:flex-row sm:items-center sm:gap-6">
          <div className="relative">
            <span className="grid size-20 shrink-0 place-items-center rounded-full bg-navy text-2xl font-semibold text-white shadow-md">
              {initialsFrom(displayName)}
            </span>
            <span
              className={cn(
                "absolute bottom-0 right-0 size-5 rounded-full border-2 border-surface",
                health?.status === "healthy"
                  ? "bg-emerald-500"
                  : "bg-amber-500",
              )}
              title={health?.status === "healthy" ? "Online" : "Degraded"}
            />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-2xl font-bold tracking-tight text-foreground">
                {displayName}
              </h2>
              <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                Workspace Owner
              </span>
            </div>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-text">
              <Building2 className="size-4" /> @{username} · Single-tenant local
              instance
            </p>
          </div>
          {health ? (
            <div className="sm:text-right">
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium",
                  health.status === "healthy"
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
                )}>
                <BadgeCheck className="size-3.5" />
                {health.status === "healthy"
                  ? "System active"
                  : `System ${health.status}`}
              </span>
              <p className="mt-1 text-[11px] text-muted-text">
                {health.service} {health.version}
              </p>
            </div>
          ) : null}
        </section>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Section 2: Personal Information */}
          <SectionCard
            title="Personal information"
            description="Manage your identity across the AION workspace."
            action={<UserRound className="size-5 text-primary" />}>
            <div className="space-y-4">
              <div>
                <label
                  htmlFor="display-name-input"
                  className="block text-xs font-medium text-foreground">
                  Display name
                </label>
                <input
                  id="display-name-input"
                  type="text"
                  value={settings?.workspace_name ?? ""}
                  onChange={(e) => update("workspace_name", e.target.value)}
                  aria-invalid={Boolean(nameError)}
                  aria-describedby={
                    nameError ? "display-name-error" : undefined
                  }
                  className={cn(
                    "mt-2 h-11 w-full rounded-full border bg-surface px-4 text-sm text-foreground shadow-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20",
                    nameError &&
                      "border-destructive focus:border-destructive focus:ring-destructive/20",
                  )}
                  placeholder="Enter your name or workspace title"
                />
                {nameError ? (
                  <p
                    id="display-name-error"
                    className="mt-1.5 text-xs text-destructive">
                    {nameError}
                  </p>
                ) : null}
              </div>

              <div>
                <label className="block text-xs font-medium text-foreground">
                  Username
                </label>
                <div className="mt-2 flex h-11 items-center rounded-full border bg-muted/60 px-4 text-sm text-muted-text">
                  <User className="mr-2 size-4 text-muted-text" />
                  <span>@{username}</span>
                </div>
                <p className="mt-1 text-[11px] text-muted-text">
                  Derived from workspace identity.
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-foreground">
                  Email address
                </label>
                <div className="mt-2 flex h-11 items-center rounded-full border bg-muted/60 px-4 text-sm text-muted-text">
                  <Mail className="mr-2 size-4 text-muted-text" />
                  <span>Not configured (Local workspace mode)</span>
                </div>
                <p className="mt-1 text-[11px] text-muted-text">
                  Single-tenant workspace deployment. User accounts and email
                  credentials are not configured in this environment.
                </p>
              </div>

              <div className="rounded-2xl border border-dashed border-border bg-muted/40 p-3.5 text-xs text-muted-text">
                <span className="font-semibold text-foreground">
                  Avatar photo:
                </span>{" "}
                Photo upload is currently not supported by the backend
                architecture (requires an asset/file storage API). An initials
                avatar is automatically generated from your display name.
              </div>
            </div>
          </SectionCard>

          {/* Section 3: Account Information */}
          <SectionCard
            title="Account information"
            description="Live runtime and infrastructure status from the AION backend."
            action={<Server className="size-5 text-primary" />}>
            <dl className="divide-y divide-border">
              <InfoRow
                label="Service name"
                value={health?.service ?? "AION API"}
              />
              <InfoRow label="API version" value={health?.version ?? "0.1.0"} />
              <InfoRow
                label="Active LLM engine"
                value={
                  health?.model_name ??
                  settings?.preferred_model ??
                  "gemini-3.6-flash"
                }
              />
              <InfoRow
                label="Account status"
                value={
                  health?.status === "healthy"
                    ? "Active (Online)"
                    : (health?.status ?? "Unknown")
                }
              />
              <InfoRow
                label="Cognitive memory"
                value={
                  health
                    ? `${health.memory.status} (${health.memory.detail})`
                    : "Active"
                }
              />
              <InfoRow
                label="Agent registry"
                value={
                  health
                    ? `${health.agents.status} (${health.agents.detail})`
                    : "Active"
                }
              />
              <InfoRow
                label="Tenant isolation"
                value="default (Single-tenant)"
              />
              <InfoRow
                label="Account creation / Uptime"
                value="Current session (Process-lifetime)"
              />
            </dl>
          </SectionCard>

          {/* Section 4: Preferences */}
          <SectionCard
            title="Preferences"
            description="Customize default navigation and notifications."
            action={<Activity className="size-5 text-primary" />}
            className="lg:col-span-2">
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-4">
                <div>
                  <label
                    htmlFor="default-view-select"
                    className="block text-xs font-medium text-foreground">
                    Default landing view
                  </label>
                  <select
                    id="default-view-select"
                    value={settings?.default_view ?? "dashboard"}
                    onChange={(e) => update("default_view", e.target.value)}
                    className="mt-2 h-11 w-full rounded-full border bg-surface px-4 text-sm text-foreground shadow-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20">
                    <option value="dashboard">Dashboard</option>
                    <option value="chat">AI Chat</option>
                    <option value="tasks">Tasks</option>
                  </select>
                  <p className="mt-1 text-[11px] text-muted-text">
                    Page displayed when first launching AION.
                  </p>
                </div>

                <div>
                  <span className="block text-xs font-medium text-foreground">
                    Theme preference
                  </span>
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    {[
                      { value: "light" as Theme, label: "Light", icon: Sun },
                      { value: "dark" as Theme, label: "Dark", icon: Moon },
                      {
                        value: "system" as Theme,
                        label: "System",
                        icon: Monitor,
                      },
                    ].map(({ value, label, icon: Icon }) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => {
                          update("theme", value);
                          setTheme(value);
                        }}
                        aria-pressed={(settings?.theme ?? "light") === value}
                        className={cn(
                          "flex items-center justify-center gap-2 rounded-full border py-2.5 text-xs font-medium transition-colors",
                          (settings?.theme ?? "light") === value
                            ? "border-primary bg-primary/10 text-primary"
                            : "hover:bg-muted text-muted-text",
                        )}>
                        <Icon className="size-3.5" />
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="space-y-4 rounded-2xl border bg-muted/30 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                  <Bell className="size-4 text-primary" />
                  Notification preferences
                </div>

                <div className="space-y-3 text-sm">
                  <label className="flex items-center justify-between gap-3 cursor-pointer">
                    <span className="text-xs text-foreground">
                      Notify on task completions
                    </span>
                    <input
                      type="checkbox"
                      checked={settings?.notify_task_completions ?? true}
                      onChange={(e) =>
                        update("notify_task_completions", e.target.checked)
                      }
                      className="size-4 rounded text-primary focus:ring-primary"
                    />
                  </label>

                  <label className="flex items-center justify-between gap-3 cursor-pointer">
                    <span className="text-xs text-foreground">
                      Notify on system health alerts
                    </span>
                    <input
                      type="checkbox"
                      checked={settings?.notify_system_health ?? true}
                      onChange={(e) =>
                        update("notify_system_health", e.target.checked)
                      }
                      className="size-4 rounded text-primary focus:ring-primary"
                    />
                  </label>

                  <label className="flex items-center justify-between gap-3 cursor-pointer">
                    <span className="text-xs text-foreground">
                      Send weekly intelligence digest
                    </span>
                    <input
                      type="checkbox"
                      checked={settings?.notify_weekly_summary ?? false}
                      onChange={(e) =>
                        update("notify_weekly_summary", e.target.checked)
                      }
                      className="size-4 rounded text-primary focus:ring-primary"
                    />
                  </label>
                </div>

                <div className="pt-2">
                  <Link
                    href="/settings"
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline">
                    <Palette className="size-3.5" /> Configure advanced
                    parameters in Settings
                  </Link>
                </div>
              </div>
            </div>
          </SectionCard>
        </div>
      </div>
    </>
  );
}
