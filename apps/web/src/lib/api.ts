export interface UserProfile {
  id: string;
  email: string;
  name: string | null;
  request_id: string;
}

export interface Paper {
  paper_id: string;
  title: string | null;
  authors: string[] | null;
  year: number | null;
  source: string;
  stage: string;
  active_version_id: string;
  source_version: string | null;
  screening_warning: string | null;
}

export interface PaperListResponse {
  papers: Paper[];
  request_id: string;
}

export interface PaperDetailResponse extends Paper {
  request_id: string;
}

export interface IntakeResponse {
  paper_id: string;
  document_version: string;
  job_id: string;
  stage: string;
  screening_warning: string | null;
  source_version: string | null;
  arxiv_version?: string | null;
  request_id: string;
}

export interface ApiErrorPayload {
  code: string;
  message: string;
  request_id?: string;
}

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function mutate(path: string, body?: BodyInit, key?: string): Promise<Response> {
  const csrf = typeof document !== 'undefined'
    ? decodeURIComponent(document.cookie.match(/(?:^|; )researcy_csrf=([^;]+)/)?.[1] ?? '')
    : '';

  return fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'X-CSRF-Token': csrf,
      ...(key ? { 'Idempotency-Key': key } : {}),
      ...(typeof body === 'string' ? { 'Content-Type': 'application/json' } : {}),
    },
    body,
  });
}


export async function parseResponse<T>(res: Response): Promise<T> {
  const requestIdHeader = res.headers.get('x-request-id');
  if (!res.ok) {
    let code = 'ERROR';
    let message = 'An unexpected error occurred.';
    let requestId = requestIdHeader ?? undefined;
    try {
      const data = await res.json();
      if (data && typeof data === 'object') {
        if (data.code) code = String(data.code);
        if (data.message) message = String(data.message);
        if (data.request_id) requestId = String(data.request_id);
      }
    } catch {
      message = res.statusText || message;
    }
    throw new ApiError(res.status, code, message, requestId);
  }

  const data = await res.json();
  if (data && typeof data === 'object' && requestIdHeader && !data.request_id) {
    data.request_id = requestIdHeader;
  }
  return data as T;
}

export async function fetchCurrentUser(): Promise<UserProfile> {
  const res = await fetch('/api/me', { method: 'GET', credentials: 'same-origin' });
  return parseResponse<UserProfile>(res);
}

export async function fetchPapers(search?: string): Promise<PaperListResponse> {
  const path = search && search.trim().length > 0
    ? `/api/papers?search=${encodeURIComponent(search.trim())}`
    : '/api/papers';
  const res = await fetch(path, { method: 'GET', credentials: 'same-origin' });
  return parseResponse<PaperListResponse>(res);
}

export async function fetchPaperDetail(paperId: string): Promise<PaperDetailResponse> {
  const res = await fetch(`/api/papers/${encodeURIComponent(paperId)}`, { method: 'GET', credentials: 'same-origin' });
  return parseResponse<PaperDetailResponse>(res);
}

export async function importArxiv(arxivIdOrUrl: string, idempotencyKey: string): Promise<IntakeResponse> {
  const res = await mutate(
    '/api/papers/arxiv',
    JSON.stringify({ arxiv_id_or_url: arxivIdOrUrl }),
    idempotencyKey
  );
  return parseResponse<IntakeResponse>(res);
}

export async function uploadPdf(file: File, idempotencyKey: string): Promise<IntakeResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await mutate('/api/papers/upload', formData, idempotencyKey);
  return parseResponse<IntakeResponse>(res);
}

export async function logoutUser(): Promise<void> {
  const res = await mutate('/auth/logout');
  if (!res.ok) {
    let code = 'LOGOUT_FAILED';
    let message = 'Sign-out request failed on the server.';
    let requestId = res.headers.get('x-request-id') ?? undefined;
    try {
      const data = await res.json();
      if (data && typeof data === 'object') {
        if (data.code) code = String(data.code);
        if (data.message) message = String(data.message);
        if (data.request_id) requestId = String(data.request_id);
      }
    } catch {
      // response might be empty or HTML
    }
    throw new ApiError(res.status, code, message, requestId);
  }
}
