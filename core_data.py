# ============================================================
#  core_data.py  —  Genki Beibei v2.3 (Security Hardening & Modern UI Edition)
# ============================================================
import streamlit as st
import pandas as pd
import os
import json
import base64
import hmac
import hashlib
import secrets
from datetime import datetime

import bcrypt

# -------- 1. Supabase 連線層 --------
@st.cache_resource
def get_supabase():
    """初始化並快取 Supabase 連線用戶端"""
    try:
        from supabase import create_client
        if "SUPABASE_URL" in st.secrets and "SUPABASE_KEY" in st.secrets:
            return create_client(
                st.secrets["SUPABASE_URL"],
                st.secrets["SUPABASE_KEY"],
            )
    except Exception:
        return None
    return None


def load_nutrition_db():
    """載入本地飲食營養學建議知識庫（若檔案缺失則回傳空 dict，不阻斷主程式）"""
    try:
        with open("nutrition_db.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def go_to(page_name: str):
    """Streamlit 多頁面集中式路由控制器"""
    st.session_state.page = page_name
    st.rerun()


# -------- 2. 安全：HMAC 密鑰 --------
def get_hmac_secret() -> bytes:
    """取得 URL 簽章用的 HMAC 密鑰。本地端 fallback 僅供開發，正式環境必須設定 Secrets。"""
    if "HMAC_SECRET" in st.secrets:
        return st.secrets["HMAC_SECRET"].encode()
    return b"fallback_local_secret_matrix_key_2026_xyz"


# -------- 3. 安全：Nonce 簽章與驗證 --------
def make_nonce(payload: dict) -> str:
    """
    根據當前受試者狀態資訊（不含波動的測驗分數結果），
    生成具備單向雜湊特徵的 HMAC-SHA256 安全防偽 Nonce。
    """
    secret = get_hmac_secret()
    username = str(payload.get("u", ""))
    sleep_h = float(payload.get("sleep_h", 0.0))
    fatigue = int(payload.get("fatigue", 0))
    delta_E = float(payload.get("delta_E", 0.0))

    message = f"{username}-{sleep_h:.2f}-{fatigue}-{delta_E:.2f}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_nonce(verify_dict: dict, nonce: str) -> bool:
    """驗證前端 JavaScript 傳回的 URL 簽章是否遭到未授權篡改"""
    if not nonce:
        return False
    expected = make_nonce(verify_dict)
    return hmac.compare_digest(expected, nonce)


# -------- 4. 安全：URL 參數校驗與邊界檢查 --------
def validate_url_payload(raw_payload: dict) -> tuple[dict, str | None]:
    """
    對前端傳入的所有數值欄位執行防彈校驗與有限性檢查 (Finite Check)，
    排除 NaN、Inf 與極端惡意數值的注入攻擊。
    """
    clean = {}
    valid_ranges = {
        "sleep_h": (0.0, 24.0),
        "fatigue": (1, 10),
        "delta_E": (0.0, 100.0),
        "rt_mean": (100.0, 5000.0),
        "rt_congruent": (100.0, 5000.0),
        "rt_incongruent": (100.0, 5000.0),
        "interference": (-2000.0, 2000.0),
        "lapses": (0, 1000),
        "false_starts": (0, 1000),
        "valid_trials": (0, 5000),
    }

    try:
        for k, range_bound in valid_ranges.items():
            val = raw_payload.get(k)
            if val is None:
                return {}, f"參數缺失: {k}"

            # 轉換為 float 進行統一數值邊界檢查
            f_val = float(val)
            if not math.isfinite(f_val):
                return {}, f"檢測到非有限數值破壞意圖: {k}"

            # 進行極值鉗制 (Clip) 保護資料庫
            clamped = max(range_bound[0], min(f_val, range_bound[1]))

            # 還原為整數或浮點數原始格式
            clean[k] = int(clamped) if isinstance(range_bound[0], int) else clamped
        return clean, None
    except (ValueError, TypeError) as e:
        return {}, f"資料型態解析異常: {str(e)}"


# -------- 5. 安全：Bcrypt 密碼與註冊系統 --------
def register_user(username, password) -> tuple[bool, str]:
    """使用國際學術級 Bcrypt 雜湊演算法於 Supabase 隔離註冊新受試者帳號"""
    sb = get_supabase()
    if not sb:
        return False, "雲端資料庫連線中斷，請確認 Streamlit Secrets 配置。"

    clean_user = "".join(c for c in str(username).strip() if c.isalnum() or c in ("-", "_"))[:32]
    if not clean_user:
        return False, "註冊暱稱包含非法字元或長度不符。"

    if len(password) < 4:
        return False, "安全驗證密碼長度不可少於 4 個字元。"

    try:
        # 檢查該受試者代號是否已被佔用
        res = sb.table("users").select("username").eq("username", clean_user).execute()
        if res.data:
            return False, "此受試者代號已被註冊，請直接使用登入功能或更換代號。"

        # Bcrypt 自動處理高強度 Salt 鹽值與工作因子
        pwd_bytes = password.encode("utf-8")
        pw_hash = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=10)).decode("utf-8")

        sb.table("users").insert({
            "username": clean_user,
            "password_hash": pw_hash
        }).execute()

        return True, "註冊成功"
    except Exception as e:
        return False, f"資料庫寫入異常: {str(e)}"


def login_user(username, password) -> tuple[bool, str]:
    """安全驗證受試者身分登入態"""
    sb = get_supabase()
    if not sb:
        return False, "雲端資料庫連線中斷，請確認 Streamlit Secrets 配置。"

    clean_user = "".join(c for c in str(username).strip() if c.isalnum() or c in ("-", "_"))[:32]
    try:
        res = sb.table("users").select("*").eq("username", clean_user).execute()
        if not res.data:
            return False, "找不到此受試者代號，請先進行註冊。"

        record = res.data[0]
        stored_hash = record["password_hash"]

        # 校驗密碼雜湊特徵
        if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
            return True, "登入驗證通過"
        return False, "密碼不正確，請重新輸入。"
    except Exception as e:
        return False, f"身分鑑權異常: {str(e)}"


# -------- 6. 資料流：整合數據雲端同步同步器 --------
def save_full_pipeline_data(
    name, sleep, fatigue, delta_e, rt_mean=0, rt_congruent=0,
    rt_incongruent=0, interference=0, lapses=0, false_starts=0,
    valid_trials=0, delta_e_left=None, delta_e_right=None, asymmetry=None,
) -> bool:
    """整合生理與雙模式認知數據，完整寫入雲端資料庫並備份至本地 CSV。"""
    sb = get_supabase()

    data = {
        "User_Name": str(name),
        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Sleep_Hours": float(sleep),
        "Fatigue_Level": int(fatigue),
        "Delta_E": float(delta_e),
        "Delta_E_Left": float(delta_e_left) if delta_e_left is not None else 0.0,
        "Delta_E_Right": float(delta_e_right) if delta_e_right is not None else 0.0,
        "Asymmetry": float(asymmetry) if asymmetry_index is not None else 0.0,
        "Mean_RT": float(rt_mean),
        "RT_Congruent": float(rt_congruent),
        "RT_Incongruent": float(rt_incongruent),
        "Interference": float(interference),
        "Lapses": int(lapses),
        "False_Starts": int(false_starts),
        "Valid_Trials": int(valid_trials),
    }

    # 1. 寫入雲端資料庫 Supabase
    supabase_ok = False
    if sb:
        try:
            sb.table("health_logs").insert(data).execute()
            supabase_ok = True
        except Exception:
            pass

    # 2. 寫入本地 CSV 作為底層防護備份
    try:
        safe_name = "".join(c for c in str(name) if c.isalnum() or c in ("-", "_"))[:32] or "anon"
        fname = f"health_data_{safe_name}.csv"
        df_new = pd.DataFrame([data])
        if os.path.exists(fname):
            df_old = pd.read_csv(fname)
            pd.concat([df_old, df_new], ignore_index=True).to_csv(fname, index=False)
        else:
            df_new.to_csv(fname, index=False)
    except Exception:
        pass

    return supabase_ok


# -------- 7. 資料流：歷史追蹤數據載入器 --------
def load_user_history(user_name: str) -> pd.DataFrame:
    """優先自雲端獲取完整的縱向歷史紀錄，雲端斷線時自動從本地降級加載。"""
    sb = get_supabase()
    clean_user = "".join(c for c in str(user_name) if c.isalnum() or c in ("-", "_"))[:32]

    if sb:
        try:
            res = sb.table("health_logs").select("*").eq("User_Name", clean_user).order("Date").execute()
            if res.data:
                return pd.DataFrame(res.data)
        except Exception:
            pass

    safe_name = "".join(c for c in str(user_name) if c.isalnum() or c in ("-", "_"))[:32] or "anon"
    fname = f"health_data_{safe_name}.csv"
    return pd.read_csv(fname) if os.path.exists(fname) else pd.DataFrame()


# -------- 8. 臨床分析：基準線與相對位移量計算 --------
def compute_user_baseline(df: pd.DataFrame, n_days: int = 3) -> dict[str, float]:
    """用受試者『前 n_days 次的中位數』作為穩健的個人生理與認知平衡基準線 (Baseline)。"""
    if df is None or df.empty:
        return {}
    df_sorted = df.sort_values("Date").head(max(n_days, 1))
    out = {}
    for col in ("Delta_E", "Mean_RT", "Lapses", "Interference"):
        if col in df_sorted.columns and df_sorted[col].notna().any():
            out[col] = float(df_sorted[col].median())
    return out


def compute_relative_change(current: float, baseline: float) -> float | None:
    """計算最新單次數據相對於個人基準線的百分比偏差位移量。"""
    if baseline is None or abs(baseline) < 1e-9:
        return None
    return (current - baseline) / baseline * 100.0


# ------------------------------------------------------------------
#  9. 視覺：高端全局毛玻璃卡片模塊化 CSS 注入器（UI 優化核心）
# ------------------------------------------------------------------
def set_bg_from_local(image_file: str):
    """
    高度硬化的 CSS 全局注入：為表單、數據指標、輸入框與上傳區
    全面套用高對比深色毛玻璃模塊背景，徹底根除草地背景導致的字體吃字與不易辨識問題。
    """
    try:
        if not os.path.exists(image_file):
            return
        with open(image_file, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        ext = os.path.splitext(image_file)[1].lower().lstrip(".")
        mime = "png" if ext == "png" else "jpeg"

        st.markdown(
            f"""
        <style>
        /* 1. 設定背景圖與基礎暗色濾鏡 */
        .stApp {{
            background-image: url("data:image/{mime};base64,{b64}");
            background-size: cover;
            background-attachment: fixed;
            background-position: center;
        }}
        [data-testid="stAppViewContainer"] > .main {{
            background-color: rgba(10, 10, 10, 0.78) !important;
        }}
        
        /* 2. 所有主要表單 (st.form) 模塊化卡片化設計 */
        [data-testid="stForm"] {{
            background-color: rgba(22, 22, 22, 0.92) !important;
            border: 1px solid rgba(255, 255, 255, 0.16) !important;
            border-radius: 16px !important;
            padding: 28px !important;
            backdrop-filter: blur(12px) !important;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6) !important;
        }}
        
        /* 3. 數據儀表板統計指標 (st.metric) 模塊卡片化 */
        [data-testid="stMetric"] {{
            background-color: rgba(30, 30, 30, 0.94) !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            border-radius: 12px !important;
            padding: 16px !important;
            backdrop-filter: blur(8px) !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4) !important;
        }}
        
        /* 4. 強化所有文字輸入框、下拉選單、檔案上傳拖曳區的底色對比度 */
        div[data-baseweb="input"], div[data-baseweb="select"], [data-testid="stFileUploadDropzone"] {{
            background-color: rgba(14, 14, 14, 0.95) !important;
            border: 1px solid rgba(255, 255, 255, 0.15) !important;
            border-radius: 8px !important;
        }}
        
        /* 5. 提示框 (st.info, st.success, st.warning) 視覺硬化 */
        [data-testid="stAlert"] {{
            background-color: rgba(28, 28, 28, 0.96) !important;
            border: 1px solid rgba(255, 255, 255, 0.22) !important;
            border-radius: 12px !important;
            backdrop-filter: blur(10px) !important;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5) !important;
        }}
        [data-testid="stAlert"] p {{
            color: #FFFFFF !important;
            font-weight: 500 !important;
        }}
        
        /* 6. 折疊面板 (st.expander) 視覺一致化 */
        [data-testid="stExpander"] {{
            background-color: rgba(26, 26, 26, 0.88) !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 10px !important;
            backdrop-filter: blur(6px) !important;
        }}
        
        /* 7. 全局文字邊緣文字陰影 (Text Shadow) 保護層，全面防禦吃字 */
        h1, h2, h3, h4, h5, h6, p, label, .stMarkdown {{
            text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.85) !important;
        }}
        </style>
        """,
            unsafe_allow_html=True,
        )
    except Exception:
        pass