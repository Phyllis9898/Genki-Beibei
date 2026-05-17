# ============================================================
#  core_cv.py  —  Genki Beibei v2.3 (Robust CV Edition)
# ============================================================
import math
import cv2
import numpy as np
import mediapipe as mp


# -------- 1. 工具函式 --------
def calculate_distance(p1, p2):
    """計算兩點之間的歐式距離"""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def validate_lighting_conditions(img_gray):
    """雙指標光源品質檢測：有效拒絕逆光、過曝與極暗環境"""
    mean_brightness = float(np.mean(img_gray))
    contrast = float(np.std(img_gray))
    if mean_brightness < 40 or mean_brightness > 215 or contrast < 15:
        return False, (
            f"光源不良 (平均亮度: {mean_brightness:.1f}, "
            f"對比度: {contrast:.1f})"
        )
    return True, "光源良好"


def apply_adaptive_chromatic_adaptation(img_bgr):
    """基於灰世界假設的自適應白平衡演算法"""
    img_float = img_bgr.astype(np.float32)
    b, g, r = cv2.split(img_float)
    mean_b = float(np.mean(b))
    mean_g = float(np.mean(g))
    mean_r = float(np.mean(r))
    mean_gray = (mean_b + mean_g + mean_r) / 3.0

    eps = 1e-6
    b_gain = mean_gray / (mean_b + eps)
    g_gain = mean_gray / (mean_g + eps)
    r_gain = mean_gray / (mean_r + eps)

    b_corrected = np.clip(b * b_gain, 0, 255)
    g_corrected = np.clip(g * g_gain, 0, 255)
    r_corrected = np.clip(r * r_gain, 0, 255)

    return cv2.merge([b_corrected, g_corrected, r_corrected]).astype(np.uint8)


# -------- 2. ROI 索引常數 --------
LEFT_EYE_ROI  = [228, 229, 230, 231, 232, 233, 123]
RIGHT_EYE_ROI = [448, 449, 450, 451, 452, 453, 342]
CHEEK_ROI     = [205, 206, 207, 187, 147]


# -------- 3. 主管線 --------
def analyze_dark_circles(image_file):
    """
    完整黑眼圈色彩分析流水線。

    隱患修補清單：
      1) 補上 file_pointer.seek(0)：Streamlit 的 UploadedFile 若先前被讀過會走到 EOF，
         此處重置避免空 buffer 造成 imdecode 失敗。
      2) imdecode 失敗或檔案損毀時優雅回傳錯誤訊息。
      3) ITA 計算改為 atan2 避免除以接近 0 的 b* 造成數值爆走。
      4) Mediapipe FaceMesh 結束後顯式 close（with 區塊保證）。
    """
    # ---- (1) 讀檔保護 ----
    try:
        if hasattr(image_file, "seek"):
            image_file.seek(0)
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    except Exception:
        return None, "讀取上傳檔案時發生錯誤，請重新上傳。"

    if file_bytes.size == 0:
        return None, "上傳的檔案為空，請選擇有效的圖片。"

    orig_image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if orig_image is None:
        return None, "圖片解碼失敗，請確認是合法的 JPG/PNG 格式。"

    # 過小的圖片無法進行可靠的臉部分析
    h, w = orig_image.shape[:2]
    if h < 200 or w < 200:
        return None, f"圖片解析度過低 ({w}×{h})，請上傳至少 200×200 像素的清晰自拍。"

    # ---- (2) 光源品質 ----
    gray_image = cv2.cvtColor(orig_image, cv2.COLOR_BGR2GRAY)
    is_good_light, light_msg = validate_lighting_conditions(gray_image)
    if not is_good_light:
        return None, f"檢測失敗：{light_msg}。請在光線均勻處重新拍攝。"

    # ---- (3) 白平衡 & Lab 色彩空間轉換 ----
    wb_img = apply_adaptive_chromatic_adaptation(orig_image)
    image_rgb = cv2.cvtColor(wb_img, cv2.COLOR_BGR2RGB)
    image_lab_real = cv2.cvtColor(
        wb_img.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab
    )

    annotated_img = cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB).copy()

    # ---- (4) MediaPipe 臉部 ROI 萃取 ----
    mp_face_mesh = mp.solutions.face_mesh
    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        results = face_mesh.process(image_rgb)
        if not results.multi_face_landmarks:
            return None, "未偵測到清晰臉部。請確保正面對準鏡頭且無遮擋。"

        lms = results.multi_face_landmarks[0]

        def get_roi_stats(idx_list, color):
            pts = np.array(
                [
                    [int(lms.landmark[i].x * w), int(lms.landmark[i].y * h)]
                    for i in idx_list
                ],
                dtype=np.int32,
            )
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask, [pts], 255)

            L_vals = image_lab_real[:, :, 0][mask == 255]
            a_vals = image_lab_real[:, :, 1][mask == 255]
            b_vals = image_lab_real[:, :, 2][mask == 255]

            if len(L_vals) < 30:
                return None

            cv2.polylines(annotated_img, [pts], True, color, 2)
            return (
                float(np.median(L_vals)),
                float(np.median(a_vals)),
                float(np.median(b_vals)),
            )

        l_stats = get_roi_stats(LEFT_EYE_ROI, (255, 0, 0))
        r_stats = get_roi_stats(RIGHT_EYE_ROI, (255, 255, 0))
        c_stats = get_roi_stats(CHEEK_ROI, (0, 255, 0))

    # ---- (5) 採樣不足保護 ----
    if not l_stats or not r_stats or not c_stats:
        return None, "採樣像素不足。請靠近鏡頭並確保眼周與面頰無頭髮遮擋。"

    eye_L = (l_stats[0] + r_stats[0]) / 2.0
    eye_a = (l_stats[1] + r_stats[1]) / 2.0
    eye_b = (l_stats[2] + r_stats[2]) / 2.0

    cheek_L, cheek_a, cheek_b = c_stats

    # ---- (6) ΔE 與不對稱性 ----
    delta_E = math.sqrt(
        (cheek_L - eye_L) ** 2
        + (cheek_a - eye_a) ** 2
        + (cheek_b - eye_b) ** 2
    )
    delta_E_left = math.sqrt(
        (cheek_L - l_stats[0]) ** 2
        + (cheek_a - l_stats[1]) ** 2
        + (cheek_b - l_stats[2]) ** 2
    )
    delta_E_right = math.sqrt(
        (cheek_L - r_stats[0]) ** 2
        + (cheek_a - r_stats[1]) ** 2
        + (cheek_b - r_stats[2]) ** 2
    )
    asymmetry = abs(delta_E_left - delta_E_right)

    fatigue_index = eye_L / (cheek_L + 1e-6)

    # ---- (7) ITA (Individual Typology Angle) ----
    # 改用 atan2，當 b* 接近 0 時仍能輸出穩定角度
    ita = math.degrees(math.atan2((cheek_L - 0.5), cheek_b)) if cheek_b != 0 else 0.0

    dynamic_delta_E_thresh = float(
        np.interp(np.clip(ita, 10, 41), [10.0, 41.0], [2.0, 3.5])
    )
    has_dark_circles = (
        delta_E > dynamic_delta_E_thresh or fatigue_index < 0.85
    )
    detected_type = "vascular" if (eye_b < cheek_b - 0.003) else "pigmented"

    return {
        "orig": cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB),
        "orig_bgr": orig_image,
        "annotated_img": annotated_img,
        "has_dark_circles": has_dark_circles,
        "detected_type": detected_type,
        "metrics": {
            "delta_E":       round(float(delta_E * 100), 2),
            "delta_E_left":  round(float(delta_E_left * 100), 2),
            "delta_E_right": round(float(delta_E_right * 100), 2),
            "asymmetry":     round(float(asymmetry * 100), 2),
            "ita":           round(float(ita), 1),
        },
    }, None
