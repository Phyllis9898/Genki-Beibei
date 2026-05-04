import streamlit as st
import pandas as pd
import os
import json
import base64
from datetime import datetime

@st.cache_resource
def get_supabase():
    try:
        from supabase import create_client
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

def load_nutrition_db():
    try:
        with open("nutrition_db.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def go_to(page_name):
    st.session_state.page = page_name

def save_full_pipeline_data(name, sleep, fatigue, delta_e, rt, fast, slow, lapse, fs):
    today_str = datetime.now().strftime("%Y-%m-%d")
    data_entry = {
        "User_Name": name, "Date": today_str, "Sleep_Hours": float(sleep),
        "Fatigue_Level": int(fatigue), "Delta_E": float(delta_e),
        "Mean_RT": int(rt), "Fastest_RT": int(fast), "Slowest_RT": int(slow),
        "Lapses": int(lapse), "False_Starts": int(fs)
    }
    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("health_logs").insert(data_entry).execute()
        except Exception as e:
            st.sidebar.error(f"雲端存檔失敗: {e}")
    
    filename = f"health_data_{name}.csv"
    new_df = pd.DataFrame([data_entry])
    if os.path.exists(filename):
        old_df = pd.read_csv(filename)
        pd.concat([old_df, new_df], ignore_index=True).to_csv(filename, index=False, encoding='utf-8-sig')
    else:
        new_df.to_csv(filename, index=False, encoding='utf-8-sig')

def load_user_history(user_name):
    supabase = get_supabase()
    if supabase:
        try:
            res = supabase.table("health_logs").select("*").eq("User_Name", user_name).order("Date").execute()
            if res.data:
                df = pd.DataFrame(res.data)
                df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
                return df
        except Exception: pass
    filename = f"health_data_{user_name}.csv"
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        return df
    return pd.DataFrame()

def set_bg_from_local(image_file):
    try:
        with open(image_file, "rb") as file:
            encoded = base64.b64encode(file.read()).decode()
        st.markdown(f"""<style>.stApp {{background-image: url("data:image/jpeg;base64,{encoded}");background-size: cover;}}</style>""", unsafe_allow_html=True)
    except Exception: pass
