/**
 * api.ts — All HTTP calls to the GitPhone Render backend.
 * Uses axios for clean async/await error handling.
 */

import axios, { AxiosError } from 'axios';
import { getBackendUrl } from './config';

export interface RegisterPayload {
  telegram_id: string;
  github_token: string;
  default_repo: string;
  branch: string;
}

export interface SyncFilePayload {
  telegram_id: string;
  filepath: string;
  diff: string | null;
  full_content: string | null;
  base_sha: string;
  is_binary: boolean;
  file_size: number;
}

export interface RegisterResponse {
  ok: boolean;
  message: string;
  telegram_id?: string;
  error?: string;
}

export interface SyncFileResponse {
  ok: boolean;
  staged_id?: string;
  message: string;
  error?: string;
}

export interface VersionResponse {
  schema_version: number;
  migration_sql: string | null;
  docs_url: string;
}

function baseUrl(): string {
  return getBackendUrl().replace(/\/$/, '');
}

export async function register(payload: RegisterPayload): Promise<RegisterResponse> {
  const response = await axios.post<RegisterResponse>(`${baseUrl()}/register`, payload, {
    timeout: 15000,
  });
  return response.data;
}

export async function syncFile(payload: SyncFilePayload): Promise<SyncFileResponse> {
  const response = await axios.post<SyncFileResponse>(`${baseUrl()}/sync-file`, payload, {
    timeout: 10000,
  });
  return response.data;
}

export async function getVersion(): Promise<VersionResponse> {
  const response = await axios.get<VersionResponse>(`${baseUrl()}/version`, {
    timeout: 5000,
  });
  return response.data;
}

export async function healthCheck(): Promise<boolean> {
  try {
    await axios.get(`${baseUrl()}/health`, { timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Extract a human-readable error message from an axios error.
 */
export function extractErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (typeof detail === 'object' && detail?.message) return detail.message;
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return 'Unknown error';
}
