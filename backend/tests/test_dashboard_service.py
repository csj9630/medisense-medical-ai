import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.services import dashboard_service


def _mock_execute_rows(db: MagicMock, rows: list[tuple]) -> None:
    db.execute.return_value.all.return_value = rows


class GetKpisTest(unittest.TestCase):
    # 2026-09-09: get_kpis()가 조건만 다른 count()를 여러 번(예전엔 6번) 따로
    # 날려서, Neon(원격 DB) 왕복 지연 때문에 대시보드 로드가 유독 느렸다(실측
    # 7.7초). 오늘자 집계는 조건부 SUM 하나로, document_count/chunk_count는
    # 스칼라 서브쿼리 둘을 한 SELECT로 묶어 왕복을 8회 -> 2회로 줄였다 - 그래서
    # db.scalar 대신 db.execute(...).one()을 두 번만 호출하는 걸 기준으로 검증한다.
    def test_zero_total_today_yields_none_rates_not_zero(self) -> None:
        # 오늘 상담이 0건이면 rag_hit_rate/fallback_rate는 "0%"가 아니라 "아직
        # 데이터 없음"을 뜻하는 None이어야 한다 — 0%라고 하면 "검색이 다 실패했다"는
        # 것처럼 잘못 읽힐 수 있다.
        db = MagicMock()
        db.execute.return_value.one.side_effect = [
            (0, 0, 0, 0, 0, None),  # total, rag_hits, fallback, emergency, active_users, avg_response
            (3, 7),  # document_count, chunk_count
        ]
        kpis = dashboard_service.get_kpis(db)

        self.assertEqual(kpis.today_consultations, 0)
        self.assertIsNone(kpis.rag_hit_rate)
        self.assertIsNone(kpis.fallback_rate)
        self.assertIsNone(kpis.avg_response_time_ms)
        self.assertEqual(kpis.document_count, 3)
        self.assertEqual(kpis.chunk_count, 7)
        self.assertEqual(db.execute.call_count, 2)

    def test_nonzero_total_computes_rates(self) -> None:
        # total_today=10, rag_hits=8, fallback=2 -> 80%/20%
        db = MagicMock()
        db.execute.return_value.one.side_effect = [
            (10, 8, 2, 1, 5, 1234.5),
            (3, 7),
        ]
        kpis = dashboard_service.get_kpis(db)

        self.assertEqual(kpis.today_consultations, 10)
        self.assertAlmostEqual(kpis.rag_hit_rate, 0.8)
        self.assertAlmostEqual(kpis.fallback_rate, 0.2)
        self.assertEqual(kpis.active_users_today, 5)
        self.assertEqual(kpis.avg_response_time_ms, 1234.5)
        self.assertEqual(kpis.emergency_count_today, 1)


class DailyConsultationsAndEmergencyTrendTest(unittest.TestCase):
    # get_overview()가 daily_consultations/emergency_trend를 따로 두 번 왕복하지
    # 않고 한 번에 가져오는 내부 헬퍼 - 결과가 get_daily_consultations()/
    # get_emergency_trend()를 각각 부른 것과 동일해야 한다.
    def test_matches_separate_daily_and_emergency_functions(self) -> None:
        db = MagicMock()
        today = date.today()
        middle_day = today - timedelta(days=1)
        _mock_execute_rows(db, [(middle_day, 5, 2)])  # 하루 총 5건 중 2건이 응급

        daily, emergency = dashboard_service._get_daily_consultations_and_emergency_trend(db, days=3)

        daily_by_date = {p.date: p.count for p in daily}
        emergency_by_date = {p.date: p.count for p in emergency}
        self.assertEqual(daily_by_date[str(middle_day)], 5)
        self.assertEqual(emergency_by_date[str(middle_day)], 2)
        # 로그가 없는 날은 두 시계열 모두 0으로 채워져야 한다(차트 x축이 안 끊기게).
        self.assertEqual([c for d, c in daily_by_date.items() if d != str(middle_day)], [0, 0])
        self.assertEqual([c for d, c in emergency_by_date.items() if d != str(middle_day)], [0, 0])
        # 왕복 한 번(execute 한 번)으로 두 시계열을 다 가져왔는지 확인한다.
        self.assertEqual(db.execute.call_count, 1)


class DailySeriesTest(unittest.TestCase):
    def test_missing_days_are_filled_with_zero(self) -> None:
        db = MagicMock()
        today = date.today()
        # 3일 중 가운데 하루만 데이터가 있다고 가정
        middle_day = today - timedelta(days=1)
        _mock_execute_rows(db, [(middle_day, 5)])

        points = dashboard_service.get_daily_consultations(db, days=3)

        self.assertEqual(len(points), 3)
        counts_by_date = {p.date: p.count for p in points}
        self.assertEqual(counts_by_date[str(middle_day)], 5)
        # 나머지 이틀은 로그가 없었으므로 0으로 채워져야 한다(차트 x축이 안 끊기게).
        zero_days = [c for d, c in counts_by_date.items() if d != str(middle_day)]
        self.assertEqual(zero_days, [0, 0])

    def test_points_are_in_chronological_order(self) -> None:
        db = MagicMock()
        _mock_execute_rows(db, [])
        points = dashboard_service.get_daily_consultations(db, days=5)

        dates = [p.date for p in points]
        self.assertEqual(dates, sorted(dates))


class ModelUsageTest(unittest.TestCase):
    def test_success_rate_computed_per_model(self) -> None:
        db = MagicMock()
        _mock_execute_rows(
            db,
            [
                ("medgemma-main", 10, 2),  # 10번 중 2번 성공(GPU 없어서 대부분 폴백 흉내)
                ("qwen-medical", 4, 4),
            ],
        )
        stats = dashboard_service.get_model_usage(db)

        by_model = {s.model_id: s for s in stats}
        self.assertAlmostEqual(by_model["medgemma-main"].success_rate, 0.2)
        self.assertAlmostEqual(by_model["qwen-medical"].success_rate, 1.0)

    def test_zero_total_does_not_raise_zero_division(self) -> None:
        db = MagicMock()
        _mock_execute_rows(db, [("llama-medical", 0, 0)])
        stats = dashboard_service.get_model_usage(db)

        self.assertEqual(stats[0].success_rate, 0.0)


class UserUsageDistributionTest(unittest.TestCase):
    def test_buckets_users_by_message_count(self) -> None:
        db = MagicMock()
        # 사용자별 상담 횟수: 3, 7, 15, 25, 30 -> 1~5:1명, 6~10:1명, 11~20:1명, 21+:2명
        _mock_execute_rows(db, [(3,), (7,), (15,), (25,), (30,)])
        buckets = dashboard_service.get_user_usage_distribution(db)

        by_label = {b.label: b.user_count for b in buckets}
        self.assertEqual(by_label["1~5"], 1)
        self.assertEqual(by_label["6~10"], 1)
        self.assertEqual(by_label["11~20"], 1)
        self.assertEqual(by_label["21+"], 2)

    def test_no_identifying_fields_are_returned(self) -> None:
        # 응답 구조 자체에 user_id/email 같은 개별 식별 필드가 없어야 한다 —
        # 익명 집계(구간별 인원 수)만 노출한다는 설계를 회귀 테스트로 고정.
        db = MagicMock()
        _mock_execute_rows(db, [(3,)])
        buckets = dashboard_service.get_user_usage_distribution(db)

        field_names = set(vars(buckets[0]).keys())
        self.assertEqual(field_names, {"label", "user_count"})


class GetOverviewCacheTest(unittest.TestCase):
    # 2026-09-09: get_overview()가 실시간성이 필요 없는 집계라 짧은 TTL로 캐싱하기
    # 시작했다 - Neon(원격 DB) 새 연결 비용이 지배적이라(실측 ~1~7초), 캐시가 있으면
    # 재방문/새로고침은 DB를 아예 안 타고 즉시 응답한다. 이 캐시는 모듈 전역 상태라
    # 테스트끼리 서로 오염되지 않게 매번 비운다.
    def setUp(self) -> None:
        dashboard_service._overview_cache.clear()

    def tearDown(self) -> None:
        dashboard_service._overview_cache.clear()

    def test_second_call_within_ttl_reuses_cached_result_without_hitting_db(self) -> None:
        db = MagicMock()
        with (
            patch.object(dashboard_service, "get_kpis", return_value="kpis") as kpis_mock,
            patch.object(dashboard_service, "_get_daily_consultations_and_emergency_trend", return_value=([], [])) as trend_mock,
            patch.object(dashboard_service, "get_model_usage", return_value=[]) as model_mock,
            patch.object(dashboard_service, "get_user_usage_distribution", return_value=[]) as usage_mock,
        ):
            first = dashboard_service.get_overview(db, days=14)
            second = dashboard_service.get_overview(db, days=14)

        self.assertIs(first, second)
        kpis_mock.assert_called_once()
        trend_mock.assert_called_once()
        model_mock.assert_called_once()
        usage_mock.assert_called_once()

    def test_different_days_are_cached_separately(self) -> None:
        db = MagicMock()
        with (
            patch.object(dashboard_service, "get_kpis", return_value="kpis"),
            patch.object(dashboard_service, "_get_daily_consultations_and_emergency_trend", return_value=([], [])),
            patch.object(dashboard_service, "get_model_usage", return_value=[]) as model_mock,
            patch.object(dashboard_service, "get_user_usage_distribution", return_value=[]),
        ):
            dashboard_service.get_overview(db, days=14)
            dashboard_service.get_overview(db, days=7)

        self.assertEqual(model_mock.call_count, 2)

    def test_expired_cache_entry_is_recomputed(self) -> None:
        db = MagicMock()
        with (
            patch.object(dashboard_service, "get_kpis", return_value="kpis"),
            patch.object(dashboard_service, "_get_daily_consultations_and_emergency_trend", return_value=([], [])),
            patch.object(dashboard_service, "get_model_usage", return_value=[]) as model_mock,
            patch.object(dashboard_service, "get_user_usage_distribution", return_value=[]),
        ):
            dashboard_service.get_overview(db, days=14)
            # 캐시에 기록된 시각을 TTL보다 훨씬 과거로 돌려서 만료를 흉내낸다.
            with dashboard_service._overview_cache_lock:
                cached_at, overview = dashboard_service._overview_cache[14]
                dashboard_service._overview_cache[14] = (
                    cached_at - dashboard_service._OVERVIEW_CACHE_TTL_SECONDS - 1,
                    overview,
                )
            dashboard_service.get_overview(db, days=14)

        self.assertEqual(model_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
