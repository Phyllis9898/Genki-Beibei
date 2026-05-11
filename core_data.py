# ============================================================
#  core_data.py  —  Genki Beibei v2.0
#  ------------------------------------------------------------
#  變更摘要（相對 v1）：
#   1. URL 存檔加入「值域驗證」與「HMAC nonce」（短期防 CSRF）
#   2. Supabase 寫入加入 retry (3 次, exp backoff)，失敗顯式告警
#   3. 新增 compute_user_baseline() — 以前 N 次中位數作為基準
#   4. 新增 compute_relative_change() — 相對基準的百分比變化
#   5. save_full_pipeline_data 欄位對齊新 schema (移除 fast/slow，
#      新增 RT_congruent / RT_incongruent / interference / valid_trials)
# ============================================================

from __future__ import annotations
import os
import time
import json
import math
import hmac
import base64
import hashlib
from datetime import datetime
from typing import Any

import streamlit as st
import pandas as pd

# ------------------------------------------------------------------
#  臨床合理值域 (用於 URL 參數驗證)
# ------------------------------------------------------------------
VALID_RANGES: dict[str, tuple[float, float]] = {
    "sleep_h":         (0.0, 24.0),
    "fatigue":         (1, 10),
    "delta_E":         (0.0, 50.0),        # ΔE × 100 後仍應 ≤ 50
    "rt_mean":         (100.0, 5000.0),    # ms; <100ms 為 false start, >5s 為超時
    "rt_congruent":    (0.0, 5000.0),
    "rt_incongruent":  (0.0, 5000.0),
    "interference":    (-2000.0, 2000.0),
    "lapses":          (0, 1000),
    "false_starts":    (0, 1000),
    "valid_trials":    (0, 5000),
}

# ------------------------------------------------------------------
#  Supabase 延遲初始化 (cached resource)
# ------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_supabase():
    try:
        from supabase import create_client
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None


# ------------------------------------------------------------------
#  營養資料庫
# ------------------------------------------------------------------
def load_nutrition_db() -> dict:
    try:
        with open("nutrition_db.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ------------------------------------------------------------------
#  頁面路由
# ------------------------------------------------------------------
def go_to(page_name: str) -> None:
    st.session_state.page = page_name


# ------------------------------------------------------------------
#  HMAC nonce — 短期 CSRF 防護
# ------------------------------------------------------------------
def _get_hmac_secret() -> str:
    """優先用 st.secrets，否則退回 session 內的隨機字串。"""
    try:
        return st.secrets["HMAC_SECRET"]
    except Exception:
        if "_hmac_secret" not in st.session_state:
            import secrets as _s
            st.session_state._hmac_secret = _s.token_hex(32)
        return st.session_state._hmac_secret


def make_nonce(payload: dict[str, Any]) -> str:
    """
    對 payload 鍵序排序後做 HMAC-SHA256，取前 16 hex chars。
    JS 端在送出 URL 前同步計算同樣的 nonce 即可通過驗證。
    """
    secret = _get_hmac_secret().encode("utf-8")
    items = sorted(payload.items())
    msg = "|".join(f"{k}={v}" for k, v in items).encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:16]


def verify_nonce(payload: dict[str, Any], nonce: str) -> bool:
    try:
        return hmac.compare_digest(make_nonce(payload), nonce)
    except Exception:
        return False


# ------------------------------------------------------------------
#  值域驗證
# ------------------------------------------------------------------
def _coerce_finite(v: Any, lo: float, hi: float, is_int: bool = False) -> float | int | None:
    """轉型 + finite 檢查 + 範圍 clip；不在範圍內就回傳 None 讓上層 reject。"""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    if x < lo or x > hi:
        return None
    return int(round(x)) if is_int else x


def validate_url_payload(raw: dict[str, str]) -> tuple[dict | None, str | None]:
    """
    回傳 (clean_dict, None) 或 (None, error_msg)。
    嚴格驗證每個欄位的型別與值域，任一失敗即整體拒絕。
    """
    int_keys = {"fatigue", "lapses", "false_starts", "valid_trials"}
    needed = ("sleep_h", "fatigue", "delta_E", "rt_mean",
              "rt_congruent", "rt_incongruent", "interference",
              "lapses", "false_starts", "valid_trials")
    out: dict[str, Any] = {}
    for k in needed:
        if k not in raw:
            return None, f"缺少欄位 {k}"
        lo, hi = VALID_RANGES[k]
        v = _coerce_finite(raw[k], lo, hi, is_int=k in int_keys)
        if v is None:
            return None, f"欄位 {k} 數值非法 ({raw[k]!r})"
        out[k] = v
    return out, None


# ------------------------------------------------------------------
#  寫入 Supabase + 本地 CSV  (帶 retry)
# ------------------------------------------------------------------
def save_full_pipeline_data(*,
                            name: str,
                            sleep: float,
                            fatigue: int,
                            delta_e: float,
                            rt_mean: float,
                            rt_congruent: float,
                            rt_incongruent: float,
                            interference: float,
                            lapses: int,
                            false_starts: int,
                            valid_trials: int,
                            delta_e_left: float | None = None,
                            delta_e_right: float | None = None,
                            asymmetry: float | None = None
                            ) -> bool:
    """寫入一筆完整紀錄；雲端寫入失敗時降級至本地 CSV 並回報 False。"""
    data = {
        "User_Name":       str(name)[:64],
        "Date":            datetime.now().strftime("%Y-%m-%d"),
        "Sleep_Hours":     float(sleep),
        "Fatigue_Level":   int(fatigue),
        "Delta_E":         float(delta_e),
        "Delta_E_Left":    float(delta_e_left)  if delta_e_left  is not None else None,
        "Delta_E_Right":   float(delta_e_right) if delta_e_right is not None else None,
        "Asymmetry":       float(asymmetry)     if asymmetry     is not None else None,
        "Mean_RT":         float(rt_mean),
        "RT_Congruent":    float(rt_congruent),
        "RT_Incongruent":  float(rt_incongruent),
        "Interference":    float(interference),
        "Lapses":          int(lapses),
        "False_Starts":    int(false_starts),
        "Valid_Trials":    int(valid_trials),
    }

    sb_ok = False
    sb = get_supabase()
    if sb is not None:
        for attempt in range(3):
            try:
                sb.table("health_logs").insert(data).execute()
                sb_ok = True
                break
            except Exception as e:
                if attempt == 2:
                    st.sidebar.warning(f"⚠️ 雲端備份失敗 (將存本地)：{type(e).__name__}")
                else:
                    time.sleep(0.5 * (2 ** attempt))   # 0.5s, 1.0s

    # 本地 CSV 永遠寫一份做為災難備援
    safe_name = "".join(c for c in str(name) if c.isalnum() or c in ("-", "_"))[:32] or "anon"
    fname = f"health_data_{safe_name}.csv"
    df_new = pd.DataFrame([data])
    if os.path.exists(fname):
        df_new = pd.concat([pd.read_csv(fname), df_new], ignore_index=True)
    df_new.to_csv(fname, index=False)
    return sb_ok


# ------------------------------------------------------------------
#  讀歷史 + 個人化 Baseline
# ------------------------------------------------------------------
def load_user_history(user_name: str) -> pd.DataFrame:
    sb = get_supabase()
    if sb is not None:
        try:
            res = (sb.table("health_logs")
                     .select("*")
                     .eq("User_Name", user_name)
                     .order("Date")
                     .execute())
            if res.data:
                return pd.DataFrame(res.data)
        except Exception:
            pass
    safe_name = "".join(c for c in str(user_name) if c.isalnum() or c in ("-", "_"))[:32] or "anon"
    fname = f"health_data_{safe_name}.csv"
    return pd.read_csv(fname) if os.path.exists(fname) else pd.DataFrame()


def compute_user_baseline(df: pd.DataFrame, n_days: int = 3) -> dict[str, float]:
    """
    用「前 n_days 次的中位數」作為個人基準。
    若紀錄不足 n_days，則用所有可得資料；若完全沒資料回空 dict。
    """
    if df is None or df.empty:
        return {}
    df_sorted = df.sort_values("Date").head(max(n_days, 1))
    out = {}
    for col in ("Delta_E", "Mean_RT", "Lapses", "Interference"):
        if col in df_sorted.columns and df_sorted[col].notna().any():
            out[col] = float(df_sorted[col].median())
    return out


def compute_relative_change(current: float, baseline: float) -> float | None:
    """回傳 (current − baseline) / baseline × 100；baseline ≈ 0 時回 None。"""
    if baseline is None or abs(baseline) < 1e-9:
        return None
    return (current - baseline) / baseline * 100.0


# ------------------------------------------------------------------
#  視覺背景
# ------------------------------------------------------------------
def set_bg_from_local(image_file: str) -> None:
    try:
        with open(image_file, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st.markdown(
            f"""<style>.stApp {{
                background-image: url("data:image/jpeg;base64,{b64}");
                background-size: cover;
            }}</style>""",
            unsafe_allow_html=True,
        )
    except Exception:
        pass
