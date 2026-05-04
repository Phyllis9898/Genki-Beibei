# ==========================================
# 檔案名稱：core_data.py
# 【根本修復版】解決 Supabase v2 與 streamlit-webrtc (aiortc) 的
# 非同步事件迴圈競爭問題 (Event Loop Conflict)
#
# 【根因說明】
# supabase-py v2 底層使用 httpx + anyio 作為非同步 HTTP 引擎。
# streamlit-webrtc 底層使用 aiortc，也需要控制 asyncio event loop。
# 當 Supabase Client 在「模組載入階段 (import time)」就被初始化時，
# anyio 的後端會搶先綁定 event loop，導致之後 aiortc 在建立 WebRTC
# ICE 連線時，找不到可用的 event loop，永遠卡在 Loading 黑畫面。
#
# 【修復策略：完全延遲初始化 (Full Lazy Initialization)】
# 將 `create_client()` 的呼叫從「模組頂部」移至「函式內部」，
# 並加上 st.cache_resource 快取，確保：
# 1. Supabase client 只在「真正需要存取資料庫時」才建立
# 2. 建立後被快取，避免重複連線
# 3. aiortc/WebRTC 在自己的執行緒中獨立建立 event loop，不受干擾
# ==========================================

import streamlit as st
import pandas as pd
import os
import json
import base64
from datetime import datetime


# ==========================================
# --- 1. Supabase 連線設定（完全延遲初始化）---
# ==========================================
# 【關鍵修復】使用 @st.cache_resource 裝飾器
# 這個裝飾器讓函式只在「第一次被呼叫時」執行，之後直接回傳快取的 client 物件。
# 配合「只在需要時才呼叫此函式」的設計，就能完全避免 import 階段的 event loop 衝突。
@st.cache_resource
def get_supabase():
    """
    取得 Supabase client 的工廠函式（快取單例模式）。
    
    【為何用 @st.cache_resource 而非模組層級變數？】
    - 模組層級變數在 `import core_data` 時就執行 → 太早，會搶 event loop
    - @st.cache_resource 在「第一次呼叫此函式時」才執行 → 延遲到實際需要時
    - Streamlit 保證此函式在整個 app 生命週期中只執行一次，效能等同單例模式
    
    回傳 None 表示 Supabase 不可用（例如未設定 secrets），程式應降級到本地 CSV。
    """
    try:
        # 只在這裡才 import supabase，進一步延遲 anyio 後端的初始化
        from supabase import create_client, Client
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except KeyError:
        # secrets 未設定，靜默降級，不顯示錯誤（本地開發常見情況）
        return None
    except Exception as e:
        # 其他連線錯誤（例如網路問題），記錄但不中斷程式
        st.sidebar.warning(f"⚠️ Supabase 連線初始化失敗: {e}")
        return None


# ==========================================
# --- 2. 營養資料庫載入 ---
# ==========================================
def load_nutrition_db():
    """載入本地 JSON 格式的營養建議資料庫。"""
    try:
        with open("nutrition_db.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        st.error("❌ 找不到 nutrition_db.json，請確認檔案已放置在專案根目錄。")
        return {}
    except json.JSONDecodeError:
        st.error("❌ nutrition_db.json 格式錯誤，請檢查 JSON 語法。")
        return {}


# ==========================================
# --- 3. 頁面跳轉核心 ---
# ==========================================
def go_to(page_name):
    """統一的頁面跳轉函式，修改 session_state.page 觸發 Streamlit 重繪。"""
    st.session_state.page = page_name


# ==========================================
# --- 4. 數據存檔核心（雙軌備份：雲端 Supabase + 本地 CSV）---
# ==========================================
def save_full_pipeline_data(name, sleep, fatigue, delta_e, rt, fast, slow, lapse, fs):
    """
    將一筆完整的健康檢測數據同時存入 Supabase（雲端）與本地 CSV（備份）。
    
    【設計說明】
    採用雙軌備份策略：
    - 主軌（Supabase）：跨裝置存取、永久保存
    - 備軌（本地 CSV）：離線備份，Supabase 失敗時仍能保留數據
    
    回傳 True 表示雲端存檔成功，False 表示僅本地備份。
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    data_entry = {
        "User_Name": name,
        "Date": today_str,
        "Sleep_Hours": float(sleep),
        "Fatigue_Level": int(fatigue),
        "Delta_E": float(delta_e),
        "Mean_RT": int(rt),
        "Fastest_RT": int(fast),
        "Slowest_RT": int(slow),
        "Lapses": int(lapse),
        "False_Starts": int(fs)
    }

    # === A. 嘗試存入 Supabase ===
    # 注意：這裡才第一次呼叫 get_supabase()，確保延遲初始化生效
    supabase = get_supabase()
    db_success = False
    if supabase:
        try:
            supabase.table("health_logs").insert(data_entry).execute()
            db_success = True
        except Exception as e:
            st.sidebar.error(f"⚠️ 雲端存檔失敗: {e}")

    # === B. 本地 CSV 備份（無論雲端成功與否，都執行）===
    filename = f"health_data_{name}.csv"
    new_df = pd.DataFrame([data_entry])
    
    if os.path.exists(filename):
        try:
            old_df = pd.read_csv(filename)
            combined = pd.concat([old_df, new_df], ignore_index=True)
            combined.to_csv(filename, index=False, encoding='utf-8-sig')
        except Exception:
            # 舊檔讀取失敗時，直接以新資料覆蓋
            new_df.to_csv(filename, index=False, encoding='utf-8-sig')
    else:
        new_df.to_csv(filename, index=False, encoding='utf-8-sig')
    
    return db_success


# ==========================================
# --- 5. 讀取歷史紀錄（優先從雲端，降級到本地）---
# ==========================================
def load_user_history(user_name):
    """
    讀取指定使用者的所有歷史健康紀錄。
    
    優先順序：Supabase（雲端）> 本地 CSV > 空 DataFrame
    
    【日期格式修正】
    強制將 Date 欄位統一轉換為 'YYYY-MM-DD' 純字串格式，
    防止 Altair 圖表將日期誤轉為毫秒時間戳導致顯示亂碼。
    """
    # 嘗試從 Supabase 讀取
    supabase = get_supabase()
    if supabase:
        try:
            res = (
                supabase.table("health_logs")
                .select("*")
                .eq("User_Name", user_name)
                .order("Date")
                .execute()
            )
            if res.data:
                df = pd.DataFrame(res.data)
                # 修正：雲端抓下來的日期強制轉為純字串，防止 Altair 時間戳亂碼
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
                return df
        except Exception:
            pass  # 靜默失敗，降級到本地 CSV

    # 降級：從本地 CSV 讀取
    filename = f"health_data_{user_name}.csv"
    if os.path.exists(filename):
        try:
            df = pd.read_csv(filename)
            # 修正：將日期強制格式化為 YYYY-MM-DD 的「純字串」，防止 Altair 轉成毫秒
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            return df
        except Exception:
            return pd.DataFrame()
    
    return pd.DataFrame()


# ==========================================
# --- 6. 保存影像資料（眼部 ROI，供深度學習訓練）---
# ==========================================
def save_roi_for_dl(img_bgr, eye_pts, mean_rt, sleep_hours, user_id):
    """
    保存眼部 ROI 影像供深度學習資料集使用。
    目前為預留介面，可在後續版本實作。
    """
    pass


# ==========================================
# --- 7. 頁面背景設定 ---
# ==========================================
def set_bg_from_local(image_file):
    """
    從本地檔案讀取圖片並設定為 Streamlit 頁面的全螢幕背景。
    找不到圖片時靜默失敗，不影響功能運作。
    """
    try:
        with open(image_file, "rb") as file:
            encoded_string = base64.b64encode(file.read()).decode()
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-image: url("data:image/jpeg;base64,{encoded_string}");
                background-size: cover;
                background-attachment: fixed;
            }}
            [data-testid="stHeader"] {{
                background-color: transparent;
            }}
            h1, h2, h3, h4, h5, h6, p, label, span, .stMarkdown {{
                color: #F8F9FA !important;
                text-shadow: 2px 2px 6px rgba(0, 0, 0, 0.9) !important;
            }}
            input, select, textarea {{
                color: #000000 !important;
                text-shadow: none !important;
            }}
            [data-testid="stAlert"] {{
                background-color: rgba(20, 20, 20, 0.65) !important;
                border-radius: 10px !important;
                backdrop-filter: blur(4px);
            }}
            [data-testid="stSidebar"] {{
                background-color: rgba(15, 15, 15, 0.8) !important;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )
    except FileNotFoundError:
        # bg.png 不存在時靜默跳過，使用預設背景
        pass
