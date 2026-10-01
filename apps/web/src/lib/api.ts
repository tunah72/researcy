export interface UserProfile {
  id: string;
  email: string;
  name: string | null;
  request_id: string;
}

export type ProcessingStage = 'queued' | 'validating' | 'parsing' | 'normalizing' | 'chunking' | 'embedding' | 'indexing' | 'ready' | 'failed';
export interface Preparation {
  state: 'waiting' | 'preparing' | 'delayed' | 'failed' | 'complete';
  reason: 'temporary' | 'unsupported' | 'resource_limit' | 'integrity' | null;
  retryable: boolean;
  retry_after_seconds: number;
}
export interface JobResponse {
  job_id: string;
  paper_id: string;
  document_version: string;
  stage: ProcessingStage;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  failed_stage: ProcessingStage | null;
  error_code: string | null;
  retry_revision: number;
  preparation: Preparation;
  request_id: string;
}

export interface Paper {
  paper_id: string;
  title: string | null;
  authors: string[] | null;
  year: number | null;
  source: string;
  stage: ProcessingStage;
  active_version_id: string;
  source_version: string | null;
  screening_warning: string | null;
  job_id: string;
  retry_revision: number;
  preparation: Preparation;
}

export interface PaperListResponse {
  papers: Paper[];
  request_id: string;
}

export interface ReaderPage {
  page_index: number;
  media_box: [number, number, number, number];
  crop_box: [number, number, number, number];
  rotation: number;
}

export interface ReaderDocument {
  document_version: string;
  source_sha256: string;
  pdf_url: string;
  pages: ReaderPage[];
  outline: { title: string; page: number }[];
}

export interface PaperDetailResponse extends Paper {
  reader?: ReaderDocument | null;
  request_id: string;
}

export interface IntakeResponse {
  paper_id: string;
  document_version: string;
  job_id: string;
  stage: ProcessingStage;
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
  retryAfter?: number;

  constructor(status: number, code: string, message: string, requestId?: string, retryAfter?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

export function parseRetryAfter(headerValue: string | null | undefined): number | undefined {
  if (!headerValue) return undefined;
  const trimmed = headerValue.trim();
  if (/^\d+$/.test(trimmed)) {
    const seconds = Number(trimmed);
    return seconds > 0 ? seconds : undefined;
  }
  const timestamp = Date.parse(trimmed);
  if (!isNaN(timestamp)) {
    const diff = Math.ceil((timestamp - Date.now()) / 1000);
    return diff > 0 ? diff : undefined;
  }
  return undefined;
}

export function formatScreeningWarning(warning: string | null | undefined): string | null {
  if (!warning) return null;
  const trimmed = warning.trim();
  if (!trimmed) return null;

  if (trimmed === 'LOW_TEXT' || trimmed.startsWith('LOW_TEXT:')) {
    return 'Some text in this PDF may be difficult to read. You can keep it in your library.';
  }

  return 'This PDF may be difficult to read. You can keep it in your library.';
}

const USER_ERROR_MESSAGES: Readonly<Record<string, string>> = {
  INVALID_ARXIV_REFERENCE: 'Enter an arXiv paper ID or a link from arxiv.org.',
  ARXIV_NOT_FOUND: 'We could not find that paper on arXiv. Check the link or paper ID.',
  ARXIV_VERSION_NOT_FOUND: 'That edition is not available on arXiv. Check the paper link.',
  ARXIV_VERSION_CONFLICT: 'A different edition of this paper is already in your library.',
  ARXIV_UPSTREAM_ERROR: 'We could not get this paper from arXiv right now. Please try again later.',
  IMPORT_RATE_LIMITED: 'You have added several papers recently. Please wait before adding another.',
  PDF_UNSUPPORTED: 'Choose a PDF file to add to your library.',
  PDF_TOO_LARGE: 'This PDF is too large. Please choose a smaller file.',
  PDF_TOO_MANY_PAGES: 'This PDF has too many pages. Please choose a shorter document.',
  PDF_ENCRYPTED: 'This PDF is password-protected. Upload a copy without a password.',
  PDF_NO_TEXT: 'Choose a PDF with selectable text rather than a scanned copy.',
  PDF_INVALID: 'We could not read this PDF. Try opening it on your device or choose another copy.',
  PDF_SCREEN_TIMEOUT: 'We could not read this PDF in time. Please try another copy.',
  PDF_SCREEN_RESOURCE_LIMIT: 'We could not read this PDF. Please try another copy.',
  FILE_REQUIRED: 'Choose a PDF file before continuing.',
  IDEMPOTENCY_CONFLICT: 'The paper you selected has changed. Close this form and add it again.',
};

export function userErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  // API diagnostics stay in transport/logs; only known reader-facing guidance reaches the UI.
  if (Object.hasOwn(USER_ERROR_MESSAGES, error.code)) return USER_ERROR_MESSAGES[error.code];
  if (error.status === 401 || error.status === 403) return 'Please sign in again, then try once more.';
  if (error.status === 429) return 'Please wait a little before trying again.';
  return fallback;
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
  const retryAfter = parseRetryAfter(res.headers.get('retry-after'));
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
    throw new ApiError(res.status, code, message, requestId, retryAfter);
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

export async function fetchJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { method: 'GET', credentials: 'same-origin' });
  return parseResponse<JobResponse>(res);
}

export async function retryJob(jobId: string, revision: number): Promise<JobResponse> {
  const res = await mutate(`/api/jobs/${encodeURIComponent(jobId)}/retry`, JSON.stringify({ retry_revision: revision }));
  return parseResponse<JobResponse>(res);
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
    const retryAfter = parseRetryAfter(res.headers.get('retry-after'));
    try {
      const data = await res.json();
      if (data && typeof data === 'object') {
        if (data.code) code = String(data.code);
        if (data.message) message = String(data.message);
        if (data.request_id) requestId = String(data.request_id);
      }
    } catch {
      // response might be empty or non-JSON
    }
    throw new ApiError(res.status, code, message, requestId, retryAfter);
  }
}
