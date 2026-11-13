export type Workspace = { id: number; name: string; created_at: string };
export type Channel = { id: number; workspace_id: number; name: string; niche: string; language: string; budget_inr: number; publishing_enabled: number };
export type ProductionJob = { id: number; workspace_id: number; channel_id: number; title: string; format: 'short' | 'long'; state: string; created_at: string };
export type AuditEvent = { id: number; workspace_id: number; channel_id: number | null; job_id: number | null; action: string; created_at: string };
export type Overview = { channels: number; total_jobs: number; pending_review: number; approved: number; queue: number; states: Record<string, number>; youtube_connected: boolean; ai_enabled: boolean; publishing_enabled: boolean };

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    cache: 'no-store',
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data: { detail?: unknown } = await response.json();
      if (typeof data.detail === 'string') message = data.detail;
    } catch { /* Keep fallback error */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
