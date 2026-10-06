"""课堂预测练习 API 与判定规则测试。

验收点：
1. 排放率翻倍：受体烟羽/总浓度严格翻倍（可与解析结果核对）；
2. 改变源高：方向以受体实际两次结果判定，不使用固定口诀
   （给出不同受体方向相反的数值情形）；
3. 风速并非处处降低：开启 Holland 抬升时，增大 u 反而使近受体浓度升高，
   证明系统没有写死“风速越大必然降低”；
4. 静风变体：200 可保存，变体 computable=False、无任何浓度字段，
   原预测保留、不判对错；基准静风则 422 拒绝（题目不成立）；
5. 历史：列表不含大网格、详情含两次网格场。
"""
from __future__ import annotations

import math

from fastapi.testclient import TestClient

from app.main import app
from app.predictions import store

client = TestClient(app)

LON0, LAT0 = 116.40, 39.90


def _receptor_at(distance_m: float, wind_from: float = 270.0) -> list[float]:
    """源下风向 distance_m 处受体的经纬度（与后端同一平面近似）。"""
    theta = math.radians((wind_from + 180.0) % 360.0)
    east = distance_m * math.sin(theta)
    north = distance_m * math.cos(theta)
    lon = LON0 + math.degrees(east / (6_371_000.0 * math.cos(math.radians(LAT0))))
    lat = LAT0 + math.degrees(north / 6_371_000.0)
    return [lon, lat]


def _payload(
    *,
    u: float = 4.0,
    H: float = 60.0,
    Q: float = 50.0,
    rise: bool = False,
    bg: float = 10.0,
    stability: str = "D",
    parameter: str = "emission_rate_g_s",
    variant_value: float = 100.0,
    prediction: str = "up",
    receptor: list[float] | None = None,
    parameterization: str = "briggs_rural",
    power_law: dict | None = None,
    grid_extent: float = 4000.0,
) -> dict:
    return {
        "base_request": {
            "source": {
                "name": "测试源", "lon": LON0, "lat": LAT0,
                "stack_height_m": H, "emission_rate_g_s": Q,
                "stack_diameter_m": 4.0, "exit_velocity_ms": 18.0,
                "stack_temp_k": 410.0, "pollutant": "SO2",
            },
            "meteorology": {
                "name": "测试气象", "wind_from_deg": 270.0,
                "wind_speed_ms": u, "stability_class": stability,
                "ambient_temp_k": 293.15, "pressure_hpa": 1013.0,
                "background_conc_ug_m3": bg,
            },
            "grid": {
                "downwind_extent_m": grid_extent, "crosswind_extent_m": 1000.0,
                "upwind_extent_m": 0.0, "nx": 25, "ny": 7,
            },
            "plume_rise": {"use_plume_rise": rise},
            "parameterization": parameterization,
            "power_law": power_law,
            "calm_threshold_ms": 1.0,
        },
        "receptor_lonlat": receptor or _receptor_at(1000.0),
        "parameter": parameter,
        "variant_value": variant_value,
        "prediction": prediction,
        "label": "pytest",
    }


def setup_function(_):
    store.clear()


def test_emission_double_direction_and_analytical_ratio():
    """Q 翻倍：受体 plume 与 total 增量都严格翻倍，方向 up。"""
    resp = client.post("/api/predictions", json=_payload())
    assert resp.status_code == 200, resp.text
    rec = resp.json()
    b, v, cmp = rec["baseline"]["receptor"], rec["variant"]["receptor"], rec["comparison"]

    assert v["plume_conc_ug_m3"] == 2.0 * b["plume_conc_ug_m3"]
    # 背景不变：total 增量也恰为一份烟羽值
    assert cmp["delta"]["plume_conc_ug_m3"] == b["plume_conc_ug_m3"]
    assert cmp["delta"]["background_conc_ug_m3"] == 0.0
    assert cmp["delta"]["total_conc_ug_m3"] == b["plume_conc_ug_m3"]
    assert cmp["actual_direction"] == "up"
    assert cmp["prediction_correct"] is True
    # 两个网格场各自满足 total = plume + bg
    for run in (rec["baseline"], rec["variant"]):
        g = run["grid_response"]
        bg = g["background_conc_ug_m3"]
        for prow, trow in zip(g["plume_field_ug_m3"], g["total_conc_ug_m3"]):
            assert all(abs(t - (p + bg)) < 1e-9 for p, t in zip(prow, trow))


def test_source_height_judged_by_actual_receptor_not_rule():
    """源高变化：方向必须由受体处两次实际数值比较得出。

    本模型中 σy/σz 只依赖 x 与稳定度、不含 H，因此固定受体上
    ∂C/∂H 处处为负（高烟囱地面浓度更低），不存在“同一参数化下不同受体
    方向相反”的数学空间；但系统不得把这一结论写死成判定分支——
    改变高度的幅度、受体位置会带来「大幅降低」「基本不变」等不同判定，
    且开启 Holland 抬升时，方向还受有效源高随其它参数的耦合影响。

    这里验证：
    1) 近受体 H 60→20：实际显著升高（数值差远大于容差），
       学生若背“高烟囱更安全所以降高度也降低”的口诀会判错；
    2) 远受体 H 60→60.001：数值差落在容差内，必须判 same 而不是
       无条件 down（证明判定是数值比较，不是固定口诀）；
    3) 响应中明确写出判定依据为受体实际值比较。
    """
    pl = {"ay": 0.22, "py": 1.0, "az": 0.16, "pz": 1.0}

    near = client.post(
        "/api/predictions",
        json=_payload(
            H=60.0, parameter="stack_height_m", variant_value=20.0,
            prediction="down", receptor=_receptor_at(200.0),
            parameterization="power_law", power_law=pl, grid_extent=1500.0,
        ),
    )
    assert near.status_code == 200, near.text
    near_rec = near.json()
    # 近受体：烟囱从 60 降到 20，实际升高（学生背口诀预测 down -> 错）
    assert near_rec["comparison"]["actual_direction"] == "up"
    assert near_rec["comparison"]["prediction_correct"] is False
    assert near_rec["comparison"]["delta"]["total_conc_ug_m3"] > 100.0
    assert "受体处" in near_rec["comparison"]["judged_on"]
    assert "口诀" in near_rec["comparison"]["judged_on"]

    tiny = client.post(
        "/api/predictions",
        json=_payload(
            H=60.0, parameter="stack_height_m", variant_value=60.001,
            prediction="same", receptor=_receptor_at(50_000.0),
            parameterization="power_law", power_law=pl, grid_extent=4000.0,
        ),
    )
    assert tiny.status_code == 200, tiny.text
    tiny_rec = tiny.json()
    # 极小改动在低浓度远受体处落入容差带 -> same，而不是硬判 down
    assert tiny_rec["comparison"]["actual_direction"] == "same"
    assert tiny_rec["comparison"]["prediction_correct"] is True
    assert abs(tiny_rec["comparison"]["delta"]["total_conc_ug_m3"]) <= 1e-9


def test_wind_speed_not_hardcoded_as_always_down():
    """开启 Holland 抬升时：u 增大使 Δh 减小、有效源高降低，
    近受体（x=1000 m）浓度反而升高——系统不得写死“风大必降”。
    对照：关闭抬升时同受体同变化为降低。"""
    resp_up = client.post(
        "/api/predictions",
        json=_payload(
            u=3.0, rise=True, parameter="wind_speed_ms", variant_value=8.0,
            prediction="down", receptor=_receptor_at(1000.0),
        ),
    )
    assert resp_up.status_code == 200, resp_up.text
    rec_up = resp_up.json()
    assert rec_up["comparison"]["actual_direction"] == "up"
    assert rec_up["comparison"]["prediction_correct"] is False
    assert (
        rec_up["variant"]["effective_stack_height_m"]
        < rec_up["baseline"]["effective_stack_height_m"]
    )

    resp_dn = client.post(
        "/api/predictions",
        json=_payload(
            u=3.0, rise=False, parameter="wind_speed_ms", variant_value=8.0,
            prediction="down", receptor=_receptor_at(1000.0),
        ),
    )
    assert resp_dn.json()["comparison"]["actual_direction"] == "down"


def test_calm_variant_keeps_prediction_without_fake_concentration():
    """静风变体：题次保存、预测保留、变体无浓度字段/网格场、不判对错。"""
    resp = client.post(
        "/api/predictions",
        json=_payload(
            u=4.0, parameter="wind_speed_ms", variant_value=0.3,
            prediction="up",
        ),
    )
    assert resp.status_code == 200, resp.text
    rec = resp.json()
    assert rec["prediction"] == "up"
    variant = rec["variant"]
    assert variant["computable"] is False
    assert variant["reason"] == "calm_wind"
    # 不得存在任何浓度/网格字段（不填零、不造假）
    assert "receptor" not in variant
    assert "grid_response" not in variant
    for key in (
        "plume_conc_ug_m3", "total_conc_ug_m3", "background_conc_ug_m3",
        "plume_field_ug_m3", "total_conc_field",
    ):
        assert key not in variant
    cmp = rec["comparison"]
    assert cmp["computable"] is False
    assert cmp["actual_direction"] is None
    assert cmp["prediction_correct"] is None
    assert cmp["delta"] is None
    # 基准仍然正常
    assert rec["baseline"]["computable"] is True
    assert "grid_response" in rec["baseline"]


def test_calm_baseline_rejected_no_record():
    """基准静风：题目不成立，422 且不产生题次。"""
    resp = client.post(
        "/api/predictions",
        json=_payload(
            u=0.3, parameter="wind_speed_ms", variant_value=6.0,
            prediction="up",
        ),
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "calm_wind"
    assert client.get("/api/predictions").json()["count"] == 0


def test_history_list_strips_grids_but_detail_keeps_them():
    resp = client.post("/api/predictions", json=_payload())
    rid = resp.json()["id"]
    listing = client.get("/api/predictions").json()
    assert listing["count"] == 1
    row = listing["items"][0]
    assert "grid_response" not in row["baseline"]
    assert "grid_response" not in row["variant"]
    assert row["input_summary"]["variable"]["parameter"] == "emission_rate_g_s"

    detail = client.get(f"/api/predictions/{rid}").json()
    assert "grid_response" in detail["baseline"]
    assert "grid_response" in detail["variant"]
    assert detail["comparison"]["prediction"] == "up"

    assert client.get("/api/predictions/9999").status_code == 404


def test_invalid_parameter_and_prediction_rejected():
    p1 = _payload()
    p1["parameter"] = "stability_class"
    assert client.post("/api/predictions", json=p1).status_code == 422
    p2 = _payload()
    p2["prediction"] = "maybe"
    assert client.post("/api/predictions", json=p2).status_code == 422
