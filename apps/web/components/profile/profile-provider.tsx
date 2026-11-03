"use client";

// Single profile fetch shared by the header, the dashboard greeting and
// the Profile page (Phase 1D). One GET on mount; save() updates every
// consumer without a refetch.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getProfile, updateProfile } from "@/services/api";
import type { Profile, ProfileResponse } from "@/types";

interface ProfileContextValue {
  configured: boolean;
  profile: Profile | null;
  createdAt: string | null;
  loading: boolean;
  error: boolean;
  save: (profile: Profile) => Promise<void>;
  refresh: () => Promise<void>;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ProfileResponse>({
    configured: false,
    profile: null,
    created_at: null,
    updated_at: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await getProfile();
      setState(response);
      setError(false);
    } catch {
      // API unreachable: consumers fall back to the neutral state and
      // the Profile page surfaces the failure itself.
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = useCallback(async (profile: Profile) => {
    const response = await updateProfile(profile);
    setState(response);
  }, []);

  const value = useMemo<ProfileContextValue>(
    () => ({
      configured: state.configured,
      profile: state.profile,
      createdAt: state.created_at,
      loading,
      error,
      save,
      refresh: load,
    }),
    [state, loading, error, save, load],
  );

  return (
    <ProfileContext.Provider value={value}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile(): ProfileContextValue {
  const context = useContext(ProfileContext);
  if (!context) {
    throw new Error("useProfile must be used inside <ProfileProvider>");
  }
  return context;
}

/** First word of the display name — "Hello, {first}". */
export function firstNameOf(profile: Profile | null): string {
  return profile?.display_name.trim().split(/\s+/)[0] ?? "";
}

export const AVATAR_CLASS: Record<Profile["avatar_color"], string> = {
  navy: "bg-avatar-navy",
  blue: "bg-avatar-blue",
  teal: "bg-avatar-teal",
  violet: "bg-avatar-violet",
  amber: "bg-avatar-amber",
  rose: "bg-avatar-rose",
};

export function initialsFrom(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
