"""课堂预测练习：先记录方向预测，再用同一物理模型做两次实际计算。

设计约束（对应课程要求）：

* **方向只由实际计算判定**。系统对基准输入与变体输入各做一次
  受体点计算，由总浓度差给出实际方向；不写死任何
  “风速越大必然处处降低”之类的经验规则——例如开启烟气抬升后，
  风速增大压低抬升高度 Δh，近-中场受体浓度可能反而升高；
  源高变化的方向同样以受体实际结果为准。
* **静风变体不可计算**：任一一侧触发静风拦截时，记录保留原预测，
  标记 computable=False，绝不生成虚构浓度。
* 受体用烟羽坐标（下风向/横风向距离）定义，与采样网格无关，
  两次计算在同一物理点上求值。
"""
from __future__ import annotations

import math

import numpy as np

from .gaussian import CalmWindError, compute_plume_field
from .geometry import transport_bearing_deg
from .schemas import (
    MeteorologyInput,
    PredictionExerciseRequest,
    ReceptorSpec,
    SourceInput,
)
from .services import effective_height

#: 可变参数的展示元数据（label/unit 随记录保存，历史题次自描述）
VARIABLE_PARAM_META: dict[str, dict[str, str]] = {
    "stack_height_m": {"label": "烟囱高度 H", "unit": "m", "target": "source"},
    "wind_speed_ms": {"label": "风速 u", "unit": "m/s", "target": "meteorology"},
    "emission_rate_g_s": {"label": "排放率 Q", "unit": "g/s", "target": "source"},
}

DIRECTION_LABELS: dict[str, str] = {
    "increase": "升高",
    "decrease": "降低",
    "unchanged": "基本不变",
}

#: 方向判定容差：|Δtotal| 相对基准总量（至少 1 μg/m³ 尺度）可忽略时判“基本不变”
_DIRECTION_REL_TOL = 1e-9

DIRECTION_NOTE = (
    "实际方向由受体处两次模型计算的总浓度差判定，不查固定口诀；"
    "模型本身不含“风速大必然降低”之类的规则——例如开启烟气抬升时，"
    "风速增大压低抬升高度，部分受体浓度可能升高。"
)


def apply_variant(
    source: SourceInput,
    met: MeteorologyInput,
    param: str,
    value: float,
) -> tuple[SourceInput, MeteorologyInput]:
    """返回只改动一项参数的 (source, met) 副本；原对象不变。"""
    src = source.model_copy(deep=True)
    m = met.model_copy(deep=True)
    if VARIABLE_PARAM_META[param]["target"] == "source":
        setattr(src, param, value)
    else:
        setattr(m, param, value)
    return src, m


def receptor_to_local_east_north(
    receptor: ReceptorSpec, wind_from_deg: float
) -> tuple[float, float]:
    """受体烟羽坐标 -> 局部 E/N（与 services.build_sampling_grid 同一变换）。"""
    theta = math.radians(transport_bearing_deg(wind_from_deg))
    x, y = receptor.downwind_m, receptor.crosswind_m
    east = x * math.sin(theta) + y * math.cos(theta)
    north = x * math.cos(theta) - y * math.sin(theta)
    return east, north


def evaluate_receptor(
    source: SourceInput,
    met: MeteorologyInput,
    receptor: ReceptorSpec,
    *,
    parameterization: str,
    power_law: dict | None,
    use_rise: bool,
    calm_threshold_ms: float,
) -> dict:
    """在固定受体处用现有物理模型求值；静风时抛 CalmWindError。"""
    # 静风预检：与 compute_plume_field 的硬拦截同一阈值语义，
    # 避免在抬升公式中先碰到近零风速除法。
    if met.wind_speed_ms < calm_threshold_ms:
        raise CalmWindError(
            f"风速 {met.wind_speed_ms:.3g} m/s 低于静风阈值 "
            f"{calm_threshold_ms:.3g} m/s：定常高斯烟羽的输运假设失效，"
            "本模型拒绝计算（不使用近零风速除出巨大浓度）。"
        )
    h_eff, rise_detail = effective_height(source, met, use_rise)
    e, n = receptor_to_local_east_north(receptor, met.wind_from_deg)
    result = compute_plume_field(
        emission_rate_g_s=source.emission_rate_g_s,
        wind_speed_ms=met.wind_speed_ms,
        wind_from_deg=met.wind_from_deg,
        stability_class=met.stability_class,
        effective_height_m=h_eff,
        east_m=np.array([[e]]),
        north_m=np.array([[n]]),
        parameterization=parameterization,
        power_law=power_law,
        calm_threshold_ms=calm_threshold_ms,
    )
    plume = float(result["field"][0, 0])
    bg = float(met.background_conc_ug_m3)
    return {
        "stack_height_m": float(source.stack_height_m),
        "wind_speed_ms": float(met.wind_speed_ms),
        "emission_rate_g_s": float(source.emission_rate_g_s),
        "effective_stack_height_m": float(h_eff),
        "plume_rise_delta_h_m": float(rise_detail["delta_h_m"]),
        "concentration": {
            "plume_conc_ug_m3": plume,
            "background_conc_ug_m3": bg,
            "total_conc_ug_m3": plume + bg,
        },
    }


def direction_from_delta(delta: float, reference: float) -> str:
    """由实际差值判定方向；差值相对参考值可忽略时为 unchanged。"""
    tol = _DIRECTION_REL_TOL * max(1.0, abs(reference))
    if delta > tol:
        return "increase"
    if delta < -tol:
        return "decrease"
    return "unchanged"


def run_prediction_exercise(req: PredictionExerciseRequest) -> dict:
    """执行一次预测练习，返回记录（id/created_at 由仓储补全）。"""
    meta = VARIABLE_PARAM_META[req.variable_param]
    base_obj = req.source if meta["target"] == "source" else req.meteorology
    baseline_value = float(getattr(base_obj, req.variable_param))
    var_src, var_met = apply_variant(
        req.source, req.meteorology, req.variable_param, req.variant_value
    )

    common = dict(
        parameterization=req.parameterization,
        power_law=req.power_law,
        use_rise=req.plume_rise.use_plume_rise,
        calm_threshold_ms=req.calm_threshold_ms,
    )

    baseline_result: dict | None = None
    variant_result: dict | None = None
    reasons: list[str] = []
    try:
        baseline_result = evaluate_receptor(
            req.source, req.meteorology, req.receptor, **common
        )
    except CalmWindError as exc:
        reasons.append(f"基准输入不可计算：{exc}")
    try:
        variant_result = evaluate_receptor(var_src, var_met, req.receptor, **common)
    except CalmWindError as exc:
        reasons.append(f"变体不可计算：{exc}")

    computable = baseline_result is not None and variant_result is not None
    delta_plume = delta_total = None
    actual_direction = None
    correct = None
    if computable:
        c0 = baseline_result["concentration"]
        c1 = variant_result["concentration"]
        delta_total = c1["total_conc_ug_m3"] - c0["total_conc_ug_m3"]
        delta_plume = c1["plume_conc_ug_m3"] - c0["plume_conc_ug_m3"]
        actual_direction = direction_from_delta(
            delta_total, c0["total_conc_ug_m3"]
        )
        correct = actual_direction == req.prediction

    input_summary = {
        "source_name": req.source.name,
        "pollutant": req.source.pollutant,
        "stack_height_m": req.source.stack_height_m,
        "emission_rate_g_s": req.source.emission_rate_g_s,
        "wind_from_deg": req.meteorology.wind_from_deg,
        "wind_speed_ms": req.meteorology.wind_speed_ms,
        "stability_class": req.meteorology.stability_class,
        "background_conc_ug_m3": req.meteorology.background_conc_ug_m3,
        "use_plume_rise": req.plume_rise.use_plume_rise,
        "parameterization": req.parameterization,
        "variable_param_label": meta["label"],
        "variable_param_unit": meta["unit"],
        "prediction_label": DIRECTION_LABELS[req.prediction],
    }

    return {
        "variable_param": req.variable_param,
        "baseline_value": baseline_value,
        "variant_value": req.variant_value,
        "receptor": req.receptor.model_dump(),
        "prediction": req.prediction,
        "input_summary": input_summary,
        "computable": computable,
        "not_computable_reason": None if computable else "；".join(reasons),
        "baseline_result": baseline_result,
        "variant_result": variant_result,
        "delta_plume_ug_m3": delta_plume,
        "delta_total_ug_m3": delta_total,
        "actual_direction": actual_direction,
        "correct": correct,
        "direction_note": DIRECTION_NOTE,
    }
