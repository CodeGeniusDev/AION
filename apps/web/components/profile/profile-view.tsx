"use client";

// Profile = identity + real statistics only (Phase 1D). Notification
// preferences and the default view live exclusively in Settings; theme
// lives in the shared ThemeProvider. Everything here reads and writes
// GET/PUT /api/profile — nothing is seeded and nothing is fake.

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  Bell,
  Check,
  Loader2,
  Mail,
  Monitor,
  Moon,
  Palette,
  Save,
  Server,
  Sun,
  UserRound,
  X,
} from "lucide-react";
import {
  getApprovals,
  getConversations,
  getDashboard,
  getHealth,
  getWorkflows,
} from "@/services/api";
import type { AvatarColor, HealthData, Profile } from "@/types";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/page-header";
import { SectionCard } from "@/components/ui/section-card";
import { useTheme, type Theme } from "@/components/layout/theme-provider";
import {
  AVATAR_CLASS,
  initialsFrom,
  useProfile,
} from "@/components/profile/profile-provider";
import { cn } from "@/utils/cn";

const EMPTY_PROFILE: Profile = {
  display_name: "",
  username: "",
  email: "",
  role: "",
  timezone: "UTC",
  bio: "",
  avatar_color: "navy",
};

// IANA zones offered in the picker; the backend validates against the full
// tz database, and any stored zone outside this list is added dynamically.
const COMMON_TIMEZONES = [
  "UTC",
  "Africa/Lagos",
  "America/Denver",
  "America/Los_Angeles",
  "America/New_York",
  "Asia/Dubai",
  "Asia/Karachi",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Europe/London",
  "Europe/Paris",
  "Pacific/Auckland",
];

const AVATAR_COLORS: Array<{ value: AvatarColor; label: string }> = [
  { value: "navy", label: "Navy" },
  { value: "blue", label: "Blue" },
  { value: "teal", label: "Teal" },
  { value: "violet", label: "Violet" },
  { value: "amber", label: "Amber" },
  { value: "rose", label: "Rose" },
];

const USERNAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function slugPreview(name: string) {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 30) || "owner"
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 text-sm">
      <dt className="text-muted-text">{label}</dt>
      <dd className="min-w-0 truncate font-medium text-foreground">{value}</dd>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-surface px-4 py-3.5">
      <p className="text-xl font-semibold tracking-tight text-foreground">
        {value}
      </p>
      <p className="mt-0.5 text-xs text-muted-text">{label}</p>
    </div>
  );
}

interface WorkspaceStats {
  tasksTotal: number;
  tasksCompleted: number;
  tasksFailed: number;
  approvalsApproved: number;
  approvalsRejected: number;
  workflowRuns: number;
  memoryRecords: number;
  conversations: number;
}

const inputClass =
  "mt-2 h-11 w-full rounded-full border bg-surface px-4 text-sm text-foreground shadow-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";
const invalidClass =
  "border-destructive focus:border-destructive focus:ring-destructive/20";
const fieldHintClass = "mt-1 text-[11px] text-muted-text";
const fieldErrorClass = "mt-1.5 text-xs text-destructive";

export function ProfileView() {
  const { theme, setTheme } = useTheme();
  const {
    configured,
    profile,
    createdAt,
    loading: profileLoading,
    error: profileError,
    save,
    refresh,
  } = useProfile();

  const [form, setForm] = useState<Profile>(EMPTY_PROFILE);
  const [baseline, setBaseline] = useState<Profile>(EMPTY_PROFILE);
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [stats, setStats] = useState<WorkspaceStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState(false);
  const [statsAttempt, setStatsAttempt] = useState(0);

  // Sync the editable form whenever the shared profile changes (initial
  // load, manual refresh, or a save returning the canonical row).
  useEffect(() => {
    if (profile) {
      setForm(profile);
      setBaseline(profile);
      setTouched(false);
    } else if (!profileLoading && !profileError) {
      setForm(EMPTY_PROFILE);
      setBaseline(EMPTY_PROFILE);
    }
  }, [profile, profileLoading, profileError]);

  useEffect(() => {
    let mounted = true;
    getHealth()
      .then((h) => mounted && setHealth(h))
      .catch(() => mounted && setHealth(null));
    return () => {
      mounted = false;
    };
  }, []);

  // Real counts only — every number comes from an existing store.
  useEffect(() => {
    let mounted = true;
    setStatsLoading(true);
    setStatsError(false);
    Promise.all([
      getDashboard(),
      getApprovals({ status: "approved" }),
      getApprovals({ status: "rejected" }),
      getWorkflows(),
      getConversations(),
    ])
      .then(([dashboard, approved, rejected, workflows, conversations]) => {
        if (!mounted) return;
        setStats({
          tasksTotal: dashboard.task_counts?.total ?? dashboard.total_tasks,
          tasksCompleted:
            dashboard.task_counts?.completed ?? dashboard.total_tasks,
          tasksFailed: dashboard.task_counts?.failed ?? 0,
          approvalsApproved: approved.total,
          approvalsRejected: rejected.total,
          workflowRuns: workflows.items.reduce(
            (sum, w) => sum + (w.runs || 0),
            0,
          ),
          memoryRecords:
            dashboard.memory_stats?.total_records ?? dashboard.saved_memories,
          conversations: conversations.length,
        });
      })
      .catch(() => {
        if (mounted) setStatsError(true);
      })
      .finally(() => {
        if (mounted) setStatsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [statsAttempt]);

  // Unsaved-changes guard: warn before closing or reloading the tab.
  const dirty = useMemo(
    () => JSON.stringify(form) !== JSON.stringify(baseline),
    [form, baseline],
  );
  useEffect(() => {
    if (!dirty) return;
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  function update<K extends keyof Profile>(key: K, value: Profile[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setTouched(true);
    setSaved(false);
    setSaveError(null);
  }

  const trimmedName = form.display_name.trim();
  const nameError =
    trimmedName.length === 0
      ? "Display name cannot be empty."
      : trimmedName.length > 60
        ? "Display name cannot exceed 60 characters."
        : undefined;
  const usernameError =
    form.username && !USERNAME_RE.test(form.username)
      ? "Use lowercase letters, numbers and single hyphens."
      : form.username.length > 30
        ? "Username cannot exceed 30 characters."
        : undefined;
  const emailError =
    form.email && !EMAIL_RE.test(form.email)
      ? "Enter a valid email address."
      : undefined;
  const hasErrors = Boolean(nameError || usernameError || emailError);

  async function handleSave() {
    if (!dirty || hasErrors) return;
    setSaving(true);
    setSaveError(null);
    try {
      await save({ ...form, display_name: trimmedName });
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch {
      setSaveError("Saving failed. Is the AION API running?");
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    setForm(baseline);
    setTouched(false);
    setSaved(false);
    setSaveError(null);
  }

  const memberSince = createdAt
    ? new Date(createdAt).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : null;

  const header = (action?: ReactNode) => (
    <PageHeader
      eyebrow="Your account"
      title="Profile"
      description={
        configured
          ? "Your identity across AION and what your workspace has done."
          : "Set up your identity — your name appears in the header and dashboard."
      }
      action={action}
    />
  );

  if (profileLoading) {
    return (
      <>
        {header()}
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="size-6 animate-spin text-primary" />
        </div>
      </>
    );
  }

  const saveBar = (
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
        disabled={!dirty || saving || hasErrors}
        aria-label="Save profile changes">
        {saving ? (
          <Loader2 className="mr-2 size-4 animate-spin" />
        ) : saved ? (
          <Check className="mr-2 size-4" />
        ) : (
          <Save className="mr-2 size-4" />
        )}
        {saving
          ? "Saving…"
          : saved
            ? "Saved"
            : configured
              ? "Save changes"
              : "Create profile"}
      </Button>
    </div>
  );

  return (
    <>
      {header(saveBar)}

      <div className="space-y-6 p-4 sm:p-6 lg:p-7">
        {profileError ? (
          <div className="flex items-center gap-2 rounded-2xl border border-destructive bg-soft-peach/40 px-4 py-3 text-sm text-destructive">
            <X className="size-4 shrink-0" /> Could not load your profile — the
            AION API is not reachable.
            <Button
              variant="outline"
              size="sm"
              className="ml-auto"
              onClick={() => void refresh()}>
              Retry
            </Button>
          </div>
        ) : null}

        {saved ? (
          <div className="flex items-center gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-success-text">
            <Check className="size-4 shrink-0" /> Profile saved. The header and
            dashboard now show your name.
          </div>
        ) : null}

        {saveError ? (
          <div className="flex items-center gap-2 rounded-2xl border border-destructive bg-soft-peach/40 px-4 py-3 text-sm text-destructive">
            <X className="size-4 shrink-0" /> {saveError}
          </div>
        ) : null}

        {!configured ? (
          <div className="flex items-start gap-2 rounded-2xl border border-dashed border-border bg-muted/40 px-4 py-3 text-sm text-muted-text">
            <UserRound className="mt-0.5 size-4 shrink-0" />
            First run: nothing is saved until you create your profile. No
            profile data is pre-seeded anywhere in AION.
          </div>
        ) : null}

        {/* Section 1: Profile overview */}
        <section
          aria-label="Profile overview"
          className="flex flex-col items-start gap-5 rounded-[24px] border bg-surface p-6 sm:flex-row sm:items-center sm:gap-6">
          <span
            className={cn(
              "grid size-20 shrink-0 place-items-center rounded-full text-2xl font-semibold text-white shadow-md",
              AVATAR_CLASS[form.avatar_color],
            )}>
            {trimmedName ? (
              initialsFrom(trimmedName)
            ) : (
              <UserRound className="size-8" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-2xl font-bold tracking-tight text-foreground">
              {trimmedName || "Your name will appear here"}
            </h2>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-text">
              <span className="truncate">
                @{form.username || slugPreview(trimmedName)}
              </span>
              {form.role ? (
                <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                  {form.role}
                </span>
              ) : null}
            </p>
            {form.bio ? (
              <p className="mt-2 line-clamp-2 max-w-xl text-sm text-muted-text">
                {form.bio}
              </p>
            ) : null}
          </div>
          {health ? (
            <div className="sm:text-right">
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium",
                  health.status === "healthy"
                    ? "border-emerald-500/30 bg-emerald-500/10 text-success-text"
                    : "border-amber-500/30 bg-amber-500/10 text-warning-text",
                )}>
                {health.status === "healthy"
                  ? "System active"
                  : `System ${health.status}`}
              </span>
              <p className="mt-1 text-[11px] text-muted-text">
                {health.service} {health.version}
                {memberSince ? ` · Member since ${memberSince}` : ""}
              </p>
            </div>
          ) : null}
        </section>

        <div className="grid items-start gap-6 lg:grid-cols-2">
          {/* Section 2: Personal information (identity form) */}
          <SectionCard
            title="Personal information"
            description="Your identity across the AION workspace."
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
                  value={form.display_name}
                  maxLength={60}
                  onChange={(e) => update("display_name", e.target.value)}
                  aria-invalid={Boolean(touched && nameError)}
                  aria-describedby={
                    touched && nameError ? "display-name-error" : undefined
                  }
                  className={cn(
                    inputClass,
                    touched && nameError && invalidClass,
                  )}
                  placeholder="How should AION address you?"
                />
                {touched && nameError ? (
                  <p id="display-name-error" className={fieldErrorClass}>
                    {nameError}
                  </p>
                ) : null}
              </div>

              <div>
                <label
                  htmlFor="username-input"
                  className="block text-xs font-medium text-foreground">
                  Username
                </label>
                <input
                  id="username-input"
                  type="text"
                  value={form.username}
                  onChange={(e) => update("username", e.target.value)}
                  aria-invalid={Boolean(usernameError)}
                  className={cn(inputClass, usernameError && invalidClass)}
                  placeholder="Leave empty to derive from your name"
                />
                {usernameError ? (
                  <p className={fieldErrorClass}>{usernameError}</p>
                ) : (
                  <p className={fieldHintClass}>
                    Lowercase slug, max 30 characters.
                  </p>
                )}
              </div>

              <div>
                <label
                  htmlFor="email-input"
                  className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                  <Mail className="size-3.5" /> Email address (optional)
                </label>
                <input
                  id="email-input"
                  type="text"
                  inputMode="email"
                  value={form.email}
                  maxLength={254}
                  onChange={(e) => update("email", e.target.value)}
                  aria-invalid={Boolean(emailError)}
                  className={cn(inputClass, emailError && invalidClass)}
                  placeholder="you@example.com"
                />
                {emailError ? (
                  <p className={fieldErrorClass}>{emailError}</p>
                ) : (
                  <p className={fieldHintClass}>
                    Stored locally; AION never sends email today.
                  </p>
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="role-input"
                    className="block text-xs font-medium text-foreground">
                    Role label
                  </label>
                  <input
                    id="role-input"
                    type="text"
                    value={form.role}
                    maxLength={60}
                    onChange={(e) => update("role", e.target.value)}
                    className={cn(inputClass, "mt-2")}
                    placeholder="e.g. Operations lead"
                  />
                </div>
                <div>
                  <label
                    htmlFor="timezone-select"
                    className="block text-xs font-medium text-foreground">
                    Timezone
                  </label>
                  <select
                    id="timezone-select"
                    value={form.timezone}
                    onChange={(e) => update("timezone", e.target.value)}
                    className={cn(inputClass, "mt-2 rounded-full")}>
                    {(COMMON_TIMEZONES.includes(form.timezone)
                      ? COMMON_TIMEZONES
                      : [form.timezone, ...COMMON_TIMEZONES]
                    ).map((tz) => (
                      <option key={tz} value={tz}>
                        {tz}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label
                  htmlFor="bio-input"
                  className="block text-xs font-medium text-foreground">
                  Bio
                </label>
                <textarea
                  id="bio-input"
                  value={form.bio}
                  maxLength={200}
                  rows={3}
                  onChange={(e) => update("bio", e.target.value)}
                  className="mt-2 w-full rounded-2xl border bg-surface px-4 py-3 text-sm text-foreground shadow-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="A short note about you (optional)"
                />
                <p className={fieldHintClass}>{form.bio.length}/200</p>
              </div>

              <div>
                <span className="block text-xs font-medium text-foreground">
                  Avatar color
                </span>
                <div className="mt-2 flex items-center gap-2">
                  {AVATAR_COLORS.map(({ value, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => update("avatar_color", value)}
                      aria-label={`Avatar color: ${label}`}
                      aria-pressed={form.avatar_color === value}
                      className={cn(
                        "grid size-8 place-items-center rounded-full text-white transition-transform",
                        AVATAR_CLASS[value],
                        form.avatar_color === value &&
                          "ring-2 ring-primary ring-offset-2 ring-offset-surface",
                      )}>
                      {form.avatar_color === value ? (
                        <Check className="size-4" />
                      ) : null}
                    </button>
                  ))}
                </div>
                <p className={fieldHintClass}>
                  Photo upload is not supported by the backend — an initials
                  avatar is generated from your display name.
                </p>
              </div>
            </div>
          </SectionCard>

          <div className="space-y-6">
            {/* Section 3: Workspace statistics (real counts only) */}
            <SectionCard
              title="Workspace statistics"
              description="Counts from live AION stores — never demo data."
              action={<Palette className="size-5 text-primary" />}>
              {statsLoading ? (
                <div className="flex h-40 items-center justify-center">
                  <Loader2 className="size-5 animate-spin text-primary" />
                </div>
              ) : statsError || !stats ? (
                <div className="flex h-40 flex-col items-center justify-center gap-3 text-sm text-muted-text">
                  Statistics are unavailable — the AION API is not reachable.
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setStatsAttempt((a) => a + 1)}>
                    Retry
                  </Button>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <StatTile
                    label="Tasks total"
                    value={String(stats.tasksTotal)}
                  />
                  <StatTile
                    label="Tasks completed"
                    value={String(stats.tasksCompleted)}
                  />
                  <StatTile
                    label="Tasks failed"
                    value={String(stats.tasksFailed)}
                  />
                  <StatTile
                    label="Approvals approved"
                    value={String(stats.approvalsApproved)}
                  />
                  <StatTile
                    label="Approvals rejected"
                    value={String(stats.approvalsRejected)}
                  />
                  <StatTile
                    label="Workflow runs"
                    value={String(stats.workflowRuns)}
                  />
                  <StatTile
                    label="Memory records"
                    value={String(stats.memoryRecords)}
                  />
                  <StatTile
                    label="Conversations"
                    value={String(stats.conversations)}
                  />
                  <StatTile label="Member since" value={memberSince ?? "—"} />
                </div>
              )}
            </SectionCard>

            {/* Section 4: Account information (live runtime) */}
            <SectionCard
              title="Account information"
              description="Live runtime and infrastructure status from the AION backend."
              action={<Server className="size-5 text-primary" />}>
              <dl className="divide-y divide-border">
                <InfoRow
                  label="Service name"
                  value={health?.service ?? "Unavailable (API offline)"}
                />
                <InfoRow
                  label="API version"
                  value={health?.version ?? "Unavailable"}
                />
                <InfoRow
                  label="Active LLM engine"
                  value={health?.model_name ?? "Unavailable"}
                />
                <InfoRow
                  label="Account status"
                  value={
                    health
                      ? health.status === "healthy"
                        ? "Active (Online)"
                        : health.status
                      : "Unknown (API offline)"
                  }
                />
                <InfoRow
                  label="Cognitive memory"
                  value={
                    health
                      ? `${health.memory.status} (${health.memory.detail})`
                      : "Unknown (API offline)"
                  }
                />
                <InfoRow
                  label="Agent registry"
                  value={
                    health
                      ? `${health.agents.status} (${health.agents.detail})`
                      : "Unknown (API offline)"
                  }
                />
                <InfoRow
                  label="Tenant isolation"
                  value="default (Single-tenant)"
                />
              </dl>
            </SectionCard>

            {/* Section 5: Appearance + pointer to Settings */}
            <SectionCard
              title="Appearance"
              description="Theme applies instantly, persists on this device and syncs to the API."
              action={<Monitor className="size-5 text-primary" />}>
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    { value: "light", label: "Light", icon: Sun },
                    { value: "dark", label: "Dark", icon: Moon },
                    { value: "system", label: "System", icon: Monitor },
                  ] as const
                ).map(({ value, label, icon: Icon }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setTheme(value as Theme)}
                    aria-pressed={theme === value}
                    className={cn(
                      "flex items-center justify-center gap-2 rounded-full border py-2.5 text-xs font-medium transition-colors",
                      theme === value
                        ? "border-primary bg-soft-blue/40 text-foreground ring-1 ring-primary/30"
                        : "hover:bg-muted text-muted-text",
                    )}>
                    <Icon className="size-3.5" />
                    {label}
                  </button>
                ))}
              </div>
              <div className="mt-4 space-y-2 rounded-2xl border bg-muted/30 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                  <Bell className="size-4 text-primary" />
                  Notification preferences and default view live in Settings
                </div>
                <Link
                  href="/settings"
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline">
                  Open Settings
                </Link>
              </div>
            </SectionCard>
          </div>
        </div>
      </div>
    </>
  );
}
