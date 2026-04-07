import type {
  ApiResponse,
  User,
  UserListResponse,
  CreateUserRequest,
  UpdateUserRequest,
  VerifyResponse,
  IdentifyResponse,
  VerifyRequest,
  EnrollFingerprintRequest,
  EnrollResponse,
  ModelInfo,
  ProfileResult,
  LogListResponse,
  StatsResponse,
  HealthResponse,
  SensorStatus,
  SystemConfig,
  UpdateConfigRequest,
  CaptureResponse,
  BackupResponse,
  WsMessage,
} from '../types';

const API_BASE = '/api/v1';

// ============================================================
// HTTP Helpers
// ============================================================

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const config: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: response.statusText }));
    throw new ApiError(response.status, body.error || body.detail || 'Request failed');
  }

  return response.json();
}

async function uploadFile<T>(
  endpoint: string,
  formData: FormData,
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: response.statusText }));
    throw new ApiError(response.status, body.error || body.detail || 'Upload failed');
  }

  return response.json();
}

// ============================================================
// Users API
// ============================================================

export const usersApi = {
  list: (params?: {
    page?: number;
    limit?: number;
    search?: string;
    department?: string;
    role?: string;
  }): Promise<ApiResponse<UserListResponse>> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.search) searchParams.set('search', params.search);
    if (params?.department) searchParams.set('department', params.department);
    if (params?.role) searchParams.set('role', params.role);
    const qs = searchParams.toString();
    return request(`/users${qs ? `?${qs}` : ''}`);
  },

  get: (id: string): Promise<ApiResponse<User>> =>
    request(`/users/${id}`),

  create: (data: CreateUserRequest): Promise<ApiResponse<User>> =>
    request('/users', { method: 'POST', body: JSON.stringify(data) }),

  update: (id: string, data: UpdateUserRequest): Promise<ApiResponse<User>> =>
    request(`/users/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  delete: (id: string): Promise<ApiResponse<null>> =>
    request(`/users/${id}`, { method: 'DELETE' }),
};

// ============================================================
// Fingerprint / Enrollment API
// ============================================================

export const fingerprintApi = {
  enroll: (userId: string, data: EnrollFingerprintRequest): Promise<ApiResponse<EnrollResponse>> =>
    request(`/users/${userId}/enroll-finger`, { method: 'POST', body: JSON.stringify(data) }),

  capture: (): Promise<ApiResponse<CaptureResponse>> =>
    request('/sensor/capture', { method: 'POST' }),
};

// ============================================================
// Verification API
// ============================================================

export const verificationApi = {
  verify: (data: VerifyRequest): Promise<ApiResponse<VerifyResponse>> =>
    request('/verify', { method: 'POST', body: JSON.stringify(data) }),

  identify: (): Promise<ApiResponse<IdentifyResponse>> =>
    request('/identify', { method: 'POST' }),
};

// ============================================================
// Models API
// ============================================================

export const modelsApi = {
  list: (): Promise<ApiResponse<{ models: ModelInfo[] }>> =>
    request('/models'),

  get: (id: string): Promise<ApiResponse<ModelInfo>> =>
    request(`/models/${id}`),

  upload: (file: File, name: string): Promise<ApiResponse<{ id: string; filename: string; size_mb: number; message: string }>> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    return uploadFile('/models/upload', formData);
  },

  activate: (id: string): Promise<ApiResponse<ModelInfo>> =>
    request(`/models/${id}/activate`, { method: 'POST' }),

  convert: (id: string, precision: string): Promise<ApiResponse<ModelInfo>> =>
    request(`/models/${id}/convert`, {
      method: 'POST',
      body: JSON.stringify({ precision }),
    }),

  profile: (id: string): Promise<ApiResponse<ProfileResult>> =>
    request(`/models/${id}/profile`, { method: 'POST' }),

  delete: (id: string): Promise<ApiResponse<null>> =>
    request(`/models/${id}`, { method: 'DELETE' }),
};

// ============================================================
// Logs API
// ============================================================

export const logsApi = {
  list: (params?: {
    page?: number;
    limit?: number;
    user_id?: string;
    action?: string;
    decision?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<ApiResponse<LogListResponse>> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.user_id) searchParams.set('user_id', params.user_id);
    if (params?.action) searchParams.set('action', params.action);
    if (params?.decision) searchParams.set('decision', params.decision);
    if (params?.date_from) searchParams.set('date_from', params.date_from);
    if (params?.date_to) searchParams.set('date_to', params.date_to);
    const qs = searchParams.toString();
    return request(`/logs${qs ? `?${qs}` : ''}`);
  },
};

// ============================================================
// Stats API
// ============================================================

export const statsApi = {
  get: (): Promise<ApiResponse<StatsResponse>> =>
    request('/stats'),
};

// ============================================================
// Health API
// ============================================================

export const healthApi = {
  get: (): Promise<ApiResponse<HealthResponse>> =>
    request('/health'),
};

// ============================================================
// Sensor API
// ============================================================

export const sensorApi = {
  status: (): Promise<ApiResponse<SensorStatus>> =>
    request('/sensor/status'),

  capture: (): Promise<ApiResponse<CaptureResponse>> =>
    request('/sensor/capture', { method: 'POST' }),

  reset: (): Promise<ApiResponse<null>> =>
    request('/sensor/reset', { method: 'POST' }),
};

// ============================================================
// Config API
// ============================================================

export const configApi = {
  get: (): Promise<ApiResponse<SystemConfig>> =>
    request('/config'),

  update: (data: UpdateConfigRequest): Promise<ApiResponse<SystemConfig>> =>
    request('/config', { method: 'PUT', body: JSON.stringify(data) }),

  backup: (): Promise<ApiResponse<BackupResponse>> =>
    request('/backup', { method: 'POST' }),

  restore: (file: File): Promise<ApiResponse<null>> => {
    const formData = new FormData();
    formData.append('file', file);
    return uploadFile('/config/restore', formData);
  },
};

// ============================================================
// WebSocket Helpers
// ============================================================

export function createWebSocket(
  path: string,
  onMessage: (msg: WsMessage) => void,
  onError?: (error: Event) => void,
  onClose?: () => void,
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws${path}`;
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const message: WsMessage = JSON.parse(event.data);
      onMessage(message);
    } catch {
      console.error('Failed to parse WebSocket message:', event.data);
    }
  };

  ws.onerror = (event) => {
    console.error('WebSocket error:', event);
    onError?.(event);
  };

  ws.onclose = () => {
    onClose?.();
  };

  return ws;
}

export function createVerificationStream(
  onMessage: (msg: WsMessage) => void,
  onError?: (error: Event) => void,
  onClose?: () => void,
): WebSocket {
  return createWebSocket('/verification', onMessage, onError, onClose);
}

export function createSensorStream(
  onMessage: (msg: WsMessage) => void,
  onError?: (error: Event) => void,
  onClose?: () => void,
): WebSocket {
  return createWebSocket('/sensor', onMessage, onError, onClose);
}
