import axios, { AxiosError } from "axios";

import { getToken, signOut } from "./auth";

// In production the app is served same-origin behind nginx, so API calls use
// relative paths (/api/…, /auth/…) and nginx proxies them to the backend. In
// dev they hit the local backend directly. An explicit VITE_API_URL always wins.
const baseURL = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

export const api = axios.create({ baseURL });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      signOut();
      if (!location.pathname.startsWith("/login")) {
        location.assign("/login");
      }
    }
    return Promise.reject(error);
  },
);

// Public, unauthenticated client — used by landlord form pages with a URL token
export const publicApi = axios.create({ baseURL });

export type GateInfo = {
  advanced: boolean;
  target_stage: number;
  failures: string[];
};

export type PropertySummary = {
  id: string;
  address: string;
  post_code?: string;
  tenancy_type?: string;
  gate_status?: string;
  gate_block_reason?: string;
  stage_changed_at?: string;
  service_level?: string;
  stage_order?: number;
  stage_name?: string;
  tc_signed?: boolean;
  ta_ll_signed?: boolean;
  ta_tt_signed?: boolean;
  created_at?: string;
};

export type PropertyDetail = {
  id: string;
  fields: Record<string, any>;
  landlords: Array<Record<string, any>>;
  tenant: Record<string, any> | null;
};

export type DashboardData = {
  generated_at: string;
  act_now: {
    gate_blocked: number;
    offers_pending: number;
    certs_expiring_30d: number;
    referencing_pending: number;
    movein_ready: number;
    overdue_diary: number;
  };
  pipeline: {
    by_stage: { order: number; name?: string; count: number }[];
    split: { pre_tenancy: number; active: number; ending: number };
    total: number;
    stalled: { property_id: string; address?: string; stage_order: number; stage_name?: string; days_stuck: number }[];
  };
  compliance: {
    breakdown: { compliant: number; expiring: number; bad: number };
    expiry_runway: { property_id: string; address?: string; cert: string; expiry: string; days_left: number }[];
    epc_fg: number;
    hmo_unconfirmed: number;
  };
  upcoming: {
    diary_agenda: { property_id?: string; address?: string; type?: string; alert_date: string; days_until: number; message?: string }[];
    overdue_count: number;
  };
  portfolio: {
    active_tenancies: number;
    rent_roll_annual: number;
    rent_roll_monthly: number;
    tenancy_type_split: Record<string, number>;
    service_level_split: Record<string, number>;
    offer_conversion: Record<string, number>;
  };
};
