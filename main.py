# ============================================================
#  main.py  —  Genki Beibei v2.0  (Cloud Edition)
#  ------------------------------------------------------------
#  變更摘要（相對 v1）：
#   1. URL 存檔攔截改用 validate_url_payload + verify_nonce
#   2. 每個欄位都做 finite check + 臨床值域 clip
#   3. 缺少 nonce 或 nonce 不符時，視為「篡改」靜默拒收並寫 sidebar warning
#   4. 移除對已不存在欄位 fast/slow 的引用
# ============================================================
import streamlit as st

st.set_page_config(page_title="元氣貝貝 Genki Beibei",
                   layout="wide",
                   page_icon="🌱")

import urllib.parse  # noqa: E402

from core_data import (   # noqa: E402
    set_bg_from_local,
    save_full_pipeline_data,
    validate_url_payload,
    verify_nonce,
)
from ui_pages import (    # noqa: E402
    show_landing,
    show_profile,
    show_home,
    show_analyzer,
    show_pvt_game,
    show_dashboard,
)

# ----------------- 背景與 Session State -----------------
set_bg_from_local("bg.png")

_defaults = {
    "page": "landing",
    "user_name": "",
    "user_age": 22,
    "user_job": "學生",
    "temp_analysis_data": None,
    "test_mode": "pvt",        # "pvt" or "stroop"
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ==========================================================
#  URL 攔截器 — 防彈存檔 API
# ==========================================================
try:
    qp = st.query_params
    has_save = "save" in qp
except AttributeError:
    qp = st.experimental_get_query_params()
    has_save = "save" in qp


def _qp_val(k: str) -> str | None:
    """Streamlit 新舊 API 都會回傳 str；experimental 版回 list[str]。"""
    v = qp.get(k)
    if v is None:
        return None
    if isinstance(v, list):
        return v[0] if v else None
    return v


if has_save:
    raw_user = _qp_val("u") or ""
    user = urllib.parse.unquote(raw_user)[:64]

    raw_payload = {
        "sleep_h":        _qp_val("sl"),
        "fatigue":        _qp_val("fa"),
        "delta_E":        _qp_val("de"),
        "rt_mean":        _qp_val("rt"),
        "rt_congruent":   _qp_val("rc"),
        "rt_incongruent": _qp_val("ri"),
        "interference":   _qp_val("it"),
        "lapses":         _qp_val("la"),
        "false_starts":   _qp_val("fs"),
        "valid_trials":   _qp_val("vt"),
    }
    nonce = _qp_val("nc") or ""

    clean, err = validate_url_payload(raw_payload)
    if err is not None or not user:
        st.sidebar.error(f"🚫 存檔被拒絕：{err or '使用者名稱缺失'}")
    else:
        # nonce 驗證：
        # 我們只簽證「前置量 + 用戶名」(sleep_h / fatigue / delta_E / u)，
        # 因為 RT、lapse 等屬於測驗結果，本來就由 JS 端產生、無法預先簽署；
        # 但 RT 等已通過 validate_url_payload 的範圍/finite 檢查，安全性已足夠。
        verify_dict = {
            "u":       user,
            "sleep_h": clean["sleep_h"],
            "fatigue": clean["fatigue"],
            "delta_E": clean["delta_E"],
        }
        if not verify_nonce(verify_dict, nonce):
            st.sidebar.error("🚫 存檔被拒絕：完整性檢查 (HMAC) 失敗。")
        else:
            extra = st.session_state.get("temp_analysis_data") or {}
            ok = save_full_pipeline_data(
                name=user,
                sleep=clean["sleep_h"],
                fatigue=clean["fatigue"],
                delta_e=clean["delta_E"],
                rt_mean=clean["rt_mean"],
                rt_congruent=clean["rt_congruent"],
                rt_incongruent=clean["rt_incongruent"],
                interference=clean["interference"],
                lapses=clean["lapses"],
                false_starts=clean["false_starts"],
                valid_trials=clean["valid_trials"],
                delta_e_left=extra.get("delta_E_left"),
                delta_e_right=extra.get("delta_E_right"),
                asymmetry=extra.get("asymmetry"),
            )
            if ok:
                st.sidebar.success("✅ 已成功寫入雲端與本地。")
            else:
                st.sidebar.info("ℹ️ 已寫入本地 CSV (雲端未連通)。")

            st.session_state.user_name = user
            st.session_state.temp_analysis_data = None
            st.session_state.page = "dashboard"

    # 不論成功失敗都清掉 query string，避免重新整理重複存檔
    try:
        st.query_params.clear()
    except AttributeError:
        st.experimental_set_query_params()
    st.rerun()


# ==========================================================
#  路由控制器
# ==========================================================
ROUTES = {
    "landing":  show_landing,
    "profile":  show_profile,
    "home":     show_home,
    "analyzer": show_analyzer,
    "pvt_game": show_pvt_game,
    "dashboard": show_dashboard,
}

view = ROUTES.get(st.session_state.page, show_landing)
view()
