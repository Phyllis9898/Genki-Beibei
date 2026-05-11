# ============================================================
#  core_cv.py  —  Genki Beibei v2.0
#  ------------------------------------------------------------
#  變更摘要（相對 v1）：
#   1. 雙眼對稱採樣 (LEFT + RIGHT ROI)
#   2. 移除 v1 殘留的 MSR 死碼分支
#   3. ROI 採樣強制 ≥ 30 px 否則整張 reject
#   4. 白平衡輸入臉部 bbox 的 median BGR (非全圖 gray-world)
#   5. 額外輸出 asymmetry_index (左右眼 L* 差) 供臨床觀察
#   6. Δ E 同時回傳左/右/平均三組數值
# ============================================================

from __future__ import annotations
import math
import cv2
import numpy as np
import mediapipe as mp

# --- MediaPipe FaceMesh landmark groups -------------------------
# (索引依據 MediaPipe Canonical Face Mesh，refine_landmarks=True)
LEFT_EYE_ROI: list[int]  = [228, 229, 230, 231, 232, 233, 123]
RIGHT_EYE_ROI: list[int] = [448, 449, 450, 451, 452, 453, 352]   # 與左眼鏡像對稱
CHEEK_ROI: list[int]     = [205, 206, 207, 187, 147]

MIN_ROI_PIXELS: int = 30   # < 30 px 時樣本量不足以給出穩定 median

# ------------------------------------------------------------------
#  工具函數
# ------------------------------------------------------------------
def validate_lighting_conditions(img_gray: np.ndarray) -> tuple[bool, str]:
    """雙指標光源篩選: 亮度 (40–215) 與對比度 (>=15)."""
    mean_brightness = float(np.mean(img_gray))
    contrast = float(np.std(img_gray))
    if mean_brightness < 40 or mean_brightness > 215 or contrast < 15:
        return False, f"光源不良 (亮度: {mean_brightness:.1f}, 對比: {contrast:.1f})"
    return True, "光源良好"


def _face_bbox_from_landmarks(lms, h: int, w: int) -> tuple[int, int, int, int]:
    """從 478 個 FaceMesh landmark 估出臉部 bbox（含一點 padding）。"""
    xs = np.array([lm.x for lm in lms.landmark]) * w
    ys = np.array([lm.y for lm in lms.landmark]) * h
    x_min, x_max = int(max(0, xs.min())), int(min(w, xs.max()))
    y_min, y_max = int(max(0, ys.min())), int(min(h, ys.max()))
    return x_min, y_min, x_max, y_max


def apply_face_aware_white_balance(img_bgr: np.ndarray,
                                   face_bbox: tuple[int, int, int, int] | None
                                   ) -> np.ndarray:
    """
    若給定 face_bbox，則以「臉部區域 BGR 中位數」作為灰世界基準，
    可避免單色背景（白牆、暗室）讓 gray-world 失真；
    若 bbox 為 None，退化為全圖 gray-world。
    """
    img_float = img_bgr.astype(np.float32)
    if face_bbox is not None:
        x0, y0, x1, y1 = face_bbox
        ref = img_float[y0:y1, x0:x1].reshape(-1, 3)
    else:
        ref = img_float.reshape(-1, 3)

    med_b, med_g, med_r = np.median(ref, axis=0)
    target = (med_b + med_g + med_r) / 3.0
    gains = np.array([target / (med_b + 1e-6),
                      target / (med_g + 1e-6),
                      target / (med_r + 1e-6)], dtype=np.float32)
    balanced = np.clip(img_float * gains[np.newaxis, np.newaxis, :], 0, 255)
    return balanced.astype(np.uint8)


# ------------------------------------------------------------------
#  主分析函數
# ------------------------------------------------------------------
def analyze_dark_circles(image_file):
    """
    回傳格式:
        (results_dict, None)   成功
        (None, error_str)      失敗
    results_dict.metrics 內含:
        delta_E         —  CIE76 ΔE × 100 後四捨五入 (與 v1 顯示口徑一致)
        delta_E_left    —  左眼相對臉頰 ΔE
        delta_E_right   —  右眼相對臉頰 ΔE
        asymmetry       —  |L_left − L_right|  左右不對稱性指標
        ita             —  Individual Typology Angle (deg)
    """
    # ---- 1. 讀檔 ----
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    orig_image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if orig_image is None:
        return None, "圖片讀取失敗。"

    gray = cv2.cvtColor(orig_image, cv2.COLOR_BGR2GRAY)
    ok, msg = validate_lighting_conditions(gray)
    if not ok:
        return None, f"檢測失敗：{msg}"

    h, w = orig_image.shape[:2]
    image_rgb_raw = cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB)

    # ---- 2. FaceMesh 偵測 ----
    mp_face_mesh = mp.solutions.face_mesh
    with mp_face_mesh.FaceMesh(static_image_mode=True,
                               max_num_faces=1,
                               refine_landmarks=True,
                               min_detection_confidence=0.5) as face_mesh:
        results = face_mesh.process(image_rgb_raw)
        if not results.multi_face_landmarks:
            return None, "未偵測到臉部，請確保臉部正面清晰且光源充足。"
        lms = results.multi_face_landmarks[0]

    # ---- 3. 臉部 bbox-aware 白平衡 ----
    face_bbox = _face_bbox_from_landmarks(lms, h, w)
    wb_img = apply_face_aware_white_balance(orig_image, face_bbox)

    # ---- 4. 轉 Lab 色彩空間 (浮點) ----
    image_lab = cv2.cvtColor(wb_img.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)
    L_ch = image_lab[:, :, 0]
    a_ch = image_lab[:, :, 1]
    b_ch = image_lab[:, :, 2]

    annotated_img = cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB).copy()

    def _roi_stats(idx_list: list[int], color_bgr: tuple[int, int, int]):
        """回傳 (L_med, a_med, b_med, n_pixels) 或 None"""
        pts = np.array([[int(lms.landmark[i].x * w),
                         int(lms.landmark[i].y * h)] for i in idx_list],
                       dtype=np.int32)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(mask, [pts], 255)
        sel = mask == 255
        n = int(sel.sum())
        if n < MIN_ROI_PIXELS:
            return None
        cv2.polylines(annotated_img, [pts], True, color_bgr, 2)
        return (float(np.median(L_ch[sel])),
                float(np.median(a_ch[sel])),
                float(np.median(b_ch[sel])),
                n)

    left  = _roi_stats(LEFT_EYE_ROI,  (255, 0, 0))      # 藍框
    right = _roi_stats(RIGHT_EYE_ROI, (255, 255, 0))    # 黃框
    cheek = _roi_stats(CHEEK_ROI,     (0, 255, 0))      # 綠框

    if not all([left, right, cheek]):
        return None, f"採樣像素不足 (需 ≥ {MIN_ROI_PIXELS}px)，請拍近一點或對好臉部。"

    # ---- 5. ΔE (CIE76) 計算 ----
    def _delta_e(eye, ck):
        return math.sqrt(
            (ck[0] - eye[0]) ** 2 +
            (ck[1] - eye[1]) ** 2 +
            (ck[2] - eye[2]) ** 2
        )

    dE_left  = _delta_e(left,  cheek)
    dE_right = _delta_e(right, cheek)
    eye_L_avg = (left[0] + right[0]) / 2.0
    eye_a_avg = (left[1] + right[1]) / 2.0
    eye_b_avg = (left[2] + right[2]) / 2.0
    cheek_L, cheek_a, cheek_b, _ = cheek
    dE_avg = math.sqrt(
        (cheek_L - eye_L_avg) ** 2 +
        (cheek_a - eye_a_avg) ** 2 +
        (cheek_b - eye_b_avg) ** 2
    )

    # 左右不對稱性 (Individual Asymmetry Index)
    asymmetry = abs(left[0] - right[0])

    fatigue_index = eye_L_avg / (cheek_L + 1e-6)

    # ITA (Individual Typology Angle)
    safe_b = max(abs(cheek_b), 1e-5)
    ita = math.atan((cheek_L - 0.5) / safe_b) * (180.0 / math.pi)

    # 依 ITA 動態調整 ΔE 閾值 (僅用於 v1 UI 旗標，不參與 baseline)
    ita_clipped = float(np.clip(ita, 10.0, 41.0))
    dynamic_thresh = float(np.interp(ita_clipped, [10.0, 41.0], [2.0, 3.5]))
    has_dark_circles = (dE_avg > dynamic_thresh) or (fatigue_index < 0.85)
    detected_type = "vascular" if (eye_b_avg < cheek_b - 0.003) else "pigmented"

    return {
        "orig": image_rgb_raw,
        "orig_bgr": orig_image,
        "annotated_img": annotated_img,
        "has_dark_circles": bool(has_dark_circles),
        "detected_type": detected_type,
        "metrics": {
            "delta_E":       round(float(dE_avg * 100), 2),
            "delta_E_left":  round(float(dE_left * 100), 2),
            "delta_E_right": round(float(dE_right * 100), 2),
            "asymmetry":     round(float(asymmetry * 100), 2),
            "ita":           round(float(ita), 1),
        },
    }, None
