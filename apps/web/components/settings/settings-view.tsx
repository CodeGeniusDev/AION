"use client";

import { useEffect, useState } from "react";
import { Bell, Bot, Check, Loader2, Monitor, Save, Settings2 } from "lucide-react";
import { getHealth, getSettings, updateSettings } from "@/services/api";
import type { AppSettings } from "@/types";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/page-header";
import { SectionCard } from "@/components/ui/section-card";

function Toggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-4 py-3">
      <span>
        <span className="block text-sm font-medium">{label}</span>
        <span className="mt-1 block text-xs text-muted-text">{description}</span>
      </span>
      <span className={`relative ml-auto h-7 w-12 rounded-full transition-colors ${checked ? "bg-primary" : "bg-[#d8dde4]"}`}>
        <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className={`absolute top-1 grid size-5 place-items-center rounded-full bg-white text-primary shadow-sm transition-transform ${checked ? "translate-x-6" : "translate-x-1"}`}>
          {checked && <Check className="size-3" />}
        </span>
      </span>
    </label>
  );
}

const defaultSettings: AppSettings = {
  workspace_name: "AION Workspace",
  default_view: "dashboard",
  preferred_model: "gemini-3.6-flash",
  theme: "light",
  memory_enabled: true,
  verification_enabled: true,
  notify_task_completions: true,
  notify_system_health: true,
  notify_weekly_summary: false,
};

export function SettingsView() {
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [modelName, setModelName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([getSettings(), getHealth()])
      .then(([s, h]) => {
        setSettings(s);
        setModelName(h.model_name || "");
      })
      .catch(() => { /* use defaults */ })
      .finally(() => setLoading(false));
  }, []);

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  async function handleSave() {
    setSaving(true);
    try {
      const updated = await updateSettings(settings);
      setSettings(updated);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2000);
    } catch {
      // non-blocking
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <>
        <PageHeader eyebrow="System preferences" title="Settings" description="Tune AION's workspace behavior and interface for this device." />
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="size-6 animate-spin text-primary" />
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="System preferences"
        title="Settings"
        description="Tune AION's workspace behavior and interface for this device."
        action={
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="mr-2 size-4 animate-spin" /> : saved ? <Check className="mr-2 size-4" /> : <Save className="mr-2 size-4" />}
            {saving ? "Saving..." : saved ? "Saved" : "Save Changes"}
          </Button>
        }
      />
      <div className="grid gap-5 p-4 sm:p-6 lg:grid-cols-2 lg:p-7">
        <SectionCard title="General" description="Basic workspace preferences" action={<Settings2 className="size-5 text-primary" />}>
          <div className="space-y-4">
            <label className="block text-xs font-medium">
              Workspace name
              <input
                value={settings.workspace_name}
                onChange={(e) => update("workspace_name", e.target.value)}
                className="mt-2 h-11 w-full rounded-full border px-4 text-sm"
              />
            </label>
            <label className="block text-xs font-medium">
              Default view
              <select
                value={settings.default_view}
                onChange={(e) => update("default_view", e.target.value)}
                className="mt-2 h-11 w-full rounded-full border bg-white px-4 text-sm"
              >
                <option value="dashboard">Dashboard</option>
                <option value="chat">AI Chat</option>
                <option value="tasks">Tasks</option>
              </select>
            </label>
          </div>
        </SectionCard>

        <SectionCard title="AI Model" description="Active model from backend configuration" action={<Bot className="size-5 text-primary" />}>
          <label className="block text-xs font-medium">
            Active model (read-only from backend)
            <div className="mt-2 h-11 w-full rounded-full border bg-[#f4f7fb] px-4 text-sm leading-[44px] text-muted-text">
              {modelName || settings.preferred_model}
            </div>
          </label>
          <div className="mt-4 rounded-[18px] bg-[#f4f7fb] p-4 text-xs leading-5 text-muted-text">
            Model selection is driven by the backend configuration. To change the active model, update the <code className="rounded bg-white px-1 text-[10px]">GeminiService</code> model in the API codebase.
          </div>
          <div className="mt-4 space-y-2 divide-y">
            <Toggle
              label="Memory enabled"
              description="Allow AION to read and write cognitive memory during chat"
              checked={settings.memory_enabled}
              onChange={(v) => update("memory_enabled", v)}
            />
            <Toggle
              label="Verification enabled"
              description="Run the Critic agent and Immune System on every response"
              checked={settings.verification_enabled}
              onChange={(v) => update("verification_enabled", v)}
            />
          </div>
        </SectionCard>

        <SectionCard title="Appearance" description="Choose how the workspace feels" action={<Monitor className="size-5 text-primary" />}>
          <div className="grid grid-cols-3 gap-2">
            {(["light", "system", "dim"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => update("theme", mode)}
                className={`rounded-[18px] border p-3 text-xs font-medium capitalize ${settings.theme === mode ? "border-primary bg-[#edf3ff] text-primary" : "bg-white"}`}
              >
                {mode}
              </button>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Notifications" description="Control system updates" action={<Bell className="size-5 text-primary" />}>
          <div className="divide-y">
            <Toggle
              label="Task completions"
              description="Notify when an agent finishes a task"
              checked={settings.notify_task_completions}
              onChange={(v) => update("notify_task_completions", v)}
            />
            <Toggle
              label="System health"
              description="Notify when a connected service changes"
              checked={settings.notify_system_health}
              onChange={(v) => update("notify_system_health", v)}
            />
            <Toggle
              label="Weekly summary"
              description="Receive a digest of recent AION activity"
              checked={settings.notify_weekly_summary}
              onChange={(v) => update("notify_weekly_summary", v)}
            />
          </div>
        </SectionCard>
      </div>
    </>
  );
}
