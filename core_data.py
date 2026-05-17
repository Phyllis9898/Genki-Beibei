import streamlit as st
import pandas as pd
import os
import json
import base64
import hmac
import hashlib
from datetime import datetime

@st.cache_resource
def get_supabase():
    """初始化並快取 Supabase 連線用戶端"""
    try:
        from supabase import create_client
        if "SUPABASE_URL" in st.secrets and "SUPABASE_KEY" in st.secrets:
            return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception:
        return None
    return None

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
    """安全獲取或生成動態加密密鑰"""
    if "HMAC_SECRET" in st.secrets:
        return st.secrets["HMAC_SECRET"].encode()
    return b"temporary_local_secret_fallback_key_12345"

def generate_secure_token(username, mean_rt, lapses):
    """生成具有時序與值域特徵的資料完整性 HMAC Token"""
    secret = get_hmac_secret()
    message = f"{username}-{mean_rt}-{lapses}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()

def verify_secure_token(username, mean_rt, lapses, received_token):
    """驗證前端傳入參數是否遭到惡意 URL 篡改"""
    expected = generate_secure_token(username, mean_rt, lapses)
    return hmac.compare_digest(expected, received_token)

def save_full_pipeline_data(name, sleep, fatigue, delta_e, rt, fast, slow, lapse, fs):
    """
    全方位資料流水線存檔中心：
    支援值域邊界檢查、Supabase 備份。若雲端連線失敗則啟動優雅降級寫入本地 CSV。
    """
    # 臨床值域合規性硬性檢查 (防止 nan/inf 注入攻擊)
    if not (0 <= float(sleep) <= 24) or not (0 <= int(fatigue) <= 10):
        raise ValueError("資料值域異常超出臨床合理範疇。")
    if not (0 <= float(delta_e) <= 100) or not (0 <= int(rt) <= 10000):
        raise ValueError("生理或反應時測驗參數異常。")

    data = {
        "User_Name": str(name),
        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Sleep_Hours": float(sleep),
        "Fatigue_Level": int(fatigue),
        "Delta_E": float(delta_e),
        "Mean_RT": int(rt),
        "Fast_Responses": int(fast),
        "Slow_Responses": int(slow),
        "Lapses": int(lapse),
        "False_Starts": int(fs)
    }
    
    # 1. 嘗試備份到雲端資料庫 Supabase
    sb = get_supabase()
    supabase_success = False
    if sb:
        try:
            sb.table("health_logs").insert(data).execute()
            supabase_success = True
        except Exception:
            pass # 靜默轉移至本地 CSV 模式
            
    # 2. 同步寫入本地或容器端的安全 CSV 檔案庫
    df = pd.DataFrame([data])
    fname = f"health_data_{name}.csv"
    if os.path.exists(fname):
        try:
            old_df = pd.read_csv(fname)
            pd.concat([old_df, df], ignore_index=True).to_csv(fname, index=False)
        except Exception:
            df.to_csv(fname, index=False)
    else:
        df.to_csv(fname, index=False)
        
    if sb and not supabase_success:
        raise ConnectionError("Supabase 表結構不相符或連線逾時")

def load_user_history(user_name):
    """跨平台資料加載器：優先讀取雲端歷史，無連線時調用本地 CSV"""
    sb = get_supabase()
    if sb:
        try:
            res = sb.table("health_logs").select("*").eq("User_Name", user_name).order("Date").execute()
            if res.data and len(res.data) > 0:
                return pd.DataFrame(res.data)
        except Exception:
            pass
            
    fname = f"health_data_{user_name}.csv"
    if os.path.exists(fname):
        try:
            return pd.read_csv(fname)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def set_bg_from_local(image_file):
    """
    注入高端全局玻璃帷幕 (Glassmorphism) 視覺樣式，
    徹底解決複雜草地背景對文字與模組框架的干擾問題。
    """
    try:
        with open(image_file, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        
        st.markdown(f"""
        <style>
        /* 1. 配置全螢幕背景 */
        .stApp {{
            background-image: url("data:image/jpeg;base64,{b64}");
            background-size: cover;
            background-attachment: fixed;
            background-position: center;
        }}
        
        /* 2. 鋪設深色主體防干擾濾鏡 */
        [data-testid="stAppViewContainer"] > .main {{
            background-color: rgba(12, 12, 12, 0.75) !important;
        }}
        
        /* 3. 玻璃化渲染 st.info, st.success, st.warning 區塊 */
        [data-testid="stAlert"] {{
            background-color: rgba(30, 30, 30, 0.94) !important;
            border: 1px solid rgba(255, 255, 255, 0.18) !important;
            border-radius: 12px !important;
            backdrop-filter: blur(12px) !important;
            box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5) !important;
        }}
        
        /* 4. 強制拉高文字可讀性 */
        [data-testid="stAlert"] p {{
            color: #FFFFFF !important;
            font-weight: 500 !important;
            font-size: 1rem !important;
        }}
        
        /* 5. 優化折疊面板 */
        [data-testid="stExpander"] {{
            background-color: rgba(32, 32, 32, 0.88) !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 10px !important;
            backdrop-filter: blur(8px) !important;
        }}
        </style>
        """, unsafe_allow_html=True)
    except Exception:
        pass