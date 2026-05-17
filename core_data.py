# ============================================================
#  core_data.py  —  Genki Beibei v2.2 (Pure Local & Stroop Edition)
#  ------------------------------------------------------------
#  移除所有 Supabase 相關依賴，專注於本地 CSV 高效儲存。
#  新增 Stroop 干擾測驗與儀表板基準線 (Baseline) 計算支援函數。
# ============================================================
import streamlit as st
import pandas as pd
import os
import json
import base64
import hmac
import hashlib
from datetime import datetime

def load_nutrition_db():
    """載入本地飲食營養學建議知識庫"""
    try:
        with open("nutrition_db.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def go_to(page_name):
    """Streamlit 多頁面集中式路由控制器"""
    st.session_state.page = page_name
    st.rerun()

def get_hmac_secret():
    """獲取本地安全加密密鑰"""
    if "HMAC_SECRET" in st.secrets:
        return st.secrets["HMAC_SECRET"].encode()
    return b"local_secret_key_12345"

def make_nonce(payload: dict) -> str:
    """為 URL 傳輸產生安全簽章"""
    secret = get_hmac_secret()
    msg = f"{payload.get('u', '')}-{payload.get('sleep_h', 0)}-{payload.get('fatigue', 0)}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()

def verify_nonce(verify_dict: dict, nonce: str) -> bool:
    """驗證 URL 傳回的參數是否遭到竄改"""
    expected = make_nonce(verify_dict)
    return hmac.compare_digest(expected, nonce)

def validate_url_payload(raw_payload: dict):
    """清理並驗證前端傳入的測驗數據"""
    clean = {}
    for k, v in raw_payload.items():
        if v is None:
            clean[k] = 0
        else:
            try:
                clean[k] = float(v) if '.' in str(v) else int(v)
            except ValueError:
                clean[k] = 0
    return clean, None

def save_full_pipeline_data(name, sleep, fatigue, delta_e, rt_mean=0, rt_congruent=0, 
                            rt_incongruent=0, interference=0, lapses=0, false_starts=0, 
                            valid_trials=0, delta_e_left=0, delta_e_right=0, asymmetry=0):
    """
    資料儲存中心：直接寫入本地 CSV，徹底解決 Supabase 連線卡死問題。
    同時支援 PVT-B 與 Stroop 測驗的雙軌數據。
    """
    data = {
        "User_Name": str(name),
        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Sleep_Hours": float(sleep),
        "Fatigue_Level": int(fatigue),
        "Delta_E": float(delta_e),
        "Delta_E_Left": float(delta_e_left) if delta_e_left else 0.0,
        "Delta_E_Right": float(delta_e_right) if delta_e_right else 0.0,
        "Asymmetry": float(asymmetry) if asymmetry else 0.0,
        "Mean_RT": int(rt_mean),
        "RT_Congruent": int(rt_congruent),
        "RT_Incongruent": int(rt_incongruent),
        "Interference": int(interference),
        "Lapses": int(lapses),
        "False_Starts": int(false_starts),
        "Valid_Trials": int(valid_trials)
    }
    
    df = pd.DataFrame([data])
    fname = f"health_data_{name}.csv"
    
    # 本地 CSV 寫入邏輯
    if os.path.exists(fname):
        try:
            old_df = pd.read_csv(fname)
            pd.concat([old_df, df], ignore_index=True).to_csv(fname, index=False)
        except Exception:
            df.to_csv(fname, index=False)
    else:
        df.to_csv(fname, index=False)
        
    return True

def load_user_history(user_name):
    """讀取用戶歷史紀錄供 Dashboard 繪圖"""
    fname = f"health_data_{user_name}.csv"
    if os.path.exists(fname):
        try:
            return pd.read_csv(fname)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def compute_user_baseline(df, n_days=3):
    """計算儀表板個人化基準線 (Baseline)"""
    if df.empty:
        return {}
    recent = df.tail(n_days)
    base = {}
    cols = ["Sleep_Hours", "Fatigue_Level", "Delta_E", "Mean_RT"]
    for col in cols:
        if col in recent.columns:
            base[col] = recent[col].median()
    return base

def compute_relative_change(current, base):
    """計算相對變化量百分比"""
    if base == 0 or pd.isna(base):
        return None
    return ((current - base) / base) * 100

def set_bg_from_local(image_file):
    """全局 CSS 玻璃帷幕注入器"""
    try:
        with open(image_file, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        
        st.markdown(f'''
        <style>
        .stApp {{
            background-image: url("data:image/jpeg;base64,{b64}");
            background-size: cover;
            background-attachment: fixed;
            background-position: center;
        }}
        [data-testid="stAppViewContainer"] > .main {{
            background-color: rgba(12, 12, 12, 0.75) !important;
        }}
        [data-testid="stAlert"] {{
            background-color: rgba(30, 30, 30, 0.94) !important;
            border: 1px solid rgba(255, 255, 255, 0.18) !important;
            border-radius: 12px !important;
            backdrop-filter: blur(12px) !important;
            box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5) !important;
        }}
        [data-testid="stAlert"] p {{
            color: #FFFFFF !important;
        }}
        [data-testid="stExpander"] {{
            background-color: rgba(32, 32, 32, 0.88) !important;
            border-radius: 10px !important;
        }}
        </style>
        ''', unsafe_allow_html=True)
    except Exception:
        pass