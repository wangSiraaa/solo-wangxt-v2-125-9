"""课堂预测练习的验收测试。

覆盖三条验收约束：
1. 排放率翻倍的方向可按解析结果核对（高斯式对 Q 线性 → 受体浓度恰翻倍）。
2. 改变源高时以受体实际结果判定方向，而非固定口诀
   （同一源高变化，在不同受体上给出“降低”与“基本不变”两种判定）。
3. 静风变体显示不可计算、保留原预测记录、不生成虚构浓度。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _payload(**over):
    """基准输入：H=60 m, Q=50 g/s, u=4 m/s, D 类，西风（烟羽向东）。"""
    payload = {
        "source": {
            "name": "练习源", "lon": 116.40, "lat": 39.90,
            "stack_height_m": 60.0, "emission_rate_g_s": 50.0,
            "stack_diameter_m": 4.0, "exit_velocity_ms": 18.0,
            "stack_temp_k": 410.0, "pollutant": "SO2",
        },
        "meteorology": {
            "name": "练习气象", "wind_from_deg": 270.0,
            "wind_speed_ms": 4.0, "stability_class": "D",
            "ambient_temp_k": 293.15, "pressure_hpa": 1013.0,
            "background_conc_ug_m3": 10.0,
        },
        "receptor": {"downwind_m": 1500.0, "crosswind_m": 0.0},
        "variable_param": "emission_rate_g_s",
        "variant_value": 100.0,
        "prediction": "increase",
    }
    for key, val in over.items():
        if isinstance(val, dict) and isinstance(payload.get(key), dict):
            payload[key] = {**payload[key], **val}
        else:
            payload[key] = val
    return payload


def test_emission_doubling_direction_matches_analytic():
    """验收 1：Q 翻倍 → 高斯式对 Q 线性，受体烟羽浓度恰翻倍，
    Δtotal 必等于基准烟羽值；方向判定必须为 increase。"""
    resp = client.post("/api/predictions", json=_payload())
    assert resp.status_code == 201, resp.text
    rec = resp.json()
    assert rec["computable"] is True
    c0 = rec["baseline_result"]["concentration"]
    c1 = rec["variant_result"]["concentration"]
    # 解析结论：plume 严格翻倍（与 /api/checks 的排放率线性用例同一性质）
    assert c1["plume_conc_ug_m3"] == pytest.approx(
        2.0 * c0["plume_conc_ug_m3"], rel=1e-12
    )
    assert rec["delta_total_ug_m3"] == pytest.approx(
        c0["plume_conc_ug_m3"], rel=1e-12
    )
    assert rec["actual_direction"] == "increase"
    assert rec["correct"] is True
    # 背景不变：两侧背景相同，总量差全部来自烟羽
    assert c0["background_conc_ug_m3"] == c1["background_conc_ug_m3"]
    assert rec["delta_plume_ug_m3"] == pytest.approx(
        rec["delta_total_ug_m3"], rel=1e-12
    )


def test_emission_wrong_prediction_kept_and_marked():
    """学生猜错也要如实记录：预测保留、correct=False。"""
    resp = client.post("/api/predictions", json=_payload(prediction="decrease"))
    assert resp.status_code == 201
    rec = resp.json()
    assert rec["prediction"] == "decrease"
    assert rec["actual_direction"] == "increase"
    assert rec["correct"] is False


def test_source_height_direction_from_actual_receptor_result():
    """验收 2：源高 60→120 m，方向由受体实算结果判定。

    * 受体 x=1000 m（烟羽已触地区）：实算为降低；
    * 受体 x=500 m, y=4000 m（远偏轴，烟羽贡献为零）：实算为基本不变。
    同一参数变化在不同受体上判定不同，证明不是查固定口诀。
    """
    rec1 = client.post(
        "/api/predictions",
        json=_payload(
            variable_param="stack_height_m",
            variant_value=120.0,
            receptor={"downwind_m": 1000.0, "crosswind_m": 0.0},
            prediction="decrease",
        ),
    ).json()
    assert rec1["computable"] is True
    c0 = rec1["baseline_result"]["concentration"]["total_conc_ug_m3"]
    c1 = rec1["variant_result"]["concentration"]["total_conc_ug_m3"]
    assert c1 < c0  # 该受体实算确实降低
    assert rec1["actual_direction"] == "decrease"
    assert rec1["correct"] is True

    rec2 = client.post(
        "/api/predictions",
        json=_payload(
            variable_param="stack_height_m",
            variant_value=120.0,
            receptor={"downwind_m": 500.0, "crosswind_m": 4000.0},
            prediction="decrease",
        ),
    ).json()
    assert rec2["computable"] is True
    p0 = rec2["baseline_result"]["concentration"]["plume_conc_ug_m3"]
    p1 = rec2["variant_result"]["concentration"]["plume_conc_ug_m3"]
    assert p0 == 0.0 and p1 == 0.0  # 烟羽未到该受体，实算为基本不变
    assert rec2["actual_direction"] == "unchanged"
    assert rec2["correct"] is False  # 口诀“必降”在该受体上不成立


def test_wind_speed_with_plume_rise_can_increase():
    """反例守卫：开启抬升后风速 3→9 m/s，Δh∝1/u 压低有效源高，
    x=2000 m 受体实算浓度升高——系统不得写死“风大必降”。"""
    payload = _payload(
        variable_param="wind_speed_ms",
        variant_value=9.0,
        prediction="increase",
        receptor={"downwind_m": 2000.0, "crosswind_m": 0.0},
        plume_rise={"use_plume_rise": True},
    )
    payload["source"]["stack_height_m"] = 120.0
    payload["meteorology"]["wind_speed_ms"] = 3.0
    rec = client.post("/api/predictions", json=payload).json()
    assert rec["computable"] is True
    # 有效源高随风速增大而降低（抬升被压低）
    he0 = rec["baseline_result"]["effective_stack_height_m"]
    he1 = rec["variant_result"]["effective_stack_height_m"]
    assert he1 < he0
    c0 = rec["baseline_result"]["concentration"]["total_conc_ug_m3"]
    c1 = rec["variant_result"]["concentration"]["total_conc_ug_m3"]
    assert c1 > c0
    assert rec["actual_direction"] == "increase"
    assert rec["correct"] is True


def test_calm_variant_not_computable_but_prediction_kept():
    """验收 3：变体风速 0.3 m/s（< 阈值）→ 不可计算；
    记录保留原预测，不生成任何虚构浓度。"""
    resp = client.post(
        "/api/predictions",
        json=_payload(
            variable_param="wind_speed_ms",
            variant_value=0.3,
            prediction="decrease",
        ),
    )
    assert resp.status_code == 201, resp.text
    rec = resp.json()
    assert rec["computable"] is False
    assert rec["prediction"] == "decrease"  # 原预测保留
    assert rec["variant_result"] is None  # 静风变体：无浓度
    assert rec["baseline_result"] is not None  # 基准为真实计算结果
    assert rec["actual_direction"] is None
    assert rec["correct"] is None
    assert rec["delta_total_ug_m3"] is None
    assert "静风" in rec["not_computable_reason"]
    # 历史题次中可复看，且仍无浓度
    got = client.get(f"/api/predictions/{rec['id']}")
    assert got.status_code == 200
    assert got.json()["variant_result"] is None
    assert got.json()["prediction"] == "decrease"


def test_history_list_and_get():
    """题次保存与复看：列表最新在前，单条可查，缺失 404。"""
    r1 = client.post("/api/predictions", json=_payload()).json()
    r2 = client.post(
        "/api/predictions",
        json=_payload(variable_param="stack_height_m", variant_value=90.0),
    ).json()
    listing = client.get("/api/predictions").json()
    ids = [r["id"] for r in listing]
    assert r2["id"] in ids and r1["id"] in ids
    assert ids.index(r2["id"]) < ids.index(r1["id"])  # 最新在前
    # 输入摘要与结果随记录保存
    item = client.get(f"/api/predictions/{r2['id']}").json()
    assert item["input_summary"]["source_name"] == "练习源"
    assert item["input_summary"]["variable_param_label"] == "烟囱高度 H"
    assert item["baseline_value"] == 60.0
    assert item["variant_value"] == 90.0
    assert item["receptor"]["downwind_m"] == 1500.0
    assert client.get("/api/predictions/999999").status_code == 404


def test_validation_rejects_bad_exercise():
    # 负的可变参数值
    resp = client.post("/api/predictions", json=_payload(variant_value=-5.0))
    assert resp.status_code == 422
    # 非法参数名
    resp = client.post("/api/predictions", json=_payload(variable_param="nx"))
    assert resp.status_code == 422
    # 受体必须位于下风向
    resp = client.post(
        "/api/predictions",
        json=_payload(receptor={"downwind_m": 0.0, "crosswind_m": 0.0}),
    )
    assert resp.status_code == 422
    # 非法预测方向
    resp = client.post("/api/predictions", json=_payload(prediction="maybe"))
    assert resp.status_code == 422
