// ============================================================
// Domain Models (matching backend Pydantic schemas)
// ============================================================

export type FingerEnum =
  | 'left_thumb'
  | 'left_index'
  | 'left_middle'
  | 'left_ring'
  | 'left_little'
  | 'right_thumb'
  | 'right_index'
  | 'right_middle'
  | 'right_ring'
  | 'right_little';

// Keep FingerType as alias for backward compat in components
export type FingerType = FingerEnum;

export interface EnrolledFinger {
  finger: FingerEnum;
  enrolled_at: string;
  quality_score: number;
}

export interface User {
  id: string;
  employee_id: string;
  full_name: string;
  department: string;
  role: string;
  is_active: boolean;
  enrolled_fingers: EnrolledFinger[];
  created_at: string;
  updated_at: string;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  user_id: string | null;
  employee_id: string | null;
  action: string; // "verify", "identify", "enroll"
  decision: string; // "accept", "reject", "error"
  score: number | null;
  latency_ms: number | null;
  details: string | null;
}

// Keep VerificationLog as alias for backward compat
export type VerificationLog = LogEntry;

export interface ModelInfo {
  id: string;
  filename: string;
  format: string;
  size_mb: number;
  is_active: boolean;
  created_at: string;
}

// Keep Model as alias
export type Model = ModelInfo;

export interface SensorStatus {
  connected: boolean;
  vendor_id: number | null;
  product_id: number | null;
  firmware_version: string | null;
  serial_number: string | null;
  resolution_dpi: number | null;
  user_count: number | null;
  compare_level: number | null;
  is_real_hardware: boolean;
}

export interface SystemConfig {
  device_id: string;
  verify_threshold: number;
  identify_threshold: number;
  identify_top_k: number;
  model_dir: string;
  data_dir: string;
  sensor_vid: number;
  sensor_pid: number;
  debug: boolean;
}

export interface DeviceInfo {
  device_id: string;
  hostname: string;
  ip_address: string | null;
  status: string;
  last_seen: string;
}

// ============================================================
// API Request Types
// ============================================================

export interface CreateUserRequest {
  employee_id: string;
  full_name: string;
  department: string;
  role: string;
}

export interface UpdateUserRequest {
  full_name?: string;
  department?: string;
  role?: string;
}

export interface VerifyRequest {
  user_id: string;
}

export interface IdentifyRequest {
  top_k?: number;
}

export interface EnrollFingerprintRequest {
  finger: FingerEnum;
  num_samples?: number;
}

export interface UpdateConfigRequest {
  verify_threshold?: number;
  identify_threshold?: number;
  identify_top_k?: number;
  debug?: boolean;
}

// ============================================================
// API Response Types
// ============================================================

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  timestamp?: string;
}

export interface PaginationMeta {
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface UserListResponse {
  users: User[];
  pagination: PaginationMeta;
}

export interface LogListResponse {
  logs: LogEntry[];
  pagination: PaginationMeta;
}

export interface VerifyResponse {
  matched: boolean;
  score: number;
  threshold: number;
  user_id: string;
  latency_ms: number;
}

export interface IdentifyCandidate {
  user_id: string;
  employee_id: string;
  full_name: string;
  score: number;
}

export interface IdentifyResponse {
  identified: boolean;
  candidates: IdentifyCandidate[];
  threshold: number;
  latency_ms: number;
}

export interface StatsResponse {
  enrolled_users: number;
  enrolled_fingers: number;
  verifications_today: number;
  identifications_today: number;
  acceptance_rate: number;
  rejection_rate: number;
  avg_latency_ms: number;
  uptime_seconds: number;
}

export interface HealthResponse {
  status: string;
  uptime_seconds: number;
  cpu_percent: number;
  cpu_temp_c: number | null;
  gpu_temp_c: number | null;
  memory_used_mb: number;
  memory_total_mb: number;
  disk_used_gb: number;
  disk_total_gb: number;
  sensor_connected: boolean;
  active_model: string | null;
  device_id: string;
}

export interface CaptureResponse {
  success: boolean;
  image_base64: string | null;
  width: number;
  height: number;
  quality_score: number;
  has_finger: boolean;
  message: string;
}

export interface EnrollResponse {
  user_id: string;
  finger: FingerEnum;
  quality_score: number;
  template_count: number;
  message: string;
}

export interface ProfileResult {
  model_id: string;
  avg_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  p95_latency_ms: number;
  throughput_fps: number;
  num_runs: number;
}

export interface BackupResponse {
  success: boolean;
  filename: string;
  size_mb: number;
  timestamp: string;
  message: string;
}

// ============================================================
// WebSocket Message Types
// ============================================================

export interface WsMessage {
  type: WsMessageType;
  payload: unknown;
  timestamp: string;
}

export type WsMessageType =
  | 'sensor_status'
  | 'capture_preview'
  | 'verification_result'
  | 'identification_result'
  | 'system_alert'
  | 'enrollment_progress'
  | 'conversion_progress';

export interface WsCapturePreview {
  type: 'capture_preview';
  payload: {
    image: string;
    quality_score: number;
  };
}

export interface WsVerificationResult {
  type: 'verification_result';
  payload: VerifyResponse;
}

export interface WsIdentificationResult {
  type: 'identification_result';
  payload: IdentifyResponse;
}

export interface WsConversionProgress {
  type: 'conversion_progress';
  payload: {
    model_id: string;
    progress: number;
    status: 'converting' | 'completed' | 'failed';
    message: string;
  };
}

export interface WsSystemAlert {
  type: 'system_alert';
  payload: {
    level: 'info' | 'warning' | 'error';
    message: string;
  };
}
