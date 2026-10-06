"""课堂预测练习服务。

流程（严格“先预测、后看结果”）：
1. 教师选定**固定受体**（经纬度）、**基准输入**（源/气象/网格/参数化）
   与**一项**可变参数（烟囱高 stack_height_m / 风速 wind_speed_ms /
   排放率 emission_rate_g_s）及其变体取值；
2. 学生只看到输入摘要，提交方向预测（升高 up / 降低 down / 基本不变 same）；
3. 服务用**现有物理模型**分别独立计算两次：
   * 基准计算：run_grid + run_points（受体点）；
   * 变体计算：run_grid + run_points（受体点，同一受体位置）。
   方向完全由受体处两次实际浓度的数值比较得出，服务端不内置任何
   “烟囱越高越低”“风速越大越低”之类的经验口诀——这两类结论都只在
   特定前提下成立（例如开启 Holland 抬升时增大 u 会压低 Δh，
   近源受体浓度反而可能升高）。
4. 静风变体（或基准）不执行计算：保留题次与学生原预测，
   变体结果显式标记 computable=False/calm_wind=True，**不填零、
   不生成任何虚假浓度场**。

题次保存在进程内仓储（与本应用“无数据库也可完全离线运行”的约定一致），
前端同时把题次镜像到 localStorage，支持复看历史题次。
"""
from __future__ import annotations

from typing import Literal

from .gaussian import CalmWindError, PlumeInputError
from .repository import get_prediction_store
from .schemas import PlumeGridRequest
from .services import run_grid, run_points

# 可变参数 -> （中文短名, 单位）；键即请求中的 parameter 字段
VARIABLE_META: dict[str, dict[str, str]] = {
    "stack_height_m": {"label": "烟囱几何高度 H", "unit": "m"},
    "wind_speed_ms": {"label": "风速 u", "unit": "m/s"},
    "emission_rate_g_s": {"label": "排放率 Q", "unit": "g/s"},
}

Direction = Literal["up", "down", "same"]

# 方向判定容差：|ΔC| 大于 max(相对容差·C_基准, 绝对容差) 才算升高/降低
REL_TOL = 1e-9
ABS_TOL_UG_M3 = 1e-9

# 进程内/PostGIS 题次仓储由 repository 统一提供（无数据库时内存回退）；
# FIFO 上限防止离线课堂长跑无限增长。
_MAX_RECORDS = 500


def store_add(record: dict) -> dict:
    return get_prediction_store().add(record)


def store_list() -> list[dict]:
    return get_prediction_store().list()


def store_get(record_id: int) -> dict | None:
    return get_prediction_store().get(record_id)


def store_summarized_list() -> list[dict]:
    """列表视图：剔除两场完整网格矩阵，保留受体结果/差值/输入摘要。"""
    return [summarize(r) for r in store_list()]


def store_count() -> int:
    return get_prediction_store().count()


def store_clear() -> None:
    """仅供测试使用。"""
    get_prediction_store().clear()


class _StoreAdapter:
    """仓储薄封装，供测试/内部以 store.add/list/get 方式调用。"""

    @staticmethod
    def add(record: dict) -> dict:
        return store_add(record)

    @staticmethod
    def list() -> list[dict]:
        return store_summarized_list()

    @staticmethod
    def get(record_id: int) -> dict | None:
        return store_get(record_id)

    @staticmethod
    def count() -> int:
        return store_count()

    @staticmethod
    def clear() -> None:
        store_clear()


store = _StoreAdapter()


def _direction(c_base: float, c_variant: float) -> Direction:
    """实际方向：仅由两个数值决定，不含任何经验规则。"""
    delta = c_variant - c_base
    if abs(delta) > max(REL_TOL * max(abs(c_base), abs(c_variant)), ABS_TOL_UG_M3):
        return "up" if delta > 0 else "down"
    return "same"


def summarize(record: dict) -> dict:
    """列表视图：剔除两场完整网格矩阵，保留受体结果/差值/输入摘要。"""
    out = dict(record)
    for key in ("baseline", "variant"):
        run = out.get(key)
        if isinstance(run, dict):
            run = {k: v for k, v in run.items() if k != "grid_response"}
            out[key] = run
    return out


def _apply_variable(req: PlumeGridRequest, parameter: str, value: float) -> None:
    """在请求副本上设置唯一一项可变参数（直接落在源/气象输入对象上，
    不使用 override 通道，保证两次计算的输入完全显式）。"""
    if parameter == "stack_height_m":
        req.source.stack_height_m = value
    elif parameter == "wind_speed_ms":
        req.meteorology.wind_speed_ms = value
    elif parameter == "emission_rate_g_s":
        req.source.emission_rate_g_s = value
    # 其余参数名已在 Pydantic 模型层拦截


def _receptor_result(req: PlumeGridRequest, lon: float, lat: float) -> dict:
    """固定受体点求值（与网格无关的同一份物理模型）。"""
    point_req = req.model_copy(deep=True)
    points = run_points(point_req.model_copy(update={"points": [(lon, lat)]}))
    return points[0]


def _compute_run(req: PlumeGridRequest, receptor_lon: float, receptor_lat: float) -> dict:
    """一次完整计算：受体点 + 网格场；静风/非法输入向上抛，由调用方处理。"""
    receptor = _receptor_result(req, receptor_lon, receptor_lat)
    grid_resp = run_grid(req.model_copy(deep=True))
    return {
        "computable": True,
        "receptor": {
            "plume_conc_ug_m3": receptor["plume_conc_ug_m3"],
            "background_conc_ug_m3": receptor["background_conc_ug_m3"],
            "total_conc_ug_m3": receptor["total_conc_ug_m3"],
            "downwind_crosswind_m": receptor["downwind_crosswind_m"],
            "east_north_m": receptor["east_north_m"],
        },
        # 供前端展示两次烟羽/背景/总量场及对比
        "grid_response": grid_resp,
        "effective_stack_height_m": grid_resp["effective_stack_height_m"],
        "plume_rise_delta_h_m": grid_resp["plume_rise_delta_h_m"],
    }


def _calm_run(exc: CalmWindError, threshold_ms: float, wind_speed_ms: float) -> dict:
    """不可计算变体：结构中**没有任何浓度字段/网格字段**。"""
    return {
        "computable": False,
        "reason": "calm_wind",
        "calm": True,
        "wind_speed_ms": wind_speed_ms,
        "calm_threshold_ms": threshold_ms,
        "message": str(exc),
        "action": "静风条件下定常烟羽模型不适用；不执行除法、不输出浓度。",
    }


def _input_summary(req: PlumeGridRequest, parameter: str,
                   base_value: float, variant_value: float,
                   receptor_lon: float, receptor_lat: float) -> dict:
    return {
        "source": {
            "name": req.source.name,
            "pollutant": req.source.pollutant,
            "lonlat": [req.source.lon, req.source.lat],
            "stack_height_m": req.source.stack_height_m,
            "emission_rate_g_s": req.source.emission_rate_g_s,
            "stack_diameter_m": req.source.stack_diameter_m,
            "exit_velocity_ms": req.source.exit_velocity_ms,
            "stack_temp_k": req.source.stack_temp_k,
        },
        "meteorology": {
            "wind_from_deg": req.meteorology.wind_from_deg,
            "wind_speed_ms": req.meteorology.wind_speed_ms,
            "stability_class": req.meteorology.stability_class,
            "ambient_temp_k": req.meteorology.ambient_temp_k,
            "pressure_hpa": req.meteorology.pressure_hpa,
            "background_conc_ug_m3": req.meteorology.background_conc_ug_m3,
        },
        "plume_rise_enabled": req.plume_rise.use_plume_rise,
        "parameterization": req.parameterization,
        "power_law": req.power_law,
        "calm_threshold_ms": req.calm_threshold_ms,
        "receptor_lonlat": [receptor_lon, receptor_lat],
        "variable": {
            "parameter": parameter,
            "label": VARIABLE_META[parameter]["label"],
            "unit": VARIABLE_META[parameter]["unit"],
            "baseline_value": base_value,
            "variant_value": variant_value,
        },
    }


def submit_prediction(payload: dict) -> dict:
    """提交一次课堂预测并执行两次计算。

    payload 为已通过 PredictionExerciseRequest 校验的 dict。
    """
    from .schemas import PredictionExerciseRequest

    req_model = PredictionExerciseRequest.model_validate(payload)
    parameter = req_model.parameter
    base_req = req_model.base_request

    base_value = _read_variable(base_req, parameter)
    variant_value = req_model.variant_value

    receptor_lon, receptor_lat = req_model.receptor_lonlat
    summary = _input_summary(
        base_req, parameter, base_value, variant_value,
        receptor_lon, receptor_lat,
    )

    # ---- 基准计算：必须可计算；静风/非法输入直接拒绝（题目本身不成立）----
    baseline_run = _compute_run(base_req, receptor_lon, receptor_lat)

    # ---- 变体：复制基准请求，只改一项参数，独立再算一次 ----
    variant_req = base_req.model_copy(deep=True)
    _apply_variable(variant_req, parameter, variant_value)
    try:
        variant_run = _compute_run(variant_req, receptor_lon, receptor_lat)
    except CalmWindError as exc:
        # 静风变体：保留题次与原预测，绝不产出虚假浓度
        variant_run = _calm_run(exc, variant_req.calm_threshold_ms,
                                variant_req.meteorology.wind_speed_ms)

    # ---- 方向判定：仅比较受体处实际浓度 ----
    c_b_total = baseline_run["receptor"]["total_conc_ug_m3"]
    c_b_plume = baseline_run["receptor"]["plume_conc_ug_m3"]
    if variant_run["computable"]:
        c_v_total = variant_run["receptor"]["total_conc_ug_m3"]
        c_v_plume = variant_run["receptor"]["plume_conc_ug_m3"]
        actual_direction = _direction(c_b_total, c_v_total)
        plume_direction = _direction(c_b_plume, c_v_plume)
        delta = {
            "plume_conc_ug_m3": c_v_plume - c_b_plume,
            "background_conc_ug_m3": (
                variant_run["receptor"]["background_conc_ug_m3"]
                - baseline_run["receptor"]["background_conc_ug_m3"]
            ),
            "total_conc_ug_m3": c_v_total - c_b_total,
        }
        prediction_correct = req_model.prediction == actual_direction
        comparison = {
            "computable": True,
            "tolerance": {"relative": REL_TOL, "absolute_ug_m3": ABS_TOL_UG_M3},
            "judged_on": (
                "受体处总浓度 total = plume + background 的两次实际值；"
                "未使用任何方向经验口诀"
            ),
            "actual_direction": actual_direction,
            "actual_plume_direction": plume_direction,
            "prediction": req_model.prediction,
            "prediction_correct": prediction_correct,
            "delta": delta,
        }
    else:
        comparison = {
            "computable": False,
            "judged_on": "变体静风不可计算，不判定方向、不生成浓度",
            "actual_direction": None,
            "prediction": req_model.prediction,
            "prediction_correct": None,
            "delta": None,
        }

    record = {
        "created_at": _now_iso(),
        "label": req_model.label,
        "input_summary": summary,
        "prediction": req_model.prediction,
        "baseline": baseline_run,
        "variant": variant_run,
        "comparison": comparison,
    }
    return store_add(record)


def _read_variable(req: PlumeGridRequest, parameter: str) -> float:
    if parameter == "stack_height_m":
        return req.source.stack_height_m
    if parameter == "wind_speed_ms":
        return req.meteorology.wind_speed_ms
    if parameter == "emission_rate_g_s":
        return req.source.emission_rate_g_s
    raise PlumeInputError(f"未知可变参数: {parameter}")


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
