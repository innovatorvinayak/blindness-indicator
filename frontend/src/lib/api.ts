/**
 * Typed client for the FastAPI backend.
 *
 * Next.js rewrites proxy /api/* to the Python service (see next.config.ts),
 * so every call here is same-origin and the httpOnly session cookie rides
 * along automatically — no tokens in localStorage, no CORS config.
 */

export type Operator = { id: number; username: string };

export type Status = {
  operator: Operator | null;
  clinic_name: string;
  model_ready: boolean;
  model_error: string | null;
  model_path: string;
  chat_available: boolean;
  referral_threshold: number;
  signup_enabled: boolean;
  signup_requires_code: boolean;
};

export type ScreeningRow = {
  id: number;
  created_at: string;
  patient_name: string;
  phone: string | null;
  grade: number;
  label: string;
  advice: string;
  referable_grade: boolean;
  confidence: number;
  referable: boolean;
  sms_status: string | null;
};

export type ScreeningDetail = {
  id: number;
  created_at: string;
  patient_name: string;
  phone: string | null;
  age: number | null;
  sex: string | null;
  operator_username: string | null;
  image_sha256: string | null;
  grade: number;
  label: string;
  advice: string;
  confidence: number;
  referral_probability: number;
  referable: boolean;
  probabilities: number[];
  model_version: string;
  sms_status: string | null;
  history: Array<{
    id: number;
    created_at: string;
    grade: number;
    label: string;
    confidence: number;
    referable: boolean;
  }>;
};

export type ScreenResult = {
  screening_id: number;
  grade: number;
  label: string;
  advice: string;
  confidence: number;
  probabilities: number[];
  referral_probability: number;
  referable: boolean;
  warnings: string[];
  model_version: string;
  sms_status: string | null;
};

export type DashboardStats = {
  total: number;
  referable: number;
  referral_rate: number;
  unique_patients: number;
  screened_today: number;
  screened_week: number;
  grade_counts: number[];
  grade_percentages: number[];
  mean_confidence: number;
  low_confidence_count: number;
  sms_sent: number;
  sms_failed: number;
  sms_not_sent: number;
  daily: Array<{ date: string; label: string; total: number; referable: number }>;
  last_screening_at: string | null;
  busiest_day: string | null;
  severe_queue: ScreeningRow[];
  recent: ScreeningRow[];
  rejected_uploads: number;
  model: {
    ready: boolean;
    error: string | null;
    version: string | null;
    architecture: string | null;
    device: string | null;
    tta: boolean;
    channel_order: string | null;
  };
  config: {
    clinic_name: string;
    referral_threshold: number;
    sms_enabled: boolean;
    sms_provider: string;
  };
  assistant: {
    chat_available: boolean;
    chat_model: string;
    vision_available: boolean;
    vision_model: string;
  };
};

export type QualityCheck = {
  width: number;
  height: number;
  warnings: string[];
  fundus: {
    is_fundus: boolean;
    score: number;
    reasons: string[];
    metrics: Record<string, number>;
  };
};

export type AppSettings = {
  clinic_name: string;
  default_country_code: string;
  referral_threshold: number;
  sms_enabled: boolean;
  twilio_account_sid: string;
  twilio_auth_token: string;
  twilio_from_number: string;
  fast2sms_api_key: string;
  ollama_host: string;
  ollama_model: string;
  ollama_enabled: boolean;
};

/** Why an upload was refused before it ever reached the model. */
export type FundusRejection = {
  error: "not_a_fundus_image";
  message: string;
  reasons: string[];
  check: {
    is_fundus: boolean;
    score: number;
    reasons: string[];
    metrics: Record<string, number>;
  };
};

export class ApiError extends Error {
  status: number;
  /** Structured body for errors that carry one (e.g. a fundus rejection). */
  payload?: unknown;
  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }

  get fundusRejection(): FundusRejection | null {
    const p = this.payload as FundusRejection | undefined;
    return p && p.error === "not_a_fundus_image" ? p : null;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin", ...init });
  if (!res.ok) {
    let detail = res.statusText;
    let payload: unknown;
    try {
      const body = await res.json();
      payload = body?.detail;
      if (typeof body?.detail === "string") detail = body.detail;
      else if (typeof body?.detail?.message === "string") detail = body.detail.message;
    } catch {
      /* non-JSON error body — keep the status text */
    }
    throw new ApiError(res.status, detail, payload);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  status: () => request<Status>("/api/status"),
  me: () => request<Operator>("/api/me"),
  login: (username: string, password: string) =>
    request<Operator>("/api/login", json("POST", { username, password })),
  signup: (username: string, password: string, code: string) =>
    request<Operator>("/api/signup", json("POST", { username, password, code })),
  logout: () => request<{ ok: true }>("/api/logout", { method: "POST" }),

  qualityCheck: (file: File) => {
    const body = new FormData();
    body.append("image", file);
    return request<QualityCheck>("/api/quality-check", { method: "POST", body });
  },

  stats: () => request<DashboardStats>("/api/stats"),

  screen: (form: FormData) => request<ScreenResult>("/api/screen", { method: "POST", body: form }),

  screenings: (q = "", referralsOnly = false) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (referralsOnly) params.set("referrals_only", "true");
    const qs = params.toString();
    return request<ScreeningRow[]>(`/api/screenings${qs ? `?${qs}` : ""}`);
  },

  screening: (id: number) => request<ScreeningDetail>(`/api/screenings/${id}`),

  settings: () => request<AppSettings>("/api/settings"),
  saveSettings: (body: AppSettings) => request<{ ok: true }>("/api/settings", json("POST", body)),

  chat: (id: number, question: string, history: Array<{ role: string; content: string }>) =>
    request<{ answer: string }>(`/api/chat/${id}`, json("POST", { question, history })),
};

/**
 * Fills for chart marks. Grades 1-4 form a sequential ramp ordered by
 * lightness so severity survives colour-vision deficiency; grade 0 is a
 * separate "no disease" status colour. Validated with the dataviz checker.
 */
export const GRADE_COLORS = ["#059669", "#fed7aa", "#fb923c", "#dc2626", "#7f1d1d"];

/** Darker tones for text/labels — all pass 4.5:1 on a white card. */
export const GRADE_INK = ["#047857", "#b45309", "#c2410c", "#b91c1c", "#7f1d1d"];
export const GRADE_SHORT = ["No DR", "Mild", "Moderate", "Severe", "Proliferative"];

export function gradeColor(grade: number) {
  return GRADE_COLORS[grade] ?? GRADE_COLORS[0];
}

export function gradeInk(grade: number) {
  return GRADE_INK[grade] ?? GRADE_INK[0];
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
