import { apiClient } from '../services/apiClient';
import { authStorage } from '../features/auth/authStorage';

export interface DashboardKpis {
  todayConsultations: number;
  activeUsersToday: number;
  avgResponseTimeMs: number | null;
  ragHitRate: number | null;
  emergencyCountToday: number;
  fallbackRate: number | null;
  documentCount: number;
  chunkCount: number;
}

export interface DashboardDailyPoint {
  date: string;
  count: number;
}

export interface DashboardModelUsage {
  modelId: string;
  total: number;
  success: number;
  successRate: number;
}

export interface DashboardUserUsageBucket {
  label: string;
  userCount: number;
}

export interface DashboardOverview {
  kpis: DashboardKpis;
  dailyConsultations: DashboardDailyPoint[];
  emergencyTrend: DashboardDailyPoint[];
  modelUsage: DashboardModelUsage[];
  userUsageDistribution: DashboardUserUsageBucket[];
}

/** 관리자 전용 — 로그인 토큰 필요(게스트 토큰으로는 403). */
export function getDashboardOverview(days = 14, signal?: AbortSignal): Promise<DashboardOverview> {
  return apiClient<DashboardOverview>(`/admin/dashboard/overview?days=${days}`, {
    token: authStorage.getToken(),
    signal,
  });
}
