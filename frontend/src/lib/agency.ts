import { create } from "zustand";

import { api } from "./api";
import { brand } from "./brand";

export type AgencyMe = {
  agency_id: string;
  name: string;
  slug?: string;
  email?: string;
  phone?: string;
  office_address?: string;
  website?: string;
  logo_url?: string;
  brand_navy?: string;
  brand_gold?: string;
  onboarding_completed: boolean;
  membership: { email: string; name: string; role: string };
  billing: {
    enabled: boolean;
    pricing: { tenancy_setup_fee: number; currency: string };
    tenancy_fees_paid: number;
    tenancy_fees_pending: number;
  };
};

type Status = "idle" | "loading" | "ready" | "no_agency" | "error";

type AgencyStore = {
  agency: AgencyMe | null;
  status: Status;
  load: (force?: boolean) => Promise<void>;
  clear: () => void;
};

export const useAgency = create<AgencyStore>((set, get) => ({
  agency: null,
  status: "idle",
  load: async (force = false) => {
    const { status } = get();
    if (!force && (status === "loading" || status === "ready")) return;
    set({ status: "loading" });
    try {
      const { data } = await api.get<AgencyMe>("/api/agencies/me");
      set({ agency: data, status: "ready" });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 403 && (detail?.code === "no_agency" || detail === "no_agency")) {
        set({ agency: null, status: "no_agency" });
      } else {
        set({ status: "error" });
      }
    }
  },
  clear: () => set({ agency: null, status: "idle" }),
}));

/** The signed-in agency's display name, falling back to the platform brand. */
export function useAgencyName(): string {
  return useAgency((s) => s.agency?.name) ?? brand.name;
}
