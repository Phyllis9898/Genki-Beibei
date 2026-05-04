# ==========================================
# 檔案名稱：ui_pages.py
# 【純淨雲端版】移除了所有 WebRTC 依賴，解決與 Supabase 的非同步衝突。
# 【專家優化版】Stroop 測驗結束後，全自動將成績寫入 URL 並自動跳轉存檔，消滅手動填表。
# ==========================================

import streamlit as st
import cv2
import numpy as np
import random
import time
import pandas as pd
import urllib.parse
import streamlit.components.v1 as components
import altair as alt

# 匯入核心功能
from core_data import save_full_pipeline_data, load_nutrition_db, go_to, save_roi_for_dl, load_user_history
from core_cv import analyze_dark_circles

# 載入資料庫
db = load_nutrition_db()

# ==========================================
# 頁面一：Landing Page
# ==========================================
def show_landing():
    st.markdown(
        "<br><br><br><h1 style='text-align: center; color: #81C784; font-size: 3.5rem;'>"
        "🌱 肌智量點 雙功能健康顧問</h1>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<h3 style='text-align: center; color: #E0E0E0;'>AI 精準判斷，由內而外的專屬健康守護</h3>"
        "<br><br>",
        unsafe_allow_html=True
    )
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.button("🚀 點此開始", use_container_width=True,
                  on_click=go_to, args=('profile',), type="primary")

# ==========================================
# 頁面二：Profile Page
# ==========================================
def show_profile():
    st.button("⬅️ 返回", on_click=go_to, args=('landing',))
    st.markdown("## 📝 建立您的專屬檔案")

    with st.container():
        name = st.text_input("✨ 您的暱稱", value=st.session_state.user_name)
        col1, col2 = st.columns(2)

        with col1:
            age = st.number_input("🎂 您的年齡", min_value=10, max_value=100,
                                  value=st.session_state.user_age)
        with col2:
            job_list = ["學生", "上班族 (朝九晚五)", "輪班/夜班", "自由業", "其他"]
            current_index = (
                job_list.index(st.session_state.user_job)
                if st.session_state.user_job in job_list else 0
            )
            job = st.selectbox("💼 職業類型", job_list, index=current_index)

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("下一步 👉", use_container_width=True, type="primary"):
            if name.strip() == "":
                st.warning("⚠️ 請輸入您的暱稱喔！")
            else:
                st.session_state.user_name = name
                st.session_state.user_age  = age
                st.session_state.user_job  = job
                go_to('home')

# ==========================================
# 頁面三：Home Page
# ==========================================
def show_home():
    st.button("⬅️ 修改個人資料", on_click=go_to, args=('profile',))
    st.markdown(
        f"<h2 style='color: #81C784;'>👋 歡迎回來，{st.session_state.user_name}！</h2>",
        unsafe_allow_html=True
    )
    st.write("---")

    col1, col2 = st.columns(2)
    with col1:
        st.info("### 📸 模式一 \n #### **✨ 檢測打卡管線** \n "
                "雲端上傳自拍提取特徵，並進行 Stroop 認知專注測試存檔。")
        st.button("👉 啟動【每日檢測打卡】", use_container_width=True,
                  on_click=go_to, args=('analyzer',), type="primary")

    with col2:
        st.warning("### 💻 模式二 \n #### **🐼 陪伴貝貝 (維護中)** \n "
                   "即時視訊監測系統目前正在進行雲端環境升級，暫不開放。")
        st.button("👉 呼叫【陪伴貝貝】 (暫停服務)", use_container_width=True, disabled=True)

    st.write("---")
    st.success("### 📊 模式三 \n #### **📈 健康趨勢儀表板** \n "
               "查看您的所有歷史數據與多維度交叉分析圖表。")
    st.button("👉 查看【健康趨勢儀表板】", use_container_width=True,
              on_click=go_to, args=('dashboard',))

# ==========================================
# 頁面四：Analyzer
# ==========================================
def show_analyzer():
    st.button("⬅️ 取消並返回功能大廳", on_click=go_to, args=('home',))
    st.title("✨ 第一階段：作息與特徵提取")

    col1, col2 = st.columns(2)
    with col1:
        sleep_hours = st.slider("您昨晚睡了幾個小時？", 0.0, 12.0, 7.0, 0.5)
    with col2:
        subjective_fatigue = st.slider(
            "您目前感覺有多疲勞？ (1: 精神飽滿, 10: 極度疲勞)", 1, 10, 5
        )

    uploaded_file = st.file_uploader("請上傳臉部清晰自拍 (JPG/PNG)，支援手機直接拍照", type=["jpg", "png", "jpeg"])

    if uploaded_file is not None:
        with st.spinner('🔍 AI 正在萃取眼周色彩特徵與計算 Delta E...'):
            results, error = analyze_dark_circles(uploaded_file)

        if error:
            st.error(error)
        else:
            col_img1, col_img2 = st.columns(2)
            with col_img1:
                st.image(results["orig"], caption="原始照片", use_container_width=True)
            with col_img2:
                st.image(results["annotated_img"], caption="AI 鎖定分析區域", use_container_width=True)

            st.markdown("### 📋 專屬氣色特徵分析")
            with st.expander("👁️ 暗沉特徵分析與趨勢建議", expanded=True):
                current_delta_E = results['metrics']['delta_E']
                current_ita     = results['metrics'].get('ita', 0)

                st.markdown(f"**🔴 局部色差偏移指數 (CIE Delta E)：`{current_delta_E}`**")
                st.markdown(f"**🔬 膚色光學分級 (ITA Angle)：`{current_ita}°`**")

                if results["has_dark_circles"] and db and results["detected_type"] in db:
                    st.warning(f"⚠️ {st.session_state.user_name}，系統偵測到眼周特徵偏移！")
                    info = db[results["detected_type"]]

                    display_title = (
                        "傾向微血管型暗沉" if results["detected_type"] == "vascular"
                        else "傾向黑色素沉澱暗沉"
                    )
                    st.markdown(f"#### 🔍 特徵判定：{display_title}")
                    st.write("💡 此結果基於色彩空間距離計算，僅供日常觀察參考。")
                    st.markdown("---")

                    rec_fruits = random.sample(info['fruits'], min(2, len(info['fruits'])))
                    rec_herbs  = random.sample(info['herbs'],  min(1, len(info['herbs'])))

                    col_f, col_h = st.columns(2)
                    with col_f:
                        st.markdown("##### 🍎 推薦天然水果")
                        for item in rec_fruits:
                            st.markdown(f"- **{item['name']}**: {item['reason']}")
                    with col_h:
                        st.markdown("##### 🍵 推薦養生茶飲")
                        for item in rec_herbs:
                            st.markdown(f"- **{item['name']}**: {item['reason']}")
                else:
                    st.success(f"✨ {st.session_state.user_name}，您的氣色良好！請繼續保持！")

            st.markdown("---")
            st.warning("⚠️ **特徵提取完成！請進入第二階段進行認知測試。**")

            if st.button("👉 進入【Stroop 史楚普認知測試】", type="primary", use_container_width=True):
                st.session_state.temp_analysis_data = {
                    "sleep_h":      sleep_hours,
                    "fatigue":      subjective_fatigue,
                    "delta_E":      current_delta_E,
                    "orig_bgr":     results["orig_bgr"],
                    "left_eye_pts": results["left_eye_pts"]
                }
                go_to('pvt_game')

# ==========================================
# 頁面五：Stroop Game (全自動回傳版)
# ==========================================
def show_pvt_game():
    if not st.session_state.temp_analysis_data:
        st.error("⚠️ 遺失前置分析數據，請先完成「第一階段檢測」。")
        st.button("⬅️ 返回重測", on_click=go_to, args=('analyzer',))
        return

    st.button("⬅️ 中斷測驗並返回大廳", on_click=go_to, args=('home',))
    st.title("🧠 第二階段：Stroop 史楚普認知測試")
    st.write("這項測試評估您在疲勞時大腦的「抗干擾認知控制能力」。")
    st.info("💡 **遊戲規則：** 畫面中央會出現有顏色的文字，請忽略字面上的意思，**根據「字體的顏色」**點擊下方對應的按鈕！測驗結束後系統會自動為您計算並存檔。")

    d = st.session_state.temp_analysis_data
    safe_user_name = urllib.parse.quote(st.session_state.user_name)

    # 【專家優化】將前置資料注入 JS，並在遊戲結束時自動建構 URL 觸發 main.py 的存檔攔截器
    stroop_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: sans-serif; text-align: center; background: transparent; color: white; margin: 0; padding: 10px; }}
            #game-area {{ width: 100%; height: 280px; background: #2D2D2D; border-radius: 10px; display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; overflow: hidden; }}
            #target-word {{ font-size: 80px; font-weight: bold; display: none; margin-bottom: 20px; text-shadow: 2px 2px 4px rgba(0,0,0,0.5); }}
            .btn-container {{ display: none; gap: 15px; }}
            .color-btn {{ padding: 15px 25px; font-size: 20px; cursor: pointer; border: 2px solid #555; background: #444; color: white; font-weight: bold; border-radius: 8px; transition: transform 0.1s; }}
            .color-btn:active {{ transform: scale(0.95); }}
            #start-btn {{ padding: 15px 30px; font-size: 18px; cursor: pointer; background: #81C784; color: black; font-weight: bold; border-radius: 5px; border: none; margin-top: 15px; }}
            #timer-bar {{ position: absolute; bottom: 0; left: 0; height: 6px; background: #81C784; width: 100%; transition: width 30s linear; }}
            #loading-overlay {{ display: none; position: absolute; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); color:#81C784; font-size: 24px; font-weight: bold; justify-content:center; align-items:center; flex-direction:column; }}
        </style>
    </head>
    <body>
        <div id="game-area">
            <div id="instruction" style="position:absolute; top:15px; color:#aaa; font-size:18px;">請依據「字體的顏色」選擇對應按鈕</div>
            <div id="target-word">紅</div>
            <div class="btn-container" id="btn-group">
                <button class="color-btn" data-color="red"    style="border-bottom: 4px solid #EF5350;">紅色</button>
                <button class="color-btn" data-color="green"  style="border-bottom: 4px solid #66BB6A;">綠色</button>
                <button class="color-btn" data-color="blue"   style="border-bottom: 4px solid #42A5F5;">藍色</button>
                <button class="color-btn" data-color="yellow" style="border-bottom: 4px solid #FFEE58;">黃色</button>
            </div>
            <div id="timer-bar" style="display:none;"></div>
            <div id="loading-overlay">✅ 測驗完成！<br><span style="font-size:16px; color:#fff; margin-top:10px;">系統正在為您自動上傳雲端存檔...</span></div>
        </div>
        <button id="start-btn">🚀 Start Test (30s)</button>

        <script>
            const gameArea   = document.getElementById('game-area');
            const targetWord = document.getElementById('target-word');
            const startBtn   = document.getElementById('start-btn');
            const timerBar   = document.getElementById('timer-bar');
            const inst       = document.getElementById('instruction');
            const btnGroup   = document.getElementById('btn-group');
            const loadingOverlay = document.getElementById('loading-overlay');
            const colorBtns  = document.querySelectorAll('.color-btn');

            const words  = ['紅', '綠', '藍', '黃'];
            const colors = [
                {{ id: 'red',    hex: '#EF5350' }},
                {{ id: 'green',  hex: '#66BB6A' }},
                {{ id: 'blue',   hex: '#42A5F5' }},
                {{ id: 'yellow', hex: '#FFEE58' }}
            ];

            let isRunning      = false;
            let appearanceTime = 0;
            let currentColorId = '';
            let rtArray        = [];
            let lapses         = 0;
            let falseStarts    = 0;

            function nextRound() {{
                if (!isRunning) return;
                let randomWord  = words[Math.floor(Math.random() * words.length)];
                let randomColor = colors[Math.floor(Math.random() * colors.length)];
                targetWord.innerText     = randomWord;
                targetWord.style.color   = randomColor.hex;
                currentColorId           = randomColor.id;
                targetWord.style.display = 'block';
                appearanceTime           = performance.now();
            }}

            colorBtns.forEach(btn => {{
                btn.addEventListener('mousedown', (e) => {{
                    if (!isRunning) return;
                    let clickedColor = e.target.getAttribute('data-color');
                    let rt = performance.now() - appearanceTime;

                    if (clickedColor === currentColorId) {{
                        rtArray.push(rt);
                        inst.innerText    = `✔️ 正確! 反應: ${{Math.round(rt)}} ms`;
                        inst.style.color  = '#81C784';
                    }} else {{
                        falseStarts++;
                        inst.innerText   = `❌ 錯誤! 大腦被干擾了`;
                        inst.style.color = '#EF5350';
                    }}

                    if (rt > 1500) {{ lapses++; }}
                    targetWord.style.display = 'none';
                    setTimeout(nextRound, 300);
                }});
            }});

            startBtn.addEventListener('click', () => {{
                startBtn.style.display  = 'none';
                inst.innerText          = '測驗進行中... 請忽略字義，點擊「顏色」！';
                inst.style.color        = '#aaa';
                btnGroup.style.display  = 'flex';
                timerBar.style.display  = 'block';
                timerBar.style.transition = 'none';
                timerBar.style.width    = '100%';

                setTimeout(() => {{
                    timerBar.style.transition = 'width 30s linear';
                    timerBar.style.width      = '0%';
                }}, 50);

                isRunning = true;
                nextRound();

                setTimeout(() => {{
                    isRunning = false;
                    targetWord.style.display = 'none';
                    inst.style.display       = 'none';
                    btnGroup.style.display   = 'none';
                    timerBar.style.display   = 'none';
                    loadingOverlay.style.display = 'flex';

                    let meanRT = rtArray.length > 0 ? Math.round(rtArray.reduce((a,b)=>a+b,0)/rtArray.length) : 0;
                    
                    // 【關鍵行為】建構 URL 讓父層 iframe 重新載入，觸發 main.py 的 API 攔截
                    let currentUrl = new URL(window.parent.location.href);
                    currentUrl.searchParams.set('save', '1');
                    currentUrl.searchParams.set('u', '{safe_user_name}');
                    currentUrl.searchParams.set('sl', '{d["sleep_h"]}');
                    currentUrl.searchParams.set('fa', '{d["fatigue"]}');
                    currentUrl.searchParams.set('de', '{d["delta_E"]}');
                    currentUrl.searchParams.set('rt', meanRT);
                    currentUrl.searchParams.set('la', lapses);
                    currentUrl.searchParams.set('fs', falseStarts);
                    
                    window.parent.location.href = currentUrl.toString();

                }}, 30000);
            }});
        </script>
    </body>
    </html>
    """
    components.html(stroop_html, height=400)
    # 移除了原本所有手動輸入的 st.number_input 表單！

# ==========================================
# 頁面六：Dashboard (保持不變，直接復用)
# ==========================================
def show_dashboard():
    st.button("⬅️ 返回功能大廳", on_click=go_to, args=('home',))
    st.title("📊 專屬健康趨勢與動態探索")

    df = load_user_history(st.session_state.user_name)

    if df.empty:
        st.warning("⚠️ 目前還沒有足夠的歷史資料喔！請先至「檢測打卡管線」進行檢測並儲存數據。")
        return

    try:
        numeric_cols = [
            'Sleep_Hours', 'Fatigue_Level', 'Delta_E', 'Delta_E_Change',
            'Mean_RT', 'Fastest_RT', 'Slowest_RT', 'Lapses', 'False_Starts'
        ]
        available_cols = [c for c in numeric_cols if c in df.columns]

        daily_df   = df.groupby('Date')[available_cols].mean().reset_index()
        daily_df   = daily_df.sort_values('Date', ascending=True)
        plot_data  = daily_df.copy()

        metric_dict = {
            'Sleep_Hours':   '💤 睡眠時間 (小時)',
            'Fatigue_Level': '🥱 主觀疲勞度 (1-10)',
            'Delta_E':       '👁️ 黑眼圈濃度 (Delta E)',
            'Mean_RT':       '⚡ 平均反應時間 (ms)',
            'Fastest_RT':    '🚀 最快反應時間 (ms)',
            'Slowest_RT':    '🐢 最慢反應時間 (ms)',
            'Lapses':        '❌ 嚴重遲緩 (次)',
            'False_Starts':  '⚠️ 認知錯誤 (次)'
        }

        valid_metrics = [k for k in metric_dict.keys() if k in available_cols]

        st.markdown("---")
        st.markdown("#### 1. 🔍 自訂多模態資料探索 (互動式雙 Y 軸)")
        if len(valid_metrics) >= 2:
            col_sel1, col_sel2 = st.columns(2)
            with col_sel1:
                default_y1 = valid_metrics.index('Sleep_Hours') if 'Sleep_Hours' in valid_metrics else 0
                y1_col = st.selectbox("📊 選擇基礎指標", valid_metrics, index=default_y1, format_func=lambda x: metric_dict[x])
            with col_sel2:
                default_y2 = valid_metrics.index('Mean_RT') if 'Mean_RT' in valid_metrics else 1
                y2_col = st.selectbox("📈 選擇對照指標", valid_metrics, index=default_y2, format_func=lambda x: metric_dict[x])

            base = alt.Chart(plot_data).encode(x=alt.X('Date:O', sort=None, title='檢測日期', axis=alt.Axis(labelAngle=-45)))
            bar = base.mark_bar(opacity=0.5, color="#42A5F5", cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(y=alt.Y(f'{y1_col}:Q', title=metric_dict[y1_col], scale=alt.Scale(zero=True)))
            line = base.mark_line(color="#EF5350", strokeWidth=3, point=alt.OverlayMarkDef(color="#EF5350", size=80)).encode(y=alt.Y(f'{y2_col}:Q', title=metric_dict[y2_col], scale=alt.Scale(zero=False)))

            dual_chart = (alt.layer(bar, line).resolve_scale(y='independent').properties(height=380).configure_axis(labelColor='#E0E0E0', titleColor='#E0E0E0', gridColor='rgba(255, 255, 255, 0.1)').configure_view(strokeWidth=0))
            st.altair_chart(dual_chart, use_container_width=True)

        with st.expander("📝 點此查看詳細歷史數據表"):
            st.dataframe(df.iloc[::-1].reset_index(drop=True), use_container_width=True)

    except Exception as e:
        st.error(f"繪製圖表時發生錯誤：{e}")