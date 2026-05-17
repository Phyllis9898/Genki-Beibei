import streamlit as st
import os
from core_data import go_to, load_user_history, load_nutrition_db, generate_secure_token

def show_home_page():
    st.title("👁️ 元氣貝貝 (Genki Beibei)")
    st.subheader("智能生理眼周色差與精神運動警覺性健康分析系統")
    
    st.info(
        "本系統結合電腦視覺 (MediaPipe Face Mesh) 進行雙眼對稱色差分析，"
        "並搭載睡眠醫學臨床公認的 PVT-B 精神運動警覺性測驗，全方位評估您的真實認知疲勞度。"
    )
    
    # 用戶基礎資料輸入面板
    with st.form("user_info_form"):
        st.write("### 📝 第一步：建立個人當日基準 (Baseline)")
        name = st.text_input("請輸入您的受試者代號或姓名：", value=st.session_state.user_name)
        sleep = st.number_input("昨晚實際睡眠時間 (小時)：", min_value=0.0, max_value=24.0, value=st.session_state.sleep_hours, step=0.5)
        fatigue = st.slider("主觀疲勞自評 (1-10分，分數越高越累)：", min_value=1, max_value=10, value=st.session_state.fatigue_level)
        
        submit_btn = st.form_submit_with_rows() if hasattr(st, "form_submit_with_rows") else st.form_submit_button("儲存基準並前往生理黑眼圈檢測")
        if submit_btn:
            if not name.strip():
                st.error("姓名或代號不能為空！")
            else:
                st.session_state.user_name = name.strip()
                st.session_state.sleep_hours = sleep
                st.session_state.fatigue_level = fatigue
                go_to("cv_analysis")

def show_cv_page():
    st.title("📸 第二步：雙眼周與面頰對稱色差分析")
    st.write(f"受試者姓名：`{st.session_state.user_name}`")
    
    st.warning(
        "💡 採樣環境指南：請確保正面對準鏡頭，面部光線左右均勻。系統已啟動【雙眼算術平均對稱採樣技術】，"
        "若左右光照角度嚴重失衡，系統將自動攔截並發出採樣無效警告，以捍衛學術嚴謹度。"
    )
    
    img_file = st.file_uploader("請上傳或拍攝您的面部清晰正面照片：", type=["jpg", "jpeg", "png"])
    
    if img_file is not None:
        from core_cv import analyze_dark_circles
        with st.spinner("影像流水線啟動中，進行色偏校正與多 ROI 色彩提取..."):
            res, err = analyze_dark_circles(img_file)
            
            if err:
                st.error(err)
            else:
                st.success("🎉 臉部特徵提取與色彩空間矩陣運算成功！")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.image(res["orig"], caption="原始輸入影像", use_container_width=True)
                with col2:
                    st.image(res["annotated_img"], caption="雙眼(紅/藍框)與面頰(綠框)自動採樣 ROI", use_container_width=True)
                
                metrics = res["metrics"]
                st.session_state.delta_e = metrics["delta_e"]
                
                st.write("### 📊 色彩分析報告數據")
                st.metric("核心定量色差值 (Delta E)", f"{metrics['delta_e']} 門檻")
                st.write(f"個體膚色分類 ITA 角度: `{metrics['ita']}°`")
                
                if res["has_dark_circles"]:
                    st.error(f"🚨 系統診斷：眼周與頰部存在顯著色差，初步判定為：【{ '血管型偏紫/青色' if res['detected_type']=='vascular' else '色素型偏褐色' }黑眼圈】。")
                else:
                    st.success("🟢 系統診斷：您的眼周色彩結構處於正常分布範圍內。")
                
                if st.button("完成生理分析，前往 PVT-B 精神控制力測驗"):
                    go_to("pvt_test")
                    
    if st.button("⬅️ 返回首頁修改基準資訊"):
        go_to("home")

def show_pvt_page():
    st.title("🧠 第三步：PVT-B 精神運動警覺性控制力測驗")
    st.write(f"受試者：`{st.session_state.user_name}`")
    
    st.info(
        "【持續性注意力科學檢測】接下來您將進行為時 120 秒的 PVT-B 測試。當畫面上出現「🔴 點擊！」紅色大方塊時，"
        "請以最快速度點擊它。畫面將即時回饋您的反應毫秒數。過於無聊的任務正是逼出真實大腦微睡眠 (Lapses) 的核心關鍵！"
    )
    
    # 生成安全驗證簽章
    secure_token = generate_secure_token(st.session_state.user_name, 0, 0) # 初始佔位或用於基底校驗
    
    # 嵌入高度改良、120秒、具備即時 RT 與進度條回饋的前端 JavaScript 引擎
    pvt_html = f"""
    <div id="pvt-container" style="text-align: center; font-family: sans-serif; background-color: #151515; color: white; padding: 30px; border-radius: 12px; border: 1px solid #333;">
        <div id="pvt-status" style="font-size: 20px; margin-bottom: 15px; font-weight: bold; color: #aaa;">準備就緒，請點擊下方按鈕開始測驗</div>
        
        <div style="width: 100%; background-color: #333; border-radius: 6px; margin-bottom: 20px; height: 12px; overflow: hidden;">
            <div id="pvt-progress" style="width: 0%; height: 100%; background: linear-gradient(90deg, #4CAF50, #2196F3); transition: width 0.2s linear;"></div>
        </div>
        
        <div id="pvt-box" style="width: 280px; height: 180px; background-color: #2a2a2a; margin: 20px auto; border-radius: 10px; display: flex; align-items: center; justify-content: center; cursor: pointer; border: 2px dashed #555; transition: all 0.1s ease;">
            <span id="pvt-box-text" style="font-size: 24px; font-weight: bold; color: #666;">等待開始...</span>
        </div>
        
        <div id="rt-feedback" style="font-size: 28px; font-weight: bold; margin: 15px; min-height: 35px; color: #4CAF50;"></div>
        
        <button id="start-pvt-btn" style="background-color: #2196F3; color: white; border: none; padding: 12px 30px; font-size: 18px; font-weight: bold; border-radius: 6px; cursor: pointer; box-shadow: 0 4px 10px rgba(33,150,243,0.3);">開始 120 秒測試</button>
        
        <div style="margin-top: 20px; font-size: 14px; color: #777;" id="trial-counter">完成試驗次數: 0</div>
    </div>

    <script>
    (function() {{
        const pvtBox = document.getElementById('pvt-box');
        const pvtBoxText = document.getElementById('pvt-box-text');
        const pvtStatus = document.getElementById('pvt-status');
        const rtFeedback = document.getElementById('rt-feedback');
        const startBtn = document.getElementById('start-pvt-btn');
        const progressBar = document.getElementById('pvt-progress');
        const trialCounter = document.getElementById('trial-counter');
        
        let testDuration = 120000; // 鎖定科學微調 120 秒
        let startTime, timeoutId, intervalId;
        let isWaitingForStimulus = false;
        let isTestRunning = false;
        
        let rts = [];
        let lapses = 0;
        let falseStarts = 0;
        let trialsCount = 0;
        let timeLeft = testDuration;
        
        startBtn.onclick = function() {{
            if (isTestRunning) return;
            isTestRunning = true;
            startBtn.style.display = 'none';
            pvtStatus.innerText = "測驗進行中... 請緊盯大方塊！";
            
            // 啟動倒數計時進度條
            const startTimeStamp = Date.now();
            intervalId = setInterval(() => {{
                let elapsed = Date.now() - startTimeStamp;
                let pct = (elapsed / testDuration) * 100;
                if (pct >= 100) {{
                    pct = 100;
                    clearInterval(intervalId);
                    endTest();
                }}
                progressBar.style.width = pct + '%';
            }}, 200);
            
            triggerNextTrial();
        }};
        
        function triggerNextTrial() {{
            if (!isTestRunning) return;
            
            pvtBox.style.backgroundColor = '#2a2a2a';
            pvtBox.style.border = '2px dashed #555';
            pvtBoxText.innerText = "稍安勿躁...";
            pvtBoxText.style.color = '#666';
            isWaitingForStimulus = false;
            
            // 隨機刺激呈現在 2~5 秒之間
            let delay = Math.random() * 3000 + 2000;
            timeoutId = setTimeout(() => {{
                pvtBox.style.backgroundColor = '#f44336'; // 變紅
                pvtBox.style.border = '2px solid #ffc107';
                pvtBoxText.innerText = "🔴 點擊！";
                pvtBoxText.style.color = '#ffffff';
                startTime = Date.now();
                isWaitingForStimulus = true;
            }}, delay);
        }}
        
        pvtBox.onclick = function() {{
            if (!isTestRunning) return;
            
            if (!isWaitingForStimulus) {{
                // 提前點擊：False Start
                clearTimeout(timeoutId);
                falseStarts++;
                rtFeedback.innerText = "❌ 太快了！(算搶答)";
                rtFeedback.style.color = '#ff9800';
                triggerNextTrial();
            }} else {{
                // 正常響應
                let rt = Date.now() - startTime;
                isWaitingForStimulus = false;
                rts.append ? rts.append(rt) : rts.push(rt);
                trialsCount++;
                trialCounter.innerText = "完成試驗次數: " + trialsCount;
                
                // 即時臨床定義反饋 (Lapse 閾值 500ms)
                if (rt > 500) {{
                    lapses++;
                    rtFeedback.innerText = rt + " ms 🔴 (注意力缺失!)";
                    rtFeedback.style.color = '#f44336';
                }} else {{
                    rtFeedback.innerText = rt + " ms 🟢";
                    rtFeedback.style.color = '#4CAF50';
                }}
                
                triggerNextTrial();
            }}
        }};
        
        function endTest() {{
            isTestRunning = false;
            clearTimeout(timeoutId);
            pvtStatus.innerText = "測驗時間到！正在計算安全認證金鑰並回傳...";
            pvtBox.style.backgroundColor = '#4CAF50';
            pvtBoxText.innerText = "完成！";
            
            let sum = 0;
            for(let i=0; i<rts.length; i++) {{ sum += rts[i]; }}
            let avg = rts.length > 0 ? Math.round(sum / rts.length) : 0;
            
            // 計算安全簽章防護防篡改 (與後端密鑰同步)
            // 由於 JS 無法直接讀取 streamlit secret，因此透過預埋的 Token 架構，或者由後端重新運算。
            // 我們在此處直接導向回 main.py 讓後端來驗證並解析。
            
            setTimeout(() => {{
                // 動態組裝安全傳輸 URL
                let targetUrl = window.location.origin + window.location.pathname + 
                    "?save=1&u=" + encodeURIComponent("{st.session_state.user_name}") + 
                    "&rt=" + avg + "&la=" + lapses + "&fs=" + falseStarts + 
                    "&token=" + encodeURIComponent("{secure_token}");
                window.parent.postMessage({{type: 'streamlit:setComponentValue', value: true}}, '*');
                window.top.location.href = targetUrl;
            }}, 1500);
        }}
    }})();
    </script>
    """
    
    st.components.v1.html(pvt_html, height=450)
    
    if st.button("⬅️ 放棄並返回生理黑眼圈檢測頁面"):
        go_to("cv_analysis")

def show_dashboard_page():
    st.title("📊 個人疲勞追蹤與全方位智能健康儀表板")
    st.write(f"當前登入用戶：`{st.session_state.user_name}`")
    
    # 讀取雲端或本地歷史紀錄庫
    df_hist = load_user_history(st.session_state.user_name)
    
    if df_hist.empty:
        st.warning("目前暫無足夠的縱向追蹤數據。請多進行幾次完整的黑眼圈與認知檢測！")
    else:
        st.write("### 🧠 本次檢測臨床摘要結果")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("黑眼圈色差值 (Delta E)", f"{st.session_state.delta_e}")
        with col2:
            st.metric("PVT 平均反應時 (Mean RT)", f"{st.session_state.mean_rt} ms")
        with col3:
            st.metric("微睡眠中斷次數 (Lapses)", f"{st.session_state.lapses} 次")
        with col4:
            st.metric("搶答/分心次數 (False Starts)", f"{st.session_state.false_starts} 次")
            
        # 疲勞綜合評估指標
        st.write("### 📝 臨床警覺性專家綜合評估")
        if st.session_state.lapses >= 3 or st.session_state.mean_rt > 350:
            st.error("🚨 【重度注意力與警覺性衰退警告】：您的 PVT 反應顯著遲緩且伴隨多次微睡眠 (Lapses)，大腦此時正面臨高度睡眠剝奪，強烈建議立即暫停操作任何精密儀器或危險機具，並安排至少 90 分鐘的完整睡眠週期！")
        elif st.session_state.lapses >= 1 or st.session_state.mean_rt > 280:
            st.warning("⚠️ 【輕度認知疲勞警告】：您的持續性注意力開始出現波動。目前的生理色差與反應時顯示大腦處於輕度疲憊狀態，建議起來伸展活動，並補充電解質或適量水分。")
        else:
            st.success("🟢 【大腦警覺度優良】：您的精神控制力極佳，反應時間處於健康人的標準高標。請繼續保持良好的作息！")
            
        # 飲食營養學知識庫推薦 (根據黑眼圈類型與疲勞度進行關聯式推薦)
        st.write("### 🥑 專屬您的智能精準營養學膳食建議")
        nut_db = load_nutrition_db()
        
        if st.session_state.lapses >= 1:
            st.info(f"💡 **針對大腦認知補給**：{nut_db.get('brain_fatigue', '建議多補充富含 Omega-3 的深海魚類以及維生素 B 群，有助於修復神經警覺性與加速多巴胺合成。')}")
        else:
            st.success(f"💡 **維持日常警覺補給**：{nut_db.get('normal_maintenance', '建議攝取適量藍莓（花青素）與堅果（維生素 E），維持大腦抗氧化高屏障。')}")
            
        # 繪製全縱向追蹤圖表 (歷史歷史趨勢分析)
        st.write("### 📈 歷史縱向演化趨勢圖")
        try:
            df_hist["Date_Short"] = pd.to_datetime(df_hist["Date"]).dt.strftime("%m-%d %H:%M")
            chart_data = df_hist.set_index("Date_Short")[["Delta_E", "Mean_RT", "Lapses"]]
            st.line_chart(chart_data)
        except Exception:
            st.write("（趨勢圖表繪製中...請確保資料庫 Date 欄位格式正確）")

    if st.button("🔄 重新進行一次全新的健康檢測流水線"):
        # 清除暫存
        st.session_state.delta_e = 0.0
        st.session_state.mean_rt = 0
        st.session_state.lapses = 0
        st.session_state.false_starts = 0
        go_to("home")