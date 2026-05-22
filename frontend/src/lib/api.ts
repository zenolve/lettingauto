import axios, { AxiosError } from "axios";

import { getToken, signOut } from "./auth";

const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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
