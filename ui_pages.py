# ============================================================
#  ui_pages.py  —  Genki Beibei v2.3 (Hardened UX Edition)
# ============================================================
from __future__ import annotations
import json
import urllib.parse

import streamlit as st
import pandas as pd
import altair as alt
import streamlit.components.v1 as components

from core_data import (
    load_nutrition_db,
    go_to,
    load_user_history,
    compute_user_baseline,
    compute_relative_change,
    make_nonce,
)
from core_cv import analyze_dark_circles

db = load_nutrition_db()


# ============================================================
#  Landing
# ============================================================
def show_landing() -> None:
    st.markdown(
        "<br><br><br><h1 style='text-align:center; color:#81C784; font-size:3.5rem;'>"
        "🌱 元氣貝貝 Genki Beibei</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<h3 style='text-align:center; color:#E0E0E0;'>"
        "電腦視覺 × 認知科學 — 由內而外的健康監測</h3><br><br>",
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.button(
            "🚀 點此開始",
            use_container_width=True,
            on_click=go_to,
            args=("profile",),
            type="primary",
        )


# ============================================================
#  Profile / Auth
# ============================================================
def show_profile() -> None:
    st.button("⬅️ 返回", on_click=go_to, args=("landing",))
    st.markdown("## 🔐 受試者身份鑑權系統")
    st.caption(
        "為避免不同受試者使用相同暱稱導致縱向數據遺失與交叉污染，"
        "系統已啟用專屬密碼隔離機制（bcrypt 強雜湊）。"
    )

    auth_mode = st.radio(
        "請選擇操作功能：",
        ["已有帳號登入", "註冊新受試者帳號"],
        horizontal=True,
    )

    name = st.text_input(
        "✨ 受試者唯一暱稱 (建議使用英文字母與數字組合)",
        value=st.session_state.user_name,
    )
    password = st.text_input(
        "🔑 安全驗證密碼",
        type="password",
        help="註冊新帳號時設定的密碼（至少 6 字元），登入時請輸入對應密碼。",
    )

    col1, col2 = st.columns(2)
    with col1:
        age = st.number_input(
            "🎂 您的年齡",
            min_value=10, max_value=100,
            value=st.session_state.user_age,
        )
    with col2:
        job_list = ["學生", "上班族 (朝九晚五)", "輪班/夜班", "自由業", "其他"]
        idx = job_list.index(st.session_state.user_job) if st.session_state.user_job in job_list else 0
        job = st.selectbox("💼 職業類型", job_list, index=idx)

    btn_label = "確認驗證並登入 👉" if auth_mode == "已有帳號登入" else "完成註冊並建立檔案 👉"

    if st.button(btn_label, use_container_width=True, type="primary"):
        if not name.strip() or not password.strip():
            st.warning("⚠️ 暱稱與密碼欄位皆不可為空白喔！")
            return

        from core_data import register_user, login_user

        clean_name = name.strip()
        clean_pwd = password.strip()

        if auth_mode == "註冊新受試者帳號":
            success, msg = register_user(clean_name, clean_pwd)
            if success:
                st.success(f"🎉 註冊成功！已自動為您登入身分：{clean_name}")
                st.session_state.user_name = clean_name
                st.session_state.user_age = int(age)
                st.session_state.user_job = job
                st.session_state.logged_in = True
                go_to("home")
            else:
                st.error(f"❌ {msg}")
        else:
            success, msg = login_user(clean_name, clean_pwd)
            if success:
                st.success(f"🎉 登入成功！歡迎回來，受試者：{clean_name}")
                st.session_state.user_name = clean_name
                st.session_state.user_age = int(age)
                st.session_state.user_job = job
                st.session_state.logged_in = True
                go_to("home")
            else:
                st.error(f"❌ {msg}")


# ============================================================
#  Home
# ============================================================
def show_home() -> None:
    # 登出按鈕：清空敏感 state
    def _logout():
        for k in ("user_name", "temp_analysis_data", "logged_in"):
            st.session_state[k] = "" if k == "user_name" else (None if k == "temp_analysis_data" else False)
        st.session_state.page = "profile"

    st.button("⬅️ 登出並返回登入頁", on_click=_logout)
    st.markdown(
        f"<h2 style='color:#81C784;'>👋 歡迎回來，受試者 {st.session_state.user_name}！</h2>",
        unsafe_allow_html=True,
    )
    st.write("---")

    col1, col2 = st.columns(2)
    with col1:
        st.info(
            "### 📸 模式一\n"
            "#### **✨ 檢測打卡管線**\n"
            "雲端上傳自拍 → 萃取雙眼周色彩特徵 → 進行認知反應測驗 → 自動存檔。"
        )
        st.button(
            "👉 啟動【每日檢測打卡】",
            use_container_width=True,
            on_click=go_to, args=("analyzer",),
            type="primary",
        )

    with col2:
        st.warning(
            "### 💻 模式二\n"
            "#### **🐼 陪伴貝貝 (維護中)**\n"
            "即時視訊監測系統目前正在進行雲端環境升級，暫不開放。"
        )
        st.button(
            "👉 呼叫【陪伴貝貝】 (暫停服務)",
            use_container_width=True,
            disabled=True,
        )

    st.write("---")
    st.success(
        "### 📊 模式三\n"
        "#### **📈 健康趨勢儀表板**\n"
        "查看您的歷史紀錄、個人化基準線 (Baseline) 與相對變化量。"
    )
    st.button(
        "👉 查看【健康趨勢儀表板】",
        use_container_width=True,
        on_click=go_to, args=("dashboard",),
    )


# ============================================================
#  Analyzer (CV)
# ============================================================
def show_analyzer() -> None:
    st.button("⬅️ 取消並返回功能大廳", on_click=go_to, args=("home",))
    st.title("✨ 第一階段：作息與眼周特徵提取")

    col1, col2 = st.columns(2)
    with col1:
        sleep_hours = st.slider("您昨晚睡了幾個小時？", 0.0, 12.0, 7.0, 0.5)
    with col2:
        subjective_fatigue = st.slider(
            "您目前感覺有多疲勞？ (1: 精神飽滿, 10: 極度疲勞)",
            1, 10, 5,
        )

    st.markdown("##### 🧪 選擇第二階段認知測驗模式")
    mode_label = st.radio(
        "選擇您偏好的測驗方式：",
        ["Stroop 顏色干擾測驗（推薦：互動活潑）", "PVT-B 紅點反應測驗（傳統：疲勞敏感）"],
        horizontal=True,
        index=0 if st.session_state.test_mode == "stroop" else 1,
    )
    st.session_state.test_mode = "stroop" if "Stroop" in mode_label else "pvt"

    uploaded_file = st.file_uploader(
        "請上傳臉部清晰自拍 (JPG/PNG)，建議自然光、無瀏海遮擋",
        type=["jpg", "png", "jpeg"],
    )

    if uploaded_file is None:
        return

    with st.spinner("🔍 AI 正在萃取雙眼周色彩特徵與計算 ΔE…"):
        results, error = analyze_dark_circles(uploaded_file)

    if error:
        st.error(error)
        return

    col_a, col_b = st.columns(2)
    with col_a:
        st.image(results["orig"], caption="原始照片", use_container_width=True)
    with col_b:
        st.image(
            results["annotated_img"],
            caption="AI 鎖定分析區域 (藍=左眼  黃=右眼  綠=臉頰)",
            use_container_width=True,
        )

    metrics = results["metrics"]
    st.markdown("### 📋 雙眼對稱採樣分析結果")
    cA, cB, cC, cD = st.columns(4)
    cA.metric("綜合 ΔE", metrics["delta_E"])
    cB.metric("左眼 ΔE", metrics["delta_E_left"])
    cC.metric("右眼 ΔE", metrics["delta_E_right"])
    cD.metric("左右不對稱性", metrics["asymmetry"])

    if results["has_dark_circles"] and db and results["detected_type"] in db:
        st.warning(f"⚠️ {st.session_state.user_name}，系統偵測到眼周特徵偏移！")
        display_title = (
            "傾向微血管型暗沉" if results["detected_type"] == "vascular"
            else "傾向黑色素沉澱暗沉"
        )
        st.markdown(f"#### 🔍 特徵判定：{display_title}")
    else:
        st.success(f"✨ {st.session_state.user_name}，您的氣色良好！請繼續保持！")

    st.markdown("---")
    next_label = (
        "Stroop 干擾測驗"
        if st.session_state.test_mode == "stroop"
        else "PVT-B 反應時間測驗"
    )
    st.warning(f"⚠️ **特徵提取完成！請進入第二階段【{next_label}】**")

    if st.button(
        f"👉 進入【{next_label}】",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.temp_analysis_data = {
            "sleep_h":       sleep_hours,
            "fatigue":       subjective_fatigue,
            "delta_E":       metrics["delta_E"],
            "delta_E_left":  metrics["delta_E_left"],
            "delta_E_right": metrics["delta_E_right"],
            "asymmetry":     metrics["asymmetry"],
        }
        go_to("pvt_game")


# ============================================================
#  PVT-B / Stroop 認知測驗
# ============================================================
def show_pvt_game() -> None:
    if not st.session_state.temp_analysis_data:
        st.error("⚠️ 遺失前置分析數據，請先完成「第一階段檢測」。")
        st.button("⬅️ 返回重測", on_click=go_to, args=("analyzer",))
        return

    st.button("⬅️ 中斷測驗並返回大廳", on_click=go_to, args=("home",))
    mode = st.session_state.test_mode

    if mode == "pvt":
        st.title("🧠 第二階段：PVT-B 簡易反應時間測驗")
        st.info(
            "💡 **規則：** 當紅色刺激出現時，**盡可能快**按下「反應」按鈕。"
            "5 次練習後正式開始 3 分鐘測驗。"
        )
    else:
        st.title("🧠 第二階段：Stroop 干擾測驗")
        st.info(
            "💡 **規則：** 忽略字義，**依字色**選擇對應顏色按鈕。"
            "5 次練習後正式開始 3 分鐘測驗。"
        )

    d = st.session_state.temp_analysis_data
    user_raw = st.session_state.user_name or ""
    safe_user = urllib.parse.quote(user_raw, safe="")

    prefill = {
        "sleep_h": float(d["sleep_h"]),
        "fatigue": int(d["fatigue"]),
        "delta_E": float(d["delta_E"]),
    }

    # ------- 預先簽章：因為 RT 等欄位要等 JS 跑完才知道，
    # 這裡先簽 prefill 部分，JS 端 finishTest 用 fetch 將完整資料 POST 是更安全的做法；
    # 但受限於 Streamlit iframe，仍走 URL 模式。為了讓全欄位都被簽章，
    # 我們將「全部欄位」一併嵌入 JS，由 Python 端在 JS 字串裡固定一份完整 nonce。
    # 改進策略：把 nonce 計算直接搬到 JS 跑完後產出之前──
    # 但因 JS 無法存取 HMAC_SECRET，所以採折衷方案：
    #   prefill 部分（u, sleep_h, fatigue, delta_E）由 Python 簽章；
    #   後端在 main.py 中對 RT 等欄位做嚴格範圍驗證 + 登入態檢查。
    # 這是 iframe 限制下的最佳安全平衡。
    pre_payload = {"u": user_raw, **prefill}
    pre_nonce = make_nonce(pre_payload)

    is_stroop_js = "true" if mode == "stroop" else "false"

    # 將 prefill 序列化為 JS 字面值（防止 XSS）
    sleep_js   = json.dumps(prefill["sleep_h"])
    fatigue_js = json.dumps(prefill["fatigue"])
    delta_e_js = json.dumps(prefill["delta_E"])
    user_js    = json.dumps(safe_user)
    nonce_js   = json.dumps(pre_nonce)

    stroop_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; text-align:center; background:transparent; color:#fff; margin:0; padding:10px; }}
  #game-area {{ width:100%; height:340px; background:#2D2D2D; border-radius:10px;
                display:flex; flex-direction:column; align-items:center; justify-content:center;
                position:relative; overflow:hidden; }}
  #stim {{ font-size:80px; font-weight:bold; display:none; margin-bottom:20px;
           text-shadow:2px 2px 4px rgba(0,0,0,.5); }}
  #pvt-dot {{ width:80px; height:80px; border-radius:50%; background:#EF5350; display:none; }}
  .btn-container {{ display:none; gap:15px; flex-wrap:wrap; justify-content:center; }}
  .color-btn, #pvt-btn {{ padding:14px 22px; font-size:18px; cursor:pointer;
                          border:2px solid #555; background:#444; color:#fff; font-weight:bold;
                          border-radius:8px; transition:transform .1s; }}
  .color-btn:active, #pvt-btn:active {{ transform:scale(.95); }}
  #start-btn {{ padding:15px 30px; font-size:18px; cursor:pointer; background:#81C784;
                color:#000; font-weight:bold; border-radius:5px; border:none; margin-top:15px; }}
  #timer-bar {{ position:absolute; bottom:0; left:0; height:6px; background:#81C784;
                width:100%; transition:width 180s linear; }}
  #inst {{ position:absolute; top:12px; color:#aaa; font-size:16px; }}
  #counter {{ position:absolute; top:12px; right:14px; color:#bbb; font-size:14px; }}
  #overlay {{ display:none; position:absolute; top:0; left:0; width:100%; height:100%;
              background:rgba(15,15,15,.95); color:#81C784; font-size:22px; font-weight:bold;
              justify-content:center; align-items:center; flex-direction:column; padding:20px; }}
</style>
</head>
<body>
  <div id="game-area">
    <div id="inst">點擊「Start」開始 5 次練習</div>
    <div id="counter"></div>
    <div id="stim">紅</div>
    <div id="pvt-dot"></div>
    <div class="btn-container" id="btn-group">
      <button class="color-btn" data-color="red"    style="border-bottom:4px solid #EF5350;">紅</button>
      <button class="color-btn" data-color="green"  style="border-bottom:4px solid #66BB6A;">綠</button>
      <button class="color-btn" data-color="blue"   style="border-bottom:4px solid #42A5F5;">藍</button>
      <button class="color-btn" data-color="yellow" style="border-bottom:4px solid #FFEE58;">黃</button>
    </div>
    <button id="pvt-btn" style="display:none;">⚡ 反應</button>
    <div id="timer-bar" style="display:none;"></div>
    <div id="overlay"></div>
  </div>
  <button id="start-btn">🚀 Start (5 練習 + 3 分鐘)</button>

<script>
  const IS_STROOP    = {is_stroop_js};
  const PRACTICE_N   = 5;
  const TEST_MS      = 180000;
  const ISI_MIN      = IS_STROOP ? 800  : 2000;
  const ISI_MAX      = IS_STROOP ? 1500 : 10000;
  const FALSE_START  = 100;
  const LAPSE_THRESH = 500;

  const PREFILL_SLEEP   = {sleep_js};
  const PREFILL_FATIGUE = {fatigue_js};
  const PREFILL_DELTA_E = {delta_e_js};
  const SAFE_USER       = {user_js};
  const PRE_NONCE       = {nonce_js};

  const words   = ['紅','綠','藍','黃'];
  const colors  = [
    {{ id:'red',    hex:'#EF5350' }},
    {{ id:'green',  hex:'#66BB6A' }},
    {{ id:'blue',   hex:'#42A5F5' }},
    {{ id:'yellow', hex:'#FFEE58' }},
  ];

  const stim   = document.getElementById('stim');
  const dot    = document.getElementById('pvt-dot');
  const inst   = document.getElementById('inst');
  const counter= document.getElementById('counter');
  const grp    = document.getElementById('btn-group');
  const pvtBtn = document.getElementById('pvt-btn');
  const startBtn = document.getElementById('start-btn');
  const timerBar = document.getElementById('timer-bar');
  const overlay  = document.getElementById('overlay');

  let isRunning = false;
  let isPractice = true;
  let practiceLeft = PRACTICE_N;
  let appearanceTime = 0;
  let currentColorId = '';
  let isCongruent = false;
  let waitingForResponse = false;
  let testStartAt = 0;

  let rtAll = [];
  let rtCongruent = [];
  let rtIncongruent = [];
  let lapses = 0;
  let falseStarts = 0;
  let validTrials = 0;
  let pendingTimer = null;

  function rand(a, b) {{ return a + Math.random() * (b - a); }}

  function showCounterText() {{
    if (isPractice) counter.innerText = '練習 ' + (PRACTICE_N - practiceLeft + 1) + '/' + PRACTICE_N;
    else            counter.innerText = '已記錄 ' + validTrials + ' 試';
  }}

  function scheduleNext() {{
    if (!isRunning) return;
    const isi = rand(ISI_MIN, ISI_MAX);
    pendingTimer = setTimeout(presentStim, isi);
  }}

  function presentStim() {{
    if (!isRunning) return;
    waitingForResponse = true;
    showCounterText();
    if (IS_STROOP) {{
      const w = words[Math.floor(Math.random() * 4)];
      const c = colors[Math.floor(Math.random() * 4)];
      stim.innerText = w;
      stim.style.color = c.hex;
      stim.style.display = 'block';
      currentColorId = c.id;
      const wIdx = words.indexOf(w);
      isCongruent = (colors[wIdx].id === c.id);
    }} else {{
      dot.style.display = 'block';
    }}
    appearanceTime = performance.now();
  }}

  function recordResponse(correct, rt) {{
    if (rt < FALSE_START) {{
      // 練習階段不計入 false start，避免污染正式成績
      if (!isPractice) falseStarts++;
      return;
    }}
    if (!correct) {{
      if (!isPractice) falseStarts++;
      return;
    }}

    if (isPractice) {{
      practiceLeft--;
      if (practiceLeft <= 0) {{
        isPractice = false;
        testStartAt = performance.now();
        inst.innerText = IS_STROOP ?
          '🎯 正式測驗中 — 依「字體顏色」回應' :
          '🎯 正式測驗中 — 看到紅點立刻按反應';
        timerBar.style.display = 'block';
        timerBar.style.transition = 'none';
        timerBar.style.width = '100%';
        setTimeout(() => {{
          timerBar.style.transition = 'width ' + TEST_MS + 'ms linear';
          timerBar.style.width = '0%';
        }}, 50);
        setTimeout(finishTest, TEST_MS);
      }}
      return;
    }}
    validTrials++;
    rtAll.push(rt);
    if (IS_STROOP) {{
      if (isCongruent) rtCongruent.push(rt);
      else             rtIncongruent.push(rt);
    }}
    if (rt >= LAPSE_THRESH) lapses++;
  }}

  function handleResponse(clickedColor) {{
    if (!isRunning || !waitingForResponse) return;
    const rt = performance.now() - appearanceTime;
    let correct;
    if (IS_STROOP) {{
      correct = (clickedColor === currentColorId);
      stim.style.display = 'none';
    }} else {{
      correct = true;
      dot.style.display = 'none';
    }}
    waitingForResponse = false;
    recordResponse(correct, rt);
    scheduleNext();
  }}

  document.querySelectorAll('.color-btn').forEach(b => {{
    b.addEventListener('mousedown', e => handleResponse(e.currentTarget.getAttribute('data-color')));
  }});
  pvtBtn.addEventListener('mousedown', () => handleResponse('any'));

  // 提前按壓（沒有刺激時的搶按）：僅在正式測驗中計入 false start
  document.addEventListener('mousedown', e => {{
    if (isRunning && !waitingForResponse && !isPractice) {{
      if (e.target.closest('.color-btn') || e.target === pvtBtn) {{
        falseStarts++;
      }}
    }}
  }});

  function finishTest() {{
    isRunning = false;
    if (pendingTimer) clearTimeout(pendingTimer);
    stim.style.display = 'none';
    dot.style.display = 'none';
    grp.style.display = 'none';
    pvtBtn.style.display = 'none';
    timerBar.style.display = 'none';
    inst.style.display = 'none';
    counter.style.display = 'none';
    overlay.style.display = 'flex';

    const meanRT  = rtAll.length        ? rtAll.reduce((a,b)=>a+b,0)/rtAll.length        : 0;
    const meanCon = rtCongruent.length  ? rtCongruent.reduce((a,b)=>a+b,0)/rtCongruent.length : 0;
    const meanInc = rtIncongruent.length? rtIncongruent.reduce((a,b)=>a+b,0)/rtIncongruent.length : 0;
    const interference = (IS_STROOP && rtCongruent.length && rtIncongruent.length)
                          ? (meanInc - meanCon) : 0;

    function safe(v, lo, hi) {{
      if (!isFinite(v)) return 0;
      return Math.min(Math.max(v, lo), hi);
    }}
    const out = {{
      sleep_h:        PREFILL_SLEEP,
      fatigue:        PREFILL_FATIGUE,
      delta_E:        PREFILL_DELTA_E,
      rt_mean:        Math.round(safe(meanRT, 0, 5000)),
      rt_congruent:   Math.round(safe(meanCon, 0, 5000)),
      rt_incongruent: Math.round(safe(meanInc, 0, 5000)),
      interference:   Math.round(safe(interference, -2000, 2000)),
      lapses:         Math.min(lapses, 1000),
      false_starts:   Math.min(falseStarts, 1000),
      valid_trials:   Math.min(validTrials, 5000),
    }};

    // 以 parent 視窗的 origin + pathname 建立 URL，避免 iframe 內 location 解析錯誤
    let baseUrl;
    try {{
      baseUrl = window.parent.location.origin + window.parent.location.pathname;
    }} catch (e) {{
      baseUrl = window.location.origin + window.location.pathname;
    }}
    const url = new URL(baseUrl);
    url.searchParams.set('save', '1');
    url.searchParams.set('u',  SAFE_USER);
    url.searchParams.set('sl', out.sleep_h);
    url.searchParams.set('fa', out.fatigue);
    url.searchParams.set('de', out.delta_E);
    url.searchParams.set('rt', out.rt_mean);
    url.searchParams.set('rc', out.rt_congruent);
    url.searchParams.set('ri', out.rt_incongruent);
    url.searchParams.set('it', out.interference);
    url.searchParams.set('la', out.lapses);
    url.searchParams.set('fs', out.false_starts);
    url.searchParams.set('vt', out.valid_trials);
    url.searchParams.set('nc', PRE_NONCE);

    // 解決自動跳轉卡死問題：生成帶有 target='_top' 的玻璃帷幕手動跳轉按鈕
    const finalUrl = url.toString();
    overlay.innerHTML =
      "<div>" +
      "<p style='font-size:24px; color:#81C784; font-weight:bold;'>✅ 測驗完成！</p>" +
      "<p style='font-size:15px; color:#bbb;'>數據計算完畢，請點此按鈕強制寫入雲端並同步至健康趨勢表。</p>" +
      "<a href='" + finalUrl + "' target='_top' style='display:inline-block; margin-top:20px; padding:14px 32px; background-color:#81C784; color:#000; text-decoration:none; border-radius:8px; font-weight:bold; font-size:18px; box-shadow:0 4px 15px rgba(0,0,0,0.5); transition:transform 0.1s;'>📊 點此確認資料庫同步</a>" +
      "</div>";

    // 嘗試自動跳轉（被 sandbox 封鎖則 fallback 至上方手動按鈕）
    try {{ window.parent.location.href = finalUrl; }}
    catch (e) {{ console.log("Iframe automatic redirect blocked; fallback to manual button."); }}
  }}

  startBtn.addEventListener('click', () => {{
    startBtn.style.display = 'none';
    inst.innerText = IS_STROOP ?
      '📝 練習階段：依「字體顏色」點擊按鈕' :
      '📝 練習階段：看到紅點立刻按反應';
    if (IS_STROOP) grp.style.display = 'flex';
    else           pvtBtn.style.display = 'inline-block';
    isRunning = true;
    isPractice = true;
    practiceLeft = PRACTICE_N;
    scheduleNext();
  }});
</script>
</body>
</html>
"""
    components.html(stroop_html, height=460)


# ============================================================
#  Dashboard
# ============================================================
def show_dashboard() -> None:
    st.button("⬅️ 返回功能大廳", on_click=go_to, args=("home",))
    st.title("📊 專屬健康趨勢與基準線分析")

    df = load_user_history(st.session_state.user_name)
    if df.empty:
        st.warning("⚠️ 目前尚無歷史資料，請先完成一次「每日檢測打卡」。")
        return

    # ---- Baseline ----
    baseline = compute_user_baseline(df, n_days=3)
    if baseline:
        st.markdown("#### 🧭 個人化基準線 (前 3 次中位數)")
        cols = st.columns(len(baseline))
        for (k, v), c in zip(baseline.items(), cols):
            c.metric(k, f"{v:.1f}" if isinstance(v, float) else str(v))

        latest = df.sort_values("Date").iloc[-1]
        st.markdown("##### 📐 最新檢測相對基準的變化量")
        ccols = st.columns(len(baseline))
        for (k, base_v), c in zip(baseline.items(), ccols):
            if k in latest.index and pd.notna(latest[k]):
                delta = compute_relative_change(float(latest[k]), base_v)
                if delta is None:
                    c.metric(k + " Δ%", "—")
                else:
                    c.metric(k + " Δ%", f"{delta:+.1f}%")
            else:
                c.metric(k + " Δ%", "—")

    st.markdown("---")
    st.markdown("#### 🔍 多指標交叉趨勢")

    try:
        numeric_cols = [
            "Sleep_Hours", "Fatigue_Level",
            "Delta_E", "Delta_E_Left", "Delta_E_Right", "Asymmetry",
            "Mean_RT", "RT_Congruent", "RT_Incongruent", "Interference",
            "Lapses", "False_Starts", "Valid_Trials",
        ]
        available_cols = [c for c in numeric_cols if c in df.columns]
        if not available_cols:
            st.info("尚無數值欄位可繪圖。")
            return

        # 將數值欄位強制轉成 numeric，避免字串混入導致 mean() 拋例外
        for c in available_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        # 修補：以日期（年月日）聚合而非完整 timestamp，否則每次紀錄都會自成一群
        df["_DateOnly"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        daily_df = (
            df.groupby("_DateOnly")[available_cols]
              .mean()
              .reset_index()
              .rename(columns={"_DateOnly": "Date"})
              .sort_values("Date")
        )

        metric_dict = {
            "Sleep_Hours":    "💤 睡眠時間 (小時)",
            "Fatigue_Level":  "🥱 主觀疲勞度 (1-10)",
            "Delta_E":        "👁️ 眼周 ΔE (綜合)",
            "Delta_E_Left":   "👁️◐ 左眼 ΔE",
            "Delta_E_Right":  "👁️◑ 右眼 ΔE",
            "Asymmetry":      "↔️ 左右不對稱性",
            "Mean_RT":        "⚡ 平均反應時間 (ms)",
            "RT_Congruent":   "✅ 一致試驗 RT",
            "RT_Incongruent": "⛔ 不一致試驗 RT",
            "Interference":   "🧠 Stroop Interference",
            "Lapses":         "❌ Lapses (RT≥500ms)",
            "False_Starts":   "⚠️ False Starts",
            "Valid_Trials":   "🎯 有效試驗數",
        }
        valid_metrics = [k for k in metric_dict if k in available_cols]
        if len(valid_metrics) < 2:
            st.info("資料維度不足以繪製雙軸圖表。")
        else:
            col_sel1, col_sel2 = st.columns(2)
            with col_sel1:
                d1 = valid_metrics.index("Sleep_Hours") if "Sleep_Hours" in valid_metrics else 0
                y1 = st.selectbox(
                    "📊 基礎指標", valid_metrics, index=d1,
                    format_func=lambda x: metric_dict[x],
                )
            with col_sel2:
                d2 = valid_metrics.index("Mean_RT") if "Mean_RT" in valid_metrics else min(1, len(valid_metrics) - 1)
                y2 = st.selectbox(
                    "📈 對照指標", valid_metrics, index=d2,
                    format_func=lambda x: metric_dict[x],
                )

            base = alt.Chart(daily_df).encode(
                x=alt.X(
                    "Date:O", sort=None, title="檢測日期",
                    axis=alt.Axis(labelAngle=-45),
                )
            )
            bar = base.mark_bar(
                opacity=0.5, color="#42A5F5",
                cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
            ).encode(
                y=alt.Y(
                    f"{y1}:Q", title=metric_dict[y1],
                    scale=alt.Scale(zero=True),
                )
            )
            line = base.mark_line(
                color="#EF5350", strokeWidth=3,
                point=alt.OverlayMarkDef(color="#EF5350", size=80),
            ).encode(
                y=alt.Y(
                    f"{y2}:Q", title=metric_dict[y2],
                    scale=alt.Scale(zero=False),
                )
            )
            chart = (
                alt.layer(bar, line)
                   .resolve_scale(y="independent")
                   .properties(height=380)
                   .configure_axis(
                       labelColor="#E0E0E0",
                       titleColor="#E0E0E0",
                       gridColor="rgba(255,255,255,0.1)",
                   )
                   .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart, use_container_width=True)

        with st.expander("📝 點此查看詳細歷史數據表"):
            display_df = df.drop(columns=["_DateOnly"], errors="ignore")
            st.dataframe(
                display_df.iloc[::-1].reset_index(drop=True),
                use_container_width=True,
            )

    except Exception as e:
        st.error(f"繪製圖表時發生錯誤：{e}")
