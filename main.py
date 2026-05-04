# ==========================================
# 檔案名稱：main.py (純淨雲端版)
# 【變更點】移除了對 show_companion 的呼叫與 WebRTC 相關的 Windows 防護程式碼。
# ==========================================
import streamlit as st

st.set_page_config(page_title="肌智量點顧問", layout="wide", page_icon="🌱")

import urllib.parse
import pandas as pd
import os
from datetime import datetime

from core_data import set_bg_from_local, save_full_pipeline_data
from ui_pages import (
    show_landing, show_profile, show_home, 
    show_analyzer, show_pvt_game, show_dashboard
)

# --- 頁面背景與初始化 Session State ---
set_bg_from_local("bg.png")

if 'page' not in st.session_state:
    st.session_state.page = 'landing'
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""
if 'user_age' not in st.session_state:
    st.session_state.user_age = 22
if 'user_job' not in st.session_state:
    st.session_state.user_job = "學生"
if 'temp_analysis_data' not in st.session_state:
    st.session_state.temp_analysis_data = None

# ==========================================
# URL 攔截器 (統一防彈存檔 API)
# ==========================================
try:
    qp = st.query_params
    has_save = "save" in qp
except AttributeError:
    qp = st.experimental_get_query_params()
    has_save = "save" in qp

if has_save:
    def get_val(key):
        val = qp.get(key)
        return val[0] if isinstance(val, list) else val

    user = urllib.parse.unquote(get_val("u"))
    sleep = float(get_val("sl"))
    fatigue = int(get_val("fa"))
    deltaE = float(get_val("de"))
    rt = float(get_val("rt"))
    lapses = int(get_val("la"))
    fs = int(get_val("fs"))

    save_full_pipeline_data(
        name=user, sleep=sleep, fatigue=fatigue, delta_e=deltaE, 
        rt=rt, fast=0, slow=0, lapse=lapses, fs=fs
    )

    st.session_state.user_name = user
    # 存檔完畢後，清空暫存並導向儀表板
    st.session_state.temp_analysis_data = None
    st.session_state.page = "dashboard"
    
    try:
        st.query_params.clear()
    except AttributeError:
        st.experimental_set_query_params()
    st.rerun()

# ==========================================
# 路由控制器 (Router)
# ==========================================
if st.session_state.page == 'landing':
    show_landing()
elif st.session_state.page == 'profile':
    show_profile()
elif st.session_state.page == 'home':
    show_home()
elif st.session_state.page == 'analyzer':
    show_analyzer()
elif st.session_state.page == 'pvt_game':
    show_pvt_game()
elif st.session_state.page == 'dashboard':
    show_dashboard()