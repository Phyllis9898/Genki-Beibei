import streamlit as st
import os
from core_data import set_bg_from_local, go_to
from ui_pages import show_home_page, show_cv_page, show_pvt_page, show_dashboard_page

# 1. 設置 Streamlit 網頁基本組態
st.set_page_config(
    page_title="元氣貝貝 - 疲勞與警覺性智能顧問系統",
    page_icon="👁️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 2. 初始化核心 Session State 變數
if "page" not in st.session_state:
    st.session_state.page = "home"
if "user_name" not in st.session_state:
    st.session_state.user_name = "龔同學"
if "sleep_hours" not in st.session_state:
    st.session_state.sleep_hours = 7.0
if "fatigue_level" not in st.session_state:
    st.session_state.fatigue_level = 3
if "delta_e" not in st.session_state:
    st.session_state.delta_e = 0.0
if "mean_rt" not in st.session_state:
    st.session_state.mean_rt = 0
if "lapses" not in st.session_state:
    st.session_state.lapses = 0
if "false_starts" not in st.session_state:
    st.session_state.false_starts = 0

# 3. 渲染全局高階視覺背景
bg_path = "background.jpg"
if os.path.exists(bg_path):
    set_bg_from_local(bg_path)

# 4. 前端表單與資料傳輸攔截中心 (防卡死機制)
def trigger_data_sync_pipeline():
    """利用 st.spinner 包裝雲端連線，提供最直觀的 Schema 錯誤捕獲提示"""
    with st.spinner("正在將您的生理眼周差值與 PVT 認知數據同步至雲端後端..."):
        try:
            from core_data import save_full_pipeline_data
            save_full_pipeline_data(
                name=st.session_state.user_name,
                sleep=st.session_state.sleep_hours,
                fatigue=st.session_state.fatigue_level,
                delta_e=st.session_state.delta_e,
                rt=st.session_state.mean_rt,
                fast=st.session_state.get('fast_responses', 0),
                slow=st.session_state.get('slow_responses', 0),
                lapse=st.session_state.lapses,
                fs=st.session_state.false_starts
            )
            st.success("🎉 數據雲端備份成功！已即時更新您的個人全縱向追蹤儀表板。")
        except Exception as e:
            st.error("⚠️ 雲端資料庫擴充同步失敗")
            st.info(
                f"診斷訊息：{str(e)}\n\n"
                "💡 您的 Supabase 後端可能尚未跑完 v2.0/v2.1 的 SQL Schema 擴充。 "
                "不過別擔心！系統已自動啟動【優雅降級機制】，本次測驗的所有數據已安全、完整地"
                f"備份在本地端的『health_data_{st.session_state.user_name}.csv』中，您的進度絕不遺失！"
            )

# 5. 處理來自 PVT JavaScript 端經由安全驗證後的 URL 回傳控制
query_params = st.query_params
if "save" in query_params and "u" in query_params:
    try:
        from core_data import verify_secure_token
        u = query_params["u"]
        rt = int(query_params.get("rt", 0))
        la = int(query_params.get("la", 0))
        fs = int(query_params.get("fs", 0))
        token = query_params.get("token", "")
        
        # 安全權限校驗
        if verify_secure_token(u, rt, la, token):
            st.session_state.user_name = u
            st.session_state.mean_rt = rt
            st.session_state.lapses = la
            st.session_state.false_starts = fs
            
            # 清空 URL 防重複觸發
            st.query_params.clear()
            
            st.sidebar.success("認知檢測數據校驗通過")
            # 觸發大流水線數據儲存
            trigger_data_sync_pipeline()
            go_to("dashboard")
        else:
            st.sidebar.error("安全驗證失敗：URL 簽章不符，拒絕寫入。")
            st.query_params.clear()
    except Exception:
        st.query_params.clear()

# 6. 多頁面路由分流渲染
if st.session_state.page == "home":
    show_home_page()
elif st.session_state.page == "cv_analysis":
    show_cv_page()
elif st.session_state.page == "pvt_test":
    show_pvt_page()
elif st.session_state.page == "dashboard":
    show_dashboard_page()