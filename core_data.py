import streamlit as st
import pandas as pd
import os, json, base64
from datetime import datetime

@st.cache_resource
def get_supabase():
    try:
        from supabase import create_client
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

def load_nutrition_db():
    try:
        with open("nutrition_db.json", "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def go_to(page_name): st.session_state.page = page_name

def save_full_pipeline_data(name, sleep, fatigue, delta_e, rt, fast, slow, lapse, fs):
    data = {
        "User_Name": name, "Date": datetime.now().strftime("%Y-%m-%d"),
        "Sleep_Hours": float(sleep), "Fatigue_Level": int(fatigue),
        "Delta_E": float(delta_e), "Mean_RT": int(rt), "Lapses": int(lapse), "False_Starts": int(fs)
    }
    sb = get_supabase()
    if sb: 
        try: sb.table("health_logs").insert(data).execute()
        except: st.sidebar.warning("雲端備份延遲")
    
    df = pd.DataFrame([data])
    fname = f"health_data_{name}.csv"
    if os.path.exists(fname): pd.concat([pd.read_csv(fname), df]).to_csv(fname, index=False)
    else: df.to_csv(fname, index=False)

def load_user_history(user_name):
    sb = get_supabase()
    if sb:
        try:
            res = sb.table("health_logs").select("*").eq("User_Name", user_name).order("Date").execute()
            if res.data: return pd.DataFrame(res.data)
        except: pass
    fname = f"health_data_{user_name}.csv"
    return pd.read_csv(fname) if os.path.exists(fname) else pd.DataFrame()

def save_roi_for_dl(*args): pass # 修正匯入崩潰

def set_bg_from_local(image_file):
    try:
        with open(image_file, "rb") as f: b64 = base64.b64encode(f.read()).decode()
        st.markdown(f"""<style>.stApp {{background-image: url("data:image/jpeg;base64,{b64}");background-size: cover;}}</style>""", unsafe_allow_html=True)
    except: pass