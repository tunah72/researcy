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

export type RunState = 'running' | 'completed' | 'refused' | 'failed' | 'interrupted';
export type MessageRole = 'user' | 'assistant';

export interface ResolvedCitation {
  citation_id: string;
  paper_id: string;
  document_version: string;
  source_ref: string;
  evidence_quote: string;
  page: number;
  boxes: [number, number, number, number][];
  section: string | null;
}

export interface CitationResponse {
  citation: ResolvedCitation;
  request_id: string;
}

export interface MessageSummary {
  id: string;
  role: MessageRole;
  text: string;
  state: RunState;
}

export interface Conversation {
  id: string;
  paper_id: string;
  document_version: string;
  created_at: string;
  updated_at: string;
  last_message: MessageSummary | null;
}

export interface Message {
  id: string;
  sequence: number;
  role: MessageRole;
  text: string;
  state: RunState;
  error_code: string | null;
  request_id: string;
  created_at: string;
  updated_at: string;
  citations: ResolvedCitation[];
}

export interface ConversationResponse {
  conversation: Conversation;
  request_id: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  next_before: string | null;
  request_id: string;
}

export interface MessageListResponse {
  messages: Message[];
  next_after: string | null;
  request_id: string;
}

export interface MessageSubmission {
  client_message_id: string;
  question: string;
}

export interface MessageStreamReplayResponse {
  run_id: string;
  message_id: string;
  state: RunState;
  request_id: string;
}

export interface ReaderStreamBaseData {
  run_id: string;
  message_id: string;
  request_id: string;
}

export interface ReaderStreamDeltaData extends ReaderStreamBaseData {
  sequence: number;
  text: string;
}

export interface ReaderStreamCitationResolvedData extends ReaderStreamBaseData {
  citation: ResolvedCitation;
}

export interface ReaderStreamCompletedData extends ReaderStreamBaseData {
  state: 'completed' | 'refused';
  citations: ResolvedCitation[];
}

export interface ReaderStreamFailedData extends ReaderStreamBaseData {
  code: string;
  message: string;
}

export type ReaderStreamEvent =
  | { event: 'answer.delta'; data: ReaderStreamDeltaData }
  | { event: 'citation.resolved'; data: ReaderStreamCitationResolvedData }
  | { event: 'answer.completed'; data: ReaderStreamCompletedData }
  | { event: 'answer.failed'; data: ReaderStreamFailedData };

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
  READER_INTERRUPTED: 'The answer was interrupted. Reload to see its saved state.',
  READER_FAILED: 'The answer could not be completed. Please submit a new question to retry.',
  READER_DEADLINE_EXCEEDED: 'The answer exceeded its time limit. Please submit a new question to retry.',
  READER_EVENT_TOO_LARGE: 'The answer evidence exceeds the size limit.',
  READER_RUN_NOT_ACTIVE: 'This answer is no longer active.',
  EVIDENCE_UNRESOLVED: 'The answer evidence could not be verified in the paper.',
  MESSAGE_CONFLICT: 'This question was already submitted. Try asking a new question.',
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

export async function mutate(path: string, body?: BodyInit, key?: string, signal?: AbortSignal): Promise<Response> {
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
    signal,
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

export async function fetchPaperDetail(paperId: string, documentVersion?: string): Promise<PaperDetailResponse> {
  const path = documentVersion
    ? `/api/papers/${encodeURIComponent(paperId)}?document_version=${encodeURIComponent(documentVersion)}`
    : `/api/papers/${encodeURIComponent(paperId)}`;
  const res = await fetch(path, { method: 'GET', credentials: 'same-origin' });
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

export async function createConversation(paperId: string, signal?: AbortSignal): Promise<ConversationResponse> {
  const res = await mutate(`/api/papers/${encodeURIComponent(paperId)}/conversations`, '{}', undefined, signal);
  return parseResponse<ConversationResponse>(res);
}

export async function listConversations(
  paperId: string,
  before?: string | null,
  signal?: AbortSignal,
): Promise<ConversationListResponse> {
  const path = before
    ? `/api/papers/${encodeURIComponent(paperId)}/conversations?before=${encodeURIComponent(before)}`
    : `/api/papers/${encodeURIComponent(paperId)}/conversations`;
  const res = await fetch(path, { method: 'GET', credentials: 'same-origin', signal });
  return parseResponse<ConversationListResponse>(res);
}

export async function listMessages(
  conversationId: string,
  after?: string | null,
  signal?: AbortSignal,
): Promise<MessageListResponse> {
  const path = after
    ? `/api/conversations/${encodeURIComponent(conversationId)}/messages?after=${encodeURIComponent(after)}`
    : `/api/conversations/${encodeURIComponent(conversationId)}/messages`;
  const res = await fetch(path, { method: 'GET', credentials: 'same-origin', signal });
  return parseResponse<MessageListResponse>(res);
}

const MAX_EVENT_BYTES = 262144;
const MAX_QUESTION_CODEPOINTS = 2400;
const MAX_BODY_BYTES = 16384;
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const VALID_RUN_STATES: Readonly<Record<RunState, true>> = {
  running: true,
  completed: true,
  refused: true,
  failed: true,
  interrupted: true,
};
const SUPPORTED_READER_EVENTS: Readonly<Record<string, true>> = {
  'answer.delta': true,
  'citation.resolved': true,
  'answer.completed': true,
  'answer.failed': true,
};

function validateResolvedCitation(raw: unknown): ResolvedCitation {
  if (!raw || typeof raw !== 'object') {
    throw new Error('Citation must be an object.');
  }
  const c = raw as Record<string, unknown>;
  if (typeof c.citation_id !== 'string' || !UUID_REGEX.test(c.citation_id)) {
    throw new Error('Invalid citation_id in citation.');
  }
  if (typeof c.paper_id !== 'string' || !UUID_REGEX.test(c.paper_id)) {
    throw new Error('Invalid paper_id in citation.');
  }
  if (typeof c.document_version !== 'string' || !UUID_REGEX.test(c.document_version)) {
    throw new Error('Invalid document_version in citation.');
  }
  if (typeof c.source_ref !== 'string' || !c.source_ref.trim()) {
    throw new Error('Invalid source_ref in citation.');
  }
  if (typeof c.evidence_quote !== 'string' || !c.evidence_quote.trim()) {
    throw new Error('Invalid evidence_quote in citation.');
  }
  if (typeof c.page !== 'number' || !Number.isInteger(c.page) || c.page < 1) {
    throw new Error('Invalid page in citation.');
  }
  if (!Array.isArray(c.boxes) || c.boxes.length === 0) {
    throw new Error('Invalid boxes in citation.');
  }
  for (const box of c.boxes) {
    if (
      !Array.isArray(box) ||
      box.length !== 4 ||
      !box.every((val) => typeof val === 'number' && Number.isFinite(val))
    ) {
      throw new Error('Invalid box geometry in citation.');
    }
    const [x0, y0, x1, y1] = box as number[];
    if (x0 > x1 || y0 > y1) {
      throw new Error('Invalid box coordinates in citation.');
    }
  }
  if (c.section !== null && typeof c.section !== 'string' && c.section !== undefined) {
    throw new Error('Invalid section in citation.');
  }
  return {
    citation_id: c.citation_id,
    paper_id: c.paper_id,
    document_version: c.document_version,
    source_ref: c.source_ref,
    evidence_quote: c.evidence_quote,
    page: c.page,
    boxes: c.boxes as [number, number, number, number][],
    section: (c.section as string | null) ?? null,
  };
}

function validateReplay(raw: unknown, initialRequestId?: string): MessageStreamReplayResponse {
  if (!raw || typeof raw !== 'object') {
    throw new ApiError(500, 'MALFORMED_STREAM', 'Replay response must be an object.', initialRequestId);
  }
  const r = raw as Record<string, unknown>;
  if (typeof r.run_id !== 'string' || !UUID_REGEX.test(r.run_id)) {
    throw new ApiError(500, 'MALFORMED_STREAM', 'Invalid run_id in replay response.', initialRequestId);
  }
  if (typeof r.message_id !== 'string' || !UUID_REGEX.test(r.message_id)) {
    throw new ApiError(500, 'MALFORMED_STREAM', 'Invalid message_id in replay response.', initialRequestId);
  }
  if (typeof r.state !== 'string' || !Object.hasOwn(VALID_RUN_STATES, r.state)) {
    throw new ApiError(500, 'MALFORMED_STREAM', 'Invalid state in replay response.', initialRequestId);
  }
  if (typeof r.request_id !== 'string' || !UUID_REGEX.test(r.request_id)) {
    throw new ApiError(500, 'MALFORMED_STREAM', 'Invalid request_id in replay response.', initialRequestId);
  }
  return {
    run_id: r.run_id,
    message_id: r.message_id,
    state: r.state as RunState,
    request_id: r.request_id,
  };
}

export async function getCitation(citationId: string, signal?: AbortSignal): Promise<CitationResponse> {
  const res = await fetch(`/api/citations/${encodeURIComponent(citationId)}`, {
    method: 'GET',
    credentials: 'same-origin',
    signal,
  });
  const data = await parseResponse<CitationResponse>(res);
  try {
    const validatedCitation = validateResolvedCitation(data.citation);
    if (typeof data.request_id !== 'string' || !UUID_REGEX.test(data.request_id)) {
      throw new Error('Invalid request_id');
    }
    return { citation: validatedCitation, request_id: data.request_id };
  } catch {
    throw new ApiError(500, 'MALFORMED_STREAM', 'Invalid citation payload received from server.', data?.request_id);
  }
}
export async function streamMessage(
  conversationId: string,
  submission: MessageSubmission,
  onEvent: (event: ReaderStreamEvent) => void,
  signal?: AbortSignal,
): Promise<MessageStreamReplayResponse | null> {
  if (signal?.aborted) {
    throw signal.reason ?? new DOMException('The operation was aborted.', 'AbortError');
  }

  if (!submission || typeof submission !== 'object') {
    throw new ApiError(422, 'INVALID_REQUEST', 'A valid message submission is required.');
  }

  if (!submission.client_message_id || !UUID_REGEX.test(submission.client_message_id)) {
    throw new ApiError(422, 'INVALID_REQUEST', 'A valid client message ID is required.');
  }

  if (!submission.question || !submission.question.trim() || submission.question.includes('\0')) {
    throw new ApiError(422, 'INVALID_REQUEST', 'A valid question is required.');
  }

  const codePoints = Array.from(submission.question).length;
  if (codePoints < 1 || codePoints > MAX_QUESTION_CODEPOINTS) {
    throw new ApiError(422, 'INVALID_REQUEST', 'Question exceeds character limit.');
  }

  const bodyJson = JSON.stringify({
    client_message_id: submission.client_message_id,
    question: submission.question,
  });

  const bodyBytes = new TextEncoder().encode(bodyJson).length;
  if (bodyBytes > MAX_BODY_BYTES) {
    throw new ApiError(413, 'REQUEST_TOO_LARGE', 'The request exceeds the size limit.');
  }

  const res = await mutate(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages:stream`,
    bodyJson,
    undefined,
    signal,
  );

  const initialRequestId = res.headers.get('x-request-id') ?? undefined;

  if (!res.ok) {
    return await parseResponse<MessageStreamReplayResponse | null>(res);
  }

  const contentType = res.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    const replayRaw = await parseResponse<unknown>(res);
    return validateReplay(replayRaw, initialRequestId);
  }
  if (!res.body) {
    throw new ApiError(500, 'READER_INTERRUPTED', 'The answer stream was empty.', initialRequestId);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
  const delimiterRegex = /\r\n\r\n|\n\n|\r\r/;
  let buffer = '';
  let terminalReceived = false;
  let establishedRunId: string | null = null;
  let establishedMessageId: string | null = null;
  let establishedRequestId: string | null = initialRequestId ?? null;
  let expectedSequence = 1;

  const processFrame = (frame: string, wireLength: number) => {
    if (wireLength > MAX_EVENT_BYTES) {
      throw new ApiError(
        500,
        'READER_EVENT_TOO_LARGE',
        'The answer evidence exceeds the stream limit.',
        establishedRequestId ?? undefined,
      );
    }

    const lines = frame.split(/\r\n|\n|\r/);
    let eventName = '';
    const dataLines: string[] = [];

    for (const line of lines) {
      if (line.startsWith(':')) {
        continue;
      }
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
      } else if (line === 'event') {
        eventName = '';
      } else if (line.startsWith('data:')) {
        const content = line.startsWith('data: ') ? line.slice(6) : line.slice(5);
        dataLines.push(content);
      } else if (line === 'data') {
        dataLines.push('');
      }
    }

    if (dataLines.length === 0) {
      return;
    }

    const rawData = dataLines.join('\n');
    let parsed: unknown;
    try {
      parsed = JSON.parse(rawData);
    } catch {
      throw new ApiError(
        500,
        'MALFORMED_STREAM',
        'Stream event contains invalid JSON.',
        establishedRequestId ?? undefined,
      );
    }

    if (!parsed || typeof parsed !== 'object') {
      throw new ApiError(
        500,
        'MALFORMED_STREAM',
        'Stream event data must be an object.',
        establishedRequestId ?? undefined,
      );
    }

    const data = parsed as Record<string, unknown>;
    const runId = typeof data.run_id === 'string' ? data.run_id : null;
    const messageId = typeof data.message_id === 'string' ? data.message_id : null;
    const requestId = typeof data.request_id === 'string' ? data.request_id : null;

    if (!runId || !messageId || !requestId) {
      throw new ApiError(
        500,
        'MALFORMED_STREAM',
        'Stream event missing required identity fields.',
        establishedRequestId ?? undefined,
      );
    }

    if (establishedRunId === null) {
      establishedRunId = runId;
      establishedMessageId = messageId;
      establishedRequestId = requestId;
    } else {
      if (runId !== establishedRunId || messageId !== establishedMessageId || requestId !== establishedRequestId) {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Stream event identity does not match run.',
          establishedRequestId ?? undefined,
        );
      }
    }

    if (!Object.hasOwn(SUPPORTED_READER_EVENTS, eventName)) {
      throw new ApiError(
        500,
        'MALFORMED_STREAM',
        `Unsupported stream event: ${eventName}`,
        establishedRequestId ?? undefined,
      );
    }

    if (eventName === 'answer.delta') {
      if (terminalReceived) {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Delta event received after stream termination.',
          establishedRequestId ?? undefined,
        );
      }
      const seq = data.sequence;
      if (typeof seq !== 'number' || seq !== expectedSequence) {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          `Stream delta sequence is out of order: expected ${expectedSequence}, got ${seq}.`,
          establishedRequestId ?? undefined,
        );
      }
      expectedSequence++;
      if (typeof data.text !== 'string') {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Delta event missing text.',
          establishedRequestId ?? undefined,
        );
      }
      onEvent({ event: 'answer.delta', data: data as unknown as ReaderStreamDeltaData });
    } else if (eventName === 'citation.resolved') {
      if (terminalReceived) {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Citation event received after stream termination.',
          establishedRequestId ?? undefined,
        );
      }
      try {
        const validated = validateResolvedCitation(data.citation);
        onEvent({
          event: 'citation.resolved',
          data: {
            run_id: runId,
            message_id: messageId,
            citation: validated,
            request_id: requestId,
          },
        });
      } catch {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Invalid citation in citation.resolved.',
          establishedRequestId ?? undefined,
        );
      }
    } else if (eventName === 'answer.completed') {
      if (terminalReceived) {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Duplicate terminal event received.',
          establishedRequestId ?? undefined,
        );
      }
      terminalReceived = true;
      if (data.state !== 'completed' && data.state !== 'refused') {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Invalid terminal state in answer.completed.',
          establishedRequestId ?? undefined,
        );
      }
      if (!Array.isArray(data.citations)) {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Citations field in answer.completed must be an array.',
          establishedRequestId ?? undefined,
        );
      }
      if (data.state === 'refused' && data.citations.length !== 0) {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Refused answer must have empty citations array.',
          establishedRequestId ?? undefined,
        );
      }
      try {
        const validatedCitations = data.citations.map((c) => validateResolvedCitation(c));
        onEvent({
          event: 'answer.completed',
          data: {
            run_id: runId,
            message_id: messageId,
            state: data.state,
            citations: validatedCitations,
            request_id: requestId,
          },
        });
      } catch {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Invalid citation in answer.completed citations list.',
          establishedRequestId ?? undefined,
        );
      }
    } else if (eventName === 'answer.failed') {
      if (terminalReceived) {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Duplicate terminal event received.',
          establishedRequestId ?? undefined,
        );
      }
      terminalReceived = true;
      if (typeof data.code !== 'string' || !data.code.trim() || typeof data.message !== 'string') {
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Invalid code or message in answer.failed event.',
          establishedRequestId ?? undefined,
        );
      }
      onEvent({
        event: 'answer.failed',
        data: {
          run_id: runId,
          message_id: messageId,
          code: data.code,
          message: data.message,
          request_id: requestId,
        },
      });
    }
  };

  const onAbort = () => {
    reader.cancel().catch(() => {});
  };
  signal?.addEventListener('abort', onAbort, { once: true });

  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel();
        throw signal.reason ?? new DOMException('The operation was aborted.', 'AbortError');
      }

      const { done, value } = await reader.read();

      if (signal?.aborted) {
        await reader.cancel();
        throw signal.reason ?? new DOMException('The operation was aborted.', 'AbortError');
      }

      if (done) {
        try {
          buffer += decoder.decode();
        } catch {
          throw new ApiError(
            500,
            'MALFORMED_STREAM',
            'Stream contains invalid UTF-8 data.',
            establishedRequestId ?? undefined,
          );
        }
        let match: RegExpExecArray | null;
        while ((match = delimiterRegex.exec(buffer)) !== null) {
          const frame = buffer.slice(0, match.index);
          const wireBytes = new TextEncoder().encode(frame + match[0]).length;
          buffer = buffer.slice(match.index + match[0].length);
          processFrame(frame, wireBytes);
          if (signal?.aborted) {
            await reader.cancel();
            throw signal.reason ?? new DOMException('The operation was aborted.', 'AbortError');
          }
        }
        break;
      }

      try {
        buffer += decoder.decode(value, { stream: true });
      } catch {
        await reader.cancel();
        throw new ApiError(
          500,
          'MALFORMED_STREAM',
          'Stream contains invalid UTF-8 data.',
          establishedRequestId ?? undefined,
        );
      }

      let match: RegExpExecArray | null;
      while ((match = delimiterRegex.exec(buffer)) !== null) {
        const frame = buffer.slice(0, match.index);
        const wireBytes = new TextEncoder().encode(frame + match[0]).length;
        buffer = buffer.slice(match.index + match[0].length);
        processFrame(frame, wireBytes);
        if (signal?.aborted) {
          await reader.cancel();
          throw signal.reason ?? new DOMException('The operation was aborted.', 'AbortError');
        }
      }

      if (terminalReceived) {
        try {
          await reader.cancel();
        } catch {
          // Safe close
        }
        break;
      }

      // Check unfinished frame buffer AFTER all complete frames in this chunk have been processed and removed
      const unfinishedBytes = new TextEncoder().encode(buffer).length;
      if (unfinishedBytes > MAX_EVENT_BYTES) {
        await reader.cancel();
        throw new ApiError(
          500,
          'READER_EVENT_TOO_LARGE',
          'The answer evidence exceeds the stream limit.',
          establishedRequestId ?? undefined,
        );
      }
    }
  } catch (err) {
    try {
      await reader.cancel();
    } catch {
      // Ignore reader cancel errors during exception handling
    }
    throw err;
  } finally {
    signal?.removeEventListener('abort', onAbort);
  }

  if (!terminalReceived) {
    throw new ApiError(
      500,
      'READER_INTERRUPTED',
      'The answer was interrupted before completing.',
      establishedRequestId ?? undefined,
    );
  }

  return null;
}
