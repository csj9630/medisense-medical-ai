import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { getDashboardOverview } from "../../../api/dashboard";
import type { DashboardOverview } from "../../../api/dashboard";
import { ApiError } from "../../../services/apiClient";
import { KpiCard } from "../components/KpiCard";
import { TrendLineChart } from "../components/TrendLineChart";
import { HorizontalBarChart } from "../components/HorizontalBarChart";
import { FALLBACK_MODEL_OPTIONS, getModelOption } from "../../../components/Chat/modelOptions";
import "../../admin/admin.css";
import "../dashboard.css";

const DAYS = 14;

function pct(value: number | null): string | null {
  if (value === null) return null;
  return `${Math.round(value * 100)}%`;
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load(signal?: AbortSignal) {
    setStatus("loading");
    setError(null);
    try {
      const overview = await getDashboardOverview(DAYS, signal);
      setData(overview);
      setStatus("ready");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof ApiError ? err.message : "대시보드를 불러오지 못했어요.");
      setStatus("error");
    }
  }

  return (
    <div className="admin-page dashboard-page">
      <div className="admin-section-heading">
        <div>
          <span className="admin-eyebrow">DASHBOARD</span>
          <h2>관리자 대시보드</h2>
          <p>서비스 운영 지표를 한눈에 봅니다. 실제 상담이 쌓일수록 지표가 채워집니다.</p>
        </div>
        <button
          type="button"
          className="admin-primary-button"
          onClick={() => void load()}
          disabled={status === "loading"}
        >
          {status === "loading" ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
          새로고침
        </button>
      </div>

      <div className="dashboard-filters">최근 {DAYS}일 기준</div>

      {status === "error" && (
        <div className="admin-card" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {status === "loading" && !data && (
        <div className="admin-card" style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
          <Loader2 size={20} className="spin" />
        </div>
      )}

      {data && (
        <>
          <div className="dashboard-kpis">
            <KpiCard label="오늘 상담 수" value={data.kpis.todayConsultations} />
            <KpiCard label="활성 사용자" value={data.kpis.activeUsersToday} />
            <KpiCard
              label="평균 응답 시간"
              value={data.kpis.avgResponseTimeMs === null ? null : `${(data.kpis.avgResponseTimeMs / 1000).toFixed(1)}s`}
            />
            <KpiCard label="RAG 검색 성공률" value={pct(data.kpis.ragHitRate)} sub="참고 문서가 검색된 비율" />
            <KpiCard label="응급 안내 건수" value={data.kpis.emergencyCountToday} />
            <KpiCard
              label="폴백 응답 비율"
              value={pct(data.kpis.fallbackRate)}
              sub="LLM 실패로 대체 응답이 나간 비율"
            />
            <KpiCard label="지식베이스 문서 수" value={data.kpis.documentCount} sub={`청크 ${data.kpis.chunkCount}개`} />
          </div>

          <div className="dashboard-charts">
            <div className="dashboard-chart-card">
              <h3>일별 상담 수</h3>
              <p className="chart-note">최근 {DAYS}일간 하루 상담 요청 수</p>
              <TrendLineChart data={data.dailyConsultations} />
            </div>
            <div className="dashboard-chart-card">
              <h3>사용자별 사용량 분포</h3>
              <p className="chart-note">개인 식별 없이 구간별 인원 수만 집계</p>
              <HorizontalBarChart
                items={data.userUsageDistribution.map((b) => ({ label: b.label, value: b.userCount }))}
                valueLabel="명"
              />
            </div>
          </div>

          <div className="dashboard-charts">
            <div className="dashboard-chart-card">
              <h3>모델별 사용/성공률</h3>
              <p className="chart-note">정상 응답한 비율 — 모델 서버가 꺼져있거나 준비 중이면 낮게 나올 수 있어요</p>
              <HorizontalBarChart
                items={data.modelUsage.map((m) => ({
                  label: getModelOption(m.modelId, FALLBACK_MODEL_OPTIONS).label,
                  value: Math.round(m.successRate * 100),
                  tooltipValue: `${Math.round(m.successRate * 100)}% (${m.success}/${m.total})`,
                }))}
                valueLabel="%"
              />
            </div>
            <div className="dashboard-chart-card">
              <h3>응급 안내 발생 추이</h3>
              <p className="chart-note">갑자기 늘면 응급 판단이 잘못됐을 가능성도 함께 확인해보세요</p>
              <TrendLineChart data={data.emergencyTrend} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
