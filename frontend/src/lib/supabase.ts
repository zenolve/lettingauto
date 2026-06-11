import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Supabase handles agent sign-in (email/password, Google, Microsoft). When
// the env vars are absent the app falls back to the legacy single-user
// bootstrap login against the backend (dev convenience).
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null;

export const supabaseEnabled = supabase !== null;
