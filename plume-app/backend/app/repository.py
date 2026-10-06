"""数据仓储：PostgreSQL/PostGIS 优先，缺省回退内存虚构数据。

表结构见 db/init.sql（PostGIS，geometry(Point,4326)，带 GIST 索引）。
运行时每个请求短连接；DATABASE_URL 未设置或连接失败时，
透明回退到 seed_data 内存数据，并在 /api/health 标明后端类型。
"""
from __future__ import annotations

import json
from typing import Any

from .config import settings
from .seed_data import SEED_METEOROLOGY, SEED_SOURCES

_SOURCE_COLS = (
    "id", "name", "pollutant", "lon", "lat", "stack_height_m",
    "emission_rate_g_s", "stack_diameter_m", "exit_velocity_ms", "stack_temp_k",
)
_MET_COLS = (
    "id", "name", "wind_from_deg", "wind_speed_ms", "stability_class",
    "ambient_temp_k", "pressure_hpa", "background_conc_ug_m3",
)


class MemoryRepository:
    backend = "memory"

    def __init__(self) -> None:
        self.sources = [dict(s) for s in SEED_SOURCES]
        self.meteorology = [dict(m) for m in SEED_METEOROLOGY]

    def list_sources(self) -> list[dict]:
        return [dict(s) for s in self.sources]

    def get_source(self, source_id: int) -> dict | None:
        return next((dict(s) for s in self.sources if s["id"] == source_id), None)

    def list_meteorology(self) -> list[dict]:
        return [dict(m) for m in self.meteorology]

    def get_meteorology(self, met_id: int) -> dict | None:
        return next((dict(m) for m in self.meteorology if m["id"] == met_id), None)


class PostgisRepository:
    backend = "postgis"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        import psycopg

        # 由调用方确保服务就绪；失败由 get_repository 的探测拦截
        return psycopg.connect(self.database_url, connect_timeout=3)

    @staticmethod
    def _rows(cur, columns: tuple[str, ...]) -> list[dict[str, Any]]:
        return [dict(zip(columns, row)) for row in cur.fetchall()]

    def list_sources(self) -> list[dict]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, pollutant,
                       ST_X(location) AS lon, ST_Y(location) AS lat,
                       stack_height_m, emission_rate_g_s,
                       stack_diameter_m, exit_velocity_ms, stack_temp_k
                FROM emission_source ORDER BY id
                """
            )
            return self._rows(cur, _SOURCE_COLS)

    def get_source(self, source_id: int) -> dict | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, pollutant,
                       ST_X(location) AS lon, ST_Y(location) AS lat,
                       stack_height_m, emission_rate_g_s,
                       stack_diameter_m, exit_velocity_ms, stack_temp_k
                FROM emission_source WHERE id = %s
                """,
                (source_id,),
            )
            rows = self._rows(cur, _SOURCE_COLS)
            return rows[0] if rows else None

    def list_meteorology(self) -> list[dict]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(_MET_COLS)}
                FROM meteorology_scenario ORDER BY id
                """
            )
            return self._rows(cur, _MET_COLS)

    def get_meteorology(self, met_id: int) -> dict | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {", ".join(_MET_COLS)}
                FROM meteorology_scenario WHERE id = %s
                """,
                (met_id,),
            )
            rows = self._rows(cur, _MET_COLS)
            return rows[0] if rows else None


_repo: MemoryRepository | PostgisRepository | None = None


def get_repository() -> MemoryRepository | PostgisRepository:
    """惰性初始化：探测 PostGIS，失败回退内存仓储。"""
    global _repo
    if _repo is not None:
        return _repo
    if settings.database_url:
        candidate = PostgisRepository(settings.database_url)
        try:
            with candidate._connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT PostGIS_version()")
                cur.fetchone()
            _repo = candidate
        except Exception as exc:  # 连接/扩展不可用 -> 回退
            print(f"[repository] PostGIS 不可用，回退内存仓储: {exc}")
            _repo = MemoryRepository()
    else:
        _repo = MemoryRepository()
    return _repo


# ---------------------------------------------------------------------------
# 课堂预测练习题次仓储
# ---------------------------------------------------------------------------

_PREDICTION_MAX = 500


class MemoryPredictionStore:
    """进程内题次仓储（与内存数据源配套，应用重启即清空）。"""

    backend = "memory"

    def __init__(self) -> None:
        self._records: list[dict] = []
        self._seq = 0

    def add(self, record: dict) -> dict:
        self._seq += 1
        record = dict(record)
        record["id"] = self._seq
        record["sequence"] = self._seq
        self._records.append(record)
        if len(self._records) > _PREDICTION_MAX:
            self._records = self._records[-_PREDICTION_MAX:]
        return record

    def list(self) -> list[dict]:
        return list(reversed(self._records))

    def get(self, record_id: int) -> dict | None:
        return next((r for r in self._records if r["id"] == record_id), None)

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()
        self._seq = 0


class PostgisPredictionStore:
    """PostgreSQL 持久化题次（record 列为 JSONB 完整文档）。"""

    backend = "postgis"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url, connect_timeout=3)

    def add(self, record: dict) -> dict:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prediction_record (label, parameter, prediction, record)
                VALUES (%s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    record.get("label"),
                    record["input_summary"]["variable"]["parameter"],
                    record["prediction"],
                    json.dumps(record, ensure_ascii=False),
                ),
            )
            new_id = int(cur.fetchone()[0])
        record = dict(record)
        record["id"] = new_id
        record["sequence"] = new_id
        return record

    @staticmethod
    def _decode(row) -> dict:
        rec = row[3] if isinstance(row[3], dict) else json.loads(row[3])
        # 以表主键为准，避免 JSONB 内 id/sequence 与数据库不一致
        rec["id"] = row[0]
        rec["sequence"] = row[0]
        return rec

    def list(self) -> list[dict]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, label, record
                FROM prediction_record ORDER BY id DESC LIMIT %s
                """,
                (_PREDICTION_MAX,),
            )
            return [self._decode(r) for r in cur.fetchall()]

    def get(self, record_id: int) -> dict | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, created_at, label, record FROM prediction_record WHERE id = %s",
                (record_id,),
            )
            row = cur.fetchone()
        return self._decode(row) if row else None

    def count(self) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM prediction_record")
            return int(cur.fetchone()[0])

    def clear(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE prediction_record RESTART IDENTITY")


_prediction_store: MemoryPredictionStore | PostgisPredictionStore | None = None


def get_prediction_store() -> MemoryPredictionStore | PostgisPredictionStore:
    """题次仓储与主仓储后端保持一致；建表缺失时安全回退内存。"""
    global _prediction_store
    if _prediction_store is not None:
        return _prediction_store
    repo = get_repository()
    if repo.backend == "postgis":
        candidate = PostgisPredictionStore(settings.database_url)
        try:
            with candidate._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT to_regclass('public.prediction_record') IS NOT NULL"
                )
                if not bool(cur.fetchone()[0]):
                    raise RuntimeError("prediction_record 表尚未初始化")
            _prediction_store = candidate
        except Exception as exc:
            print(f"[repository] 题次表不可用，题次回退内存仓储: {exc}")
            _prediction_store = MemoryPredictionStore()
    else:
        _prediction_store = MemoryPredictionStore()
    return _prediction_store
