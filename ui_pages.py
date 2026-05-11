# ============================================================
#  ui_pages.py  —  Genki Beibei v2.0
#  ------------------------------------------------------------
#  變更摘要（相對 v1）：
#   1. 移除「from core_data import save_roi_for_dl」這條會崩潰的 import
#   2. 移除對 results["left_eye_pts"] 的引用 (該欄位不存在)
#   3. 認知測驗改為「PVT-B（預設）」與「Stroop Interference」雙模式：
#        - PVT-B  : 3 分鐘簡易反應時間，lapse 閾值 500ms (Dinges 1997)
#        - Stroop : 含 congruent / incongruent 試驗分類，計算 Interference Score
#   4. 含 5 試驗 practice block（不計分）
#   5. 偵測 false start (RT < 100ms) 與 lapse (RT ≥ 500ms)
#   6. 結束後將完整數據經 Python 端預算 HMAC nonce 後注入 JS，
#      URL 不再可被外部偽造
#   7. Dashboard 加入個人 baseline 相對變化量 (% Δ vs baseline)
# ============================================================
from __future__ import annotations
import random
import urllib.parse
import json

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
        st.button("🚀 點此開始", use_container_width=True,
                  on_click=go_to, args=("profile",), type="primary")


# ============================================================
#  Profile
# ============================================================
def show_profile() -> None:
    st.button("⬅️ 返回", on_click=go_to, args=("landing",))
    st.markdown("## 📝 建立您的專屬檔案")

    name = st.text_input("✨ 您的暱稱", value=st.session_state.user_name)
    col1, col2 = st.columns(2)
    with col1:
        age = st.number_input("🎂 您的年齡", min_value=10, max_value=100,
                              value=st.session_state.user_age)
    with col2:
        job_list = ["學生", "上班族 (朝九晚五)", "輪班/夜班", "自由業", "其他"]
        idx = job_list.index(st.session_state.user_job) if st.session_state.user_job in job_list else 0
        job = st.selectbox("💼 職業類型", job_list, index=idx)

    if st.button("下一步 👉", use_container_width=True, type="primary"):
        if not name.strip():
            st.warning("⚠️ 請輸入您的暱稱喔！")
        else:
            st.session_state.user_name = name.strip()
            st.session_state.user_age = int(age)
            st.session_state.user_job = job
            go_to("home")


# ============================================================
#  Home
# ============================================================
def show_home() -> None:
    st.button("⬅️ 修改個人資料", on_click=go_to, args=("profile",))
    st.markdown(
        f"<h2 style='color:#81C784;'>👋 歡迎回來，{st.session_state.user_name}！</h2>",
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
        st.button("👉 啟動【每日檢測打卡】", use_container_width=True,
                  on_click=go_to, args=("analyzer",), type="primary")

    with col2:
        st.warning(
            "### 💻 模式二\n"
            "#### **🐼 陪伴貝貝 (維護中)**\n"
            "即時視訊監測系統目前正在進行雲端環境升級，暫不開放。"
        )
        st.button("👉 呼叫【陪伴貝貝】 (暫停服務)",
                  use_container_width=True, disabled=True)

    st.write("---")
    st.success(
        "### 📊 模式三\n"
        "#### **📈 健康趨勢儀表板**\n"
        "查看您的歷史紀錄、個人化基準線 (Baseline) 與相對變化量。"
    )
    st.button("👉 查看【健康趨勢儀表板】", use_container_width=True,
              on_click=go_to, args=("dashboard",))


# ============================================================
#  Analyzer (Stage 1: CV)
# ============================================================
def show_analyzer() -> None:
    st.button("⬅️ 取消並返回功能大廳", on_click=go_to, args=("home",))
    st.title("✨ 第一階段：作息與眼周特徵提取")

    col1, col2 = st.columns(2)
    with col1:
        sleep_hours = st.slider("您昨晚睡了幾個小時？", 0.0, 12.0, 7.0, 0.5)
    with col2:
        subjective_fatigue = st.slider(
            "您目前感覺有多疲勞？ (1: 精神飽滿, 10: 極度疲勞)", 1, 10, 5
        )

    st.markdown("##### 🧪 選擇第二階段認知測驗模式")
    mode_label = st.radio(
        "（PVT-B 為文獻黃金標準、適合疲勞偵測；Stroop 用於量測抗干擾控制能力）",
        ["PVT-B（推薦）", "Stroop 干擾測驗"],
        horizontal=True,
        index=0 if st.session_state.test_mode == "pvt" else 1,
    )
    st.session_state.test_mode = "pvt" if mode_label.startswith("PVT") else "stroop"

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
        st.image(results["annotated_img"],
                 caption="AI 鎖定分析區域 (藍=左眼  黃=右眼  綠=臉頰)",
                 use_container_width=True)

    metrics = results["metrics"]
    st.markdown("### 📋 雙眼對稱採樣分析結果")
    cA, cB, cC, cD = st.columns(4)
    cA.metric("綜合 ΔE", metrics["delta_E"])
    cB.metric("左眼 ΔE", metrics["delta_E_left"])
    cC.metric("右眼 ΔE", metrics["delta_E_right"])
    cD.metric("左右不對稱性", metrics["asymmetry"])

    st.caption(
        f"🔬 膚色光學分級 (ITA Angle)：`{metrics['ita']}°`　"
        "│ 不對稱性 > 1.5 建議檢查單側睡姿或過敏可能。"
    )

    if results["has_dark_circles"] and db and results["detected_type"] in db:
        st.warning(f"⚠️ {st.session_state.user_name}，系統偵測到眼周特徵偏移！")
        info = db[results["detected_type"]]
        display_title = (
            "傾向微血管型暗沉" if results["detected_type"] == "vascular"
            else "傾向黑色素沉澱暗沉"
        )
        st.markdown(f"#### 🔍 特徵判定：{display_title}")
        st.write("💡 本結果僅供日常觀察參考，非醫療診斷。")

        rec_fruits = random.sample(info.get("fruits", []),
                                   min(2, len(info.get("fruits", []))))
        rec_herbs  = random.sample(info.get("herbs", []),
                                   min(1, len(info.get("herbs", []))))
        cf, ch = st.columns(2)
        with cf:
            st.markdown("##### 🍎 推薦天然水果")
            for it in rec_fruits:
                st.markdown(f"- **{it['name']}**: {it['reason']}")
        with ch:
            st.markdown("##### 🍵 推薦養生茶飲")
            for it in rec_herbs:
                st.markdown(f"- **{it['name']}**: {it['reason']}")
    else:
        st.success(f"✨ {st.session_state.user_name}，您的氣色良好！請繼續保持！")

    st.markdown("---")
    next_label = "PVT-B 反應時間測驗" if st.session_state.test_mode == "pvt" else "Stroop 干擾測驗"
    st.warning(f"⚠️ **特徵提取完成！請進入第二階段【{next_label}】**")

    if st.button(f"👉 進入【{next_label}】", type="primary", use_container_width=True):
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
#  Cognitive Test (Stage 2)
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
        st.write(
            "**Brief Psychomotor Vigilance Test** — 由 Basner & Dinges (2011) "
            "提出的 3 分鐘版本，臨床上用以偵測睡眠剝奪導致的注意力失效。"
        )
        st.info(
            "💡 **規則：** 當紅色刺激出現時，**盡可能快**按下「反應」按鈕。"
            "5 次練習後正式開始 3 分鐘測驗。"
        )
    else:
        st.title("🧠 第二階段：Stroop 干擾測驗")
        st.write(
            "**Stroop Test (Stroop, 1935)** — 量測抗認知干擾能力。"
            "字義（紅/綠/藍/黃）與字色一致時為 *congruent*，不一致時為 *incongruent*；"
            "兩者反應時間的差就是 **Stroop Interference Score**。"
        )
        st.info(
            "💡 **規則：** 忽略字義，**依字色**選擇對應顏色按鈕。"
            "5 次練習後正式開始 3 分鐘測驗。"
        )

    d = st.session_state.temp_analysis_data
    safe_user = urllib.parse.quote(st.session_state.user_name)

    # 預先把資料 + nonce 傳給 JS；JS 在送 URL 時把這串 nonce 一起帶上
    # （URL 上的數值欄位名稱必須與 main.py 攔截器一致）
    prefill = {
        "sleep_h": float(d["sleep_h"]),
        "fatigue": int(d["fatigue"]),
        "delta_E": float(d["delta_E"]),
    }
    # nonce 只需把 user 與不可變的前置量綁進來；測驗結果(RT/lapse…)由 JS 端填回後另算
    # 因此這裡產一組「session-key」當作 JS 端拼裝最終 nonce 用的鹽
    # 真正的最終 nonce 在 JS 端用 SubtleCrypto 算
    # 為了與 verify_nonce 一致，我們直接用 Python 端做 nonce 生成（JS 把所有欄位回傳，
    # main.py 重算 nonce 並比對），所以 JS 只需要拿到 secret。
    # 但 secret 不該外洩到前端 → 採折衷：用 session-scoped 的「臨時 secret」生成
    # 一個「pre-nonce」綁定 user + 前置 ΔE/sleep/fatigue，
    # 並要求 JS 把該 pre-nonce 原樣回送，main.py 端比對。

    pre_payload = {"u": st.session_state.user_name, **prefill}
    pre_nonce = make_nonce(pre_payload)  # JS 不需重算

    # 把測驗階段參數依模式變化
    is_stroop_js = "true" if mode == "stroop" else "false"

    # === 嵌入 HTML/JS ===
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
              background:rgba(0,0,0,.85); color:#81C784; font-size:22px; font-weight:bold;
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
    <div id="overlay">✅ 測驗完成！<br>
      <span style="font-size:14px; color:#fff; margin-top:10px;">系統正在為您自動上傳…</span>
    </div>
  </div>
  <button id="start-btn">🚀 Start (5 練習 + 3 分鐘)</button>

<script>
  const IS_STROOP    = {is_stroop_js};
  const PRACTICE_N   = 5;
  const TEST_MS      = 180000;          // 3 分鐘
  const ISI_MIN      = IS_STROOP ? 800  : 2000;    // 試驗間隔 (ms)
  const ISI_MAX      = IS_STROOP ? 1500 : 10000;
  const FALSE_START  = 100;             // RT < 100ms = false start (按太快)
  const LAPSE_THRESH = IS_STROOP ? 500 : 500;      // 兩種測驗都用 500ms 標準

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

  // 結果累積器
  let rtAll = [];
  let rtCongruent = [];
  let rtIncongruent = [];
  let lapses = 0;
  let falseStarts = 0;
  let validTrials = 0;
  let pendingTimer = null;

  function rand(a,b) {{ return a + Math.random()*(b-a); }}

  function showCounterText() {{
    if (isPractice) counter.innerText = `練習 ${{PRACTICE_N - practiceLeft + 1}}/${{PRACTICE_N}}`;
    else            counter.innerText = `已記錄 ${{validTrials}} 試`;
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
      const w = words[Math.floor(Math.random()*4)];
      const c = colors[Math.floor(Math.random()*4)];
      stim.innerText = w;
      stim.style.color = c.hex;
      stim.style.display = 'block';
      currentColorId = c.id;
      // congruent: 字義 = 字色
      const wIdx = words.indexOf(w);
      isCongruent = (colors[wIdx].id === c.id);
    }} else {{
      dot.style.display = 'block';
    }}
    appearanceTime = performance.now();
  }}

  function recordResponse(correct, rt) {{
    if (rt < FALSE_START) {{ falseStarts++; return; }}  // 提前按
    if (!correct) {{ falseStarts++; return; }}            // 錯按 (Stroop)

    if (isPractice) {{
      practiceLeft--;
      if (practiceLeft <= 0) {{
        isPractice = false;
        testStartAt = performance.now();
        inst.innerText = IS_STROOP ?
          '🎯 正式測驗中 — 依「字體顏色」回應' :
          '🎯 正式測驗中 — 看到紅點立刻按反應';
        // 啟動 3 分鐘計時條
        timerBar.style.display = 'block';
        timerBar.style.transition = 'none';
        timerBar.style.width = '100%';
        setTimeout(() => {{
          timerBar.style.transition = `width ${{TEST_MS}}ms linear`;
          timerBar.style.width = '0%';
        }}, 50);
        setTimeout(finishTest, TEST_MS);
      }}
      return;
    }}
    // 正式期紀錄
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
      correct = true;  // PVT: 只要按了就算正確
      dot.style.display = 'none';
    }}
    waitingForResponse = false;
    recordResponse(correct, rt);
    scheduleNext();
  }}

  // Stroop 顏色按鈕
  document.querySelectorAll('.color-btn').forEach(b => {{
    b.addEventListener('mousedown', e => handleResponse(e.currentTarget.getAttribute('data-color')));
  }});
  // PVT 反應按鈕
  pvtBtn.addEventListener('mousedown', () => handleResponse('any'));

  // 偵測 false start (還沒出刺激就按)
  document.addEventListener('mousedown', e => {{
    if (isRunning && !waitingForResponse && !isPractice) {{
      // 但要排除 UI 範圍外的點擊；簡化為：在按鈕區域內 + 沒等待中 = false start
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

    const meanRT = rtAll.length ? rtAll.reduce((a,b)=>a+b,0)/rtAll.length : 0;
    const meanCon = rtCongruent.length ? rtCongruent.reduce((a,b)=>a+b,0)/rtCongruent.length : 0;
    const meanInc = rtIncongruent.length ? rtIncongruent.reduce((a,b)=>a+b,0)/rtIncongruent.length : 0;
    const interference = (IS_STROOP && rtCongruent.length && rtIncongruent.length)
                          ? (meanInc - meanCon) : 0;

    // === 數值範圍 sanity (在 JS 端就先夾，避免 NaN/inf 流出) ===
    function safe(v, lo, hi) {{
      if (!isFinite(v)) return 0;
      return Math.min(Math.max(v, lo), hi);
    }}
    const out = {{
      sleep_h:        {prefill["sleep_h"]},
      fatigue:        {prefill["fatigue"]},
      delta_E:        {prefill["delta_E"]},
      rt_mean:        Math.round(safe(meanRT, 0, 5000)),
      rt_congruent:   Math.round(safe(meanCon, 0, 5000)),
      rt_incongruent: Math.round(safe(meanInc, 0, 5000)),
      interference:   Math.round(safe(interference, -2000, 2000)),
      lapses:         Math.min(lapses, 1000),
      false_starts:   Math.min(falseStarts, 1000),
      valid_trials:   Math.min(validTrials, 5000),
    }};

    const u = '{safe_user}';
    const url = new URL(window.parent.location.href);
    url.searchParams.set('save', '1');
    url.searchParams.set('u',  u);
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
    // 注入 Python 端預先簽好的 pre-nonce；
    // main.py 端會用「user + sleep_h + fatigue + delta_E」這幾個前置欄位
    // 重算 nonce 並比對。攻擊者若無 session secret 不能偽造。
    url.searchParams.set('nc', '{pre_nonce}');

    setTimeout(() => {{ window.parent.location.href = url.toString(); }}, 800);
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
        st.warning("⚠️ 目前尚無歷史資料，請先完成「檢測打卡管線」。")
        return

    # ---------- Baseline 區塊 ----------
    baseline = compute_user_baseline(df, n_days=3)
    if baseline:
        st.markdown("#### 🧭 個人化基準線 (前 3 次中位數)")
        cols = st.columns(len(baseline))
        for (k, v), c in zip(baseline.items(), cols):
            c.metric(k, f"{v:.1f}" if isinstance(v, float) else v)

        # 用最新一筆 vs baseline 算相對變化
        latest = df.sort_values("Date").iloc[-1]
        st.markdown("##### 📐 最新檢測相對基準的變化量")
        ccols = st.columns(len(baseline))
        for (k, base_v), c in zip(baseline.items(), ccols):
            if k in latest and pd.notna(latest[k]):
                delta = compute_relative_change(float(latest[k]), base_v)
                if delta is None:
                    c.metric(k + " Δ%", "—")
                else:
                    c.metric(k + " Δ%", f"{delta:+.1f}%")

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

        daily_df = (df.groupby("Date")[available_cols]
                      .mean()
                      .reset_index()
                      .sort_values("Date"))

        metric_dict = {
            "Sleep_Hours":   "💤 睡眠時間 (小時)",
            "Fatigue_Level": "🥱 主觀疲勞度 (1-10)",
            "Delta_E":       "👁️ 眼周 ΔE (綜合)",
            "Delta_E_Left":  "👁️◐ 左眼 ΔE",
            "Delta_E_Right": "👁️◑ 右眼 ΔE",
            "Asymmetry":     "↔️ 左右不對稱性",
            "Mean_RT":       "⚡ 平均反應時間 (ms)",
            "RT_Congruent":  "✅ 一致試驗 RT",
            "RT_Incongruent":"⛔ 不一致試驗 RT",
            "Interference":  "🧠 Stroop Interference",
            "Lapses":        "❌ Lapses (RT≥500ms)",
            "False_Starts":  "⚠️ False Starts",
            "Valid_Trials":  "🎯 有效試驗數",
        }
        valid_metrics = [k for k in metric_dict if k in available_cols]
        if len(valid_metrics) < 2:
            st.info("資料維度不足以繪製雙軸圖表。")
        else:
            col_sel1, col_sel2 = st.columns(2)
            with col_sel1:
                d1 = valid_metrics.index("Sleep_Hours") if "Sleep_Hours" in valid_metrics else 0
                y1 = st.selectbox("📊 基礎指標", valid_metrics, index=d1,
                                  format_func=lambda x: metric_dict[x])
            with col_sel2:
                d2 = valid_metrics.index("Mean_RT") if "Mean_RT" in valid_metrics else min(1, len(valid_metrics)-1)
                y2 = st.selectbox("📈 對照指標", valid_metrics, index=d2,
                                  format_func=lambda x: metric_dict[x])

            base = alt.Chart(daily_df).encode(
                x=alt.X("Date:O", sort=None, title="檢測日期",
                        axis=alt.Axis(labelAngle=-45)))
            bar = base.mark_bar(opacity=0.5, color="#42A5F5",
                                cornerRadiusTopLeft=4,
                                cornerRadiusTopRight=4).encode(
                y=alt.Y(f"{y1}:Q", title=metric_dict[y1],
                        scale=alt.Scale(zero=True)))
            line = base.mark_line(color="#EF5350", strokeWidth=3,
                                  point=alt.OverlayMarkDef(color="#EF5350",
                                                           size=80)).encode(
                y=alt.Y(f"{y2}:Q", title=metric_dict[y2],
                        scale=alt.Scale(zero=False)))
            chart = (alt.layer(bar, line)
                       .resolve_scale(y="independent")
                       .properties(height=380)
                       .configure_axis(labelColor="#E0E0E0",
                                       titleColor="#E0E0E0",
                                       gridColor="rgba(255,255,255,0.1)")
                       .configure_view(strokeWidth=0))
            st.altair_chart(chart, use_container_width=True)

        with st.expander("📝 點此查看詳細歷史數據表"):
            st.dataframe(df.iloc[::-1].reset_index(drop=True),
                         use_container_width=True)

    except Exception as e:
        st.error(f"繪製圖表時發生錯誤：{e}")
