# ============================================================
#  core_data.py  —  Genki Beibei v2.3 (White Glassmorphism UI Edition)
# ============================================================
import streamlit as st
import pandas as pd
import os
import json
import base64
import hmac
import hashlib
import math
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
        secret = st.secrets["HMAC_SECRET"]
        if isinstance(secret, str):
            return secret.encode()
        return bytes(secret)
    return b"local_secret_key_DO_NOT_USE_IN_PRODUCTION_12345"


# -------- 3. 安全：密碼雜湊 --------
def _hash_password(password: str) -> str:
    """產生 bcrypt 雜湊字串（含 salt，回傳 utf-8 字串供 Supabase 存放）"""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def _verify_password(password: str, stored_hash: str) -> bool:
    """常數時間驗證密碼是否符合儲存的 bcrypt 雜湊"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# -------- 4. 鑑權：註冊 / 登入 --------
def _validate_username(username: str) -> tuple[bool, str]:
    """限制使用者暱稱字元集，避免 SQL 注入或 URL 編碼問題"""
    if not username:
        return False, "暱稱不可為空。"
    if len(username) < 2 or len(username) > 32:
        return False, "暱稱長度需在 2 至 32 個字元之間。"
    for ch in username:
        if not (ch.isalnum() or ch in "_-" or "\u4e00" <= ch <= "\u9fff"):
            return False, f"暱稱含有不允許的字元：'{ch}'。請改用英數、底線、連字號或中文字。"
    return True, ""


def _validate_password(password: str) -> tuple[bool, str]:
    """簡易密碼強度規則：長度 ≥ 6"""
    if not password or len(password) < 6:
        return False, "密碼長度至少需要 6 個字元。"
    if len(password) > 128:
        return False, "密碼過長（上限 128 字元）。"
    return True, ""


def register_user(username: str, password: str):
    """在 Supabase 資料庫中安全註冊受試者帳號"""
    sb = get_supabase()
    if not sb:
        return False, "無法連線至雲端資料庫，請先檢查 Streamlit Secrets 設定。"

    ok, msg = _validate_username(username)
    if not ok:
        return False, msg
    ok, msg = _validate_password(password)
    if not ok:
        return False, msg

    try:
        res = sb.table("users").select("username").eq("username", username).execute()
        if res.data:
            return False, "該暱稱已被註冊，請更換暱稱或直接進行登入。"

        p_hash = _hash_password(password)
        sb.table("users").insert(
            {"username": username, "password_hash": p_hash}
        ).execute()
        return True, "註冊成功"
    except Exception as e:
        return False, f"註冊程序異常: {str(e)}"


def login_user(username: str, password: str):
    """安全驗證受試者帳密登入狀態，支援舊版 SHA-256 雜湊自動遷移至 bcrypt"""
    sb = get_supabase()
    if not sb:
        return False, "無法連線至雲端資料庫，請先檢查 Streamlit Secrets 設定。"

    ok, msg = _validate_username(username)
    if not ok:
        return False, msg

    try:
        res = sb.table("users").select("*").eq("username", username).execute()
        if not res.data:
            return False, "受試者暱稱或密碼不正確，請重新檢查。"

        row = res.data[0]
        stored = row.get("password_hash", "")

        if stored.startswith("$2"):
            if _verify_password(password, stored):
                return True, "登入成功"
            return False, "受試者暱稱或密碼不正確，請重新檢查。"

        legacy_hash = hashlib.sha256(
            password.encode() + get_hmac_secret()
        ).hexdigest()
        if hmac.compare_digest(legacy_hash, stored):
            try:
                new_hash = _hash_password(password)
                sb.table("users").update({"password_hash": new_hash}).eq(
                    "username", username
                ).execute()
            except Exception:
                pass
            return True, "登入成功"

        return False, "受試者暱稱或密碼不正確，請重新檢查。"
    except Exception as e:
        return False, f"登入程序異常: {str(e)}"


# -------- 5. 安全：HMAC nonce（URL 完整性簽章）--------
# 設計理由 (iframe 約束下的最佳安全平衡):
#   由於 Streamlit Cloud 不允許將 HMAC_SECRET 下放至 JS 端 (會洩漏),
#   而 JS 端的 RT 等欄位必須等到測驗結束才有值, 所以我們無法在「同一次
#   簽章」涵蓋所有 11 個欄位。
#
#   採用「兩段式信任模型」:
#     A. 預簽欄位 (NONCE_FIELDS): u, sleep_h, fatigue, delta_E
#        — 由 Python 在進入測驗前簽章, 保證身份與主觀資料不可竄改
#     B. 測驗結果欄位: rt_*, lapses, false_starts, valid_trials, interference
#        — 由 JS 端產生, Python 端用 _PAYLOAD_SCHEMA 做嚴格範圍驗證
#
#   威脅分析: 攻擊者最多能在自己的 URL 上修改自己的測驗成績, 但
#   (a) 只會污染自己的 dashboard (b) 改假反而失去自我追蹤意義
#   故此妥協對於健康追蹤類學術應用是合理的。
NONCE_FIELDS = (
    "u", "sleep_h", "fatigue", "delta_E",
)


def make_nonce(payload: dict) -> str:
    """為 URL 傳輸鏈產生安全完整性防偽簽章（涵蓋全部關鍵欄位）"""
    secret = get_hmac_secret()
    parts = [str(payload.get(k, "")) for k in NONCE_FIELDS]
    msg = "|".join(parts).encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify_nonce(verify_dict: dict, nonce: str) -> bool:
    """驗證 URL 傳回的參數是否遭到惡意竄改（常數時間比對）"""
    if not nonce or len(nonce) != 64:
        return False
    expected = make_nonce(verify_dict)
    return hmac.compare_digest(expected, nonce)


# -------- 6. URL Payload 驗證 --------
# 各欄位允許範圍 (型別, min, max)。
# delta_E 採 CIEDE2000 標準尺度: 一般 0-100, 極端理論上限約 ~150。
# delta_L/a/b 採 CIE LAB 通道差: L 差約 -100~100, a/b 差約 -255~255
_PAYLOAD_SCHEMA = {
    "sleep_h":        ("float", 0.0,    24.0),
    "fatigue":        ("int",   1,      10),
    "delta_E":        ("float", 0.0,    150.0),
    "rt_mean":        ("int",   0,      10000),
    "rt_congruent":   ("int",   0,      10000),
    "rt_incongruent": ("int",   0,      10000),
    "interference":   ("int",  -5000,   5000),
    "lapses":         ("int",   0,      2000),
    "false_starts":   ("int",   0,      2000),
    "valid_trials":   ("int",   0,      10000),
}


def validate_url_payload(raw_payload: dict):
    """清理、轉換並校驗前端傳入的測驗數據"""
    clean = {}
    for key, (typ, lo, hi) in _PAYLOAD_SCHEMA.items():
        raw = raw_payload.get(key)
        if raw is None or raw == "":
            return None, f"欄位 {key} 缺失，無法完成存檔。"

        try:
            if typ == "int":
                val = int(float(raw))
            else:
                val = float(raw)
        except (TypeError, ValueError):
            return None, f"欄位 {key} 型態錯誤：{raw!r}"

        if val < lo or val > hi:
            return None, f"欄位 {key} 數值 {val} 超出允許範圍 [{lo}, {hi}]。"

        clean[key] = val
    return clean, None


# -------- 7. 主資料寫入 --------
def save_full_pipeline_data(
    name, sleep, fatigue, delta_e, rt_mean=0, rt_congruent=0,
    rt_incongruent=0, interference=0, lapses=0, false_starts=0,
    valid_trials=0, delta_e_left=0, delta_e_right=0, asymmetry=0,
):
    """資料同步中心：將生理與雙模式認知科學測驗數據完整寫入 Supabase"""
    sb = get_supabase()
    if not sb:
        return False

    def _safe_float(v, default=0.0):
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    def _safe_int(v, default=0):
        try:
            return int(float(v)) if v is not None else default
        except (TypeError, ValueError):
            return default

    data = {
        "User_Name":     str(name),
        "Date":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Sleep_Hours":   _safe_float(sleep),
        "Fatigue_Level": _safe_int(fatigue),
        "Delta_E":       _safe_float(delta_e),
        "Delta_E_Left":  _safe_float(delta_e_left),
        "Delta_E_Right": _safe_float(delta_e_right),
        "Asymmetry":     _safe_float(asymmetry),
        "Mean_RT":       _safe_int(rt_mean),
        "RT_Congruent":  _safe_int(rt_congruent),
        "RT_Incongruent": _safe_int(rt_incongruent),
        "Interference":  _safe_int(interference),
        "Lapses":        _safe_int(lapses),
        "False_Starts":  _safe_int(false_starts),
        "Valid_Trials":  _safe_int(valid_trials),
    }

    try:
        sb.table("health_logs").insert(data).execute()
        return True
    except Exception as e:
        st.sidebar.error(f"雲端寫入失敗: {str(e)}")
        return False


def load_user_history(user_name: str) -> pd.DataFrame:
    """讀取當前登入受試者的專屬縱向追蹤紀錄庫"""
    sb = get_supabase()
    if not sb:
        return pd.DataFrame()

    try:
        res = (
            sb.table("health_logs")
            .select("*")
            .eq("User_Name", user_name)
            .order("Date")
            .execute()
        )
        if not res.data:
            return pd.DataFrame()

        df = pd.DataFrame(res.data)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


# -------- 8. Baseline 計算 --------
def compute_user_baseline(df: pd.DataFrame, n_days: int = 3) -> dict:
    """計算儀表板個人化基準線 (Baseline)"""
    if df is None or df.empty:
        return {}

    head = df.head(n_days)
    if head.empty:
        return {}

    base = {}
    cols = ["Sleep_Hours", "Fatigue_Level", "Delta_E", "Mean_RT"]
    for col in cols:
        if col in head.columns:
            series = pd.to_numeric(head[col], errors="coerce").dropna()
            if not series.empty:
                base[col] = float(series.median())
    return base


def compute_relative_change(current, base):
    """計算最新數據相對基準線的百分比位移量"""
    try:
        if base is None or pd.isna(base) or float(base) == 0:
            return None
        return ((float(current) - float(base)) / float(base)) * 100
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------
#  9. 視覺：高端全局「白色半透明毛玻璃模塊」CSS 注入器（修復吃字核心）
# ------------------------------------------------------------------
def set_bg_from_local(image_file: str):
    """
    高階 CSS 注入：將 Streamlit 核心內容區塊包裹進一個白色、
    高識別度且稍微透明的毛玻璃懸浮卡片模塊中，徹底根除草地背景導致的黑字吃字問題。
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
        /* A. 全局網頁草地背景設定 */
        .stApp {{
            background-image: url("data:image/{mime};base64,{b64}");
            background-size: cover;
            background-attachment: fixed;
            background-position: center;
        }}
        
        /* B. 【核心優化】主應用區塊全面包裹為「白色半透明懸浮模塊」 */
        .block-container {{
            background-color: rgba(255, 255, 255, 0.88) !important; /* 白色底盤，透明度度設為 0.88 確保高對比 */
            backdrop-filter: blur(15px) !important; /* 模塊後方小羊背景自帶高級毛玻璃模糊 */
            -webkit-backdrop-filter: blur(15px) !important;
            border-radius: 20px !important; /* 四角優雅圓角化 */
            padding: 45px 35px !important; /* 擴大留白邊界，提升整潔感 */
            margin-top: 40px !important;
            margin-bottom: 40px !important;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25) !important; /* 增加深色陰影，讓白色模塊有浮現感 */
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
        }}
        
        /* C. 強化文字顏色與對比度，全面防禦光影吃字 */
        h1, h2, h3, h4, h5, h6, p, label, span, li {{
            color: #111111 !important; /* 採用高對比深炭黑色文字 */
            font-weight: 500 !important;
        }}
        
        /* 專門優化大標題 */
        h1 {{
            color: #1B5E20 !important; /* 深森林綠，在白底上非常醒目且呼應🌱主題 */
            text-shadow: 1px 1px 2px rgba(255, 255, 255, 0.8) !important;
        }}
        
        /* 專門優化說明副標題小字 */
        .stMarkdown div p, caption, small {{
            color: #2D3748 !important; /* 深灰藍色 */
            font-weight: 400 !important;
        }}
        
        /* D. 表單輸入元件與上傳拖曳區微調 */
        div[data-baseweb="input"], div[data-baseweb="select"], [data-testid="stFileUploadDropzone"] {{
            background-color: rgba(255, 255, 255, 0.95) !important;
            border: 1px solid #CBD5E1 !important;
            border-radius: 8px !important;
        }}
        
        /* E. 系統提示框 (st.info, st.success 等) 的白底適應 */
        [data-testid="stAlert"] {{
            background-color: rgba(248, 250, 252, 0.95) !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
        }}
        [data-testid="stAlert"] p {{
            color: #1E293B !important;
        }}
        
        /* F. 折疊面板 (st.expander) */
        [data-testid="stExpander"] {{
            background-color: rgba(255, 255, 255, 0.7) !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 10px !important;
        }}
        </style>
        """,
            unsafe_allow_html=True,
        )
    except Exception:
        pass