# 檔案名稱：core_cv.py
import cv2
import numpy as np
import mediapipe as mp
import math

def calculate_distance(p1, p2):
    """計算兩點之間的歐幾里得距離"""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def calculate_ear(eye_points):
    """計算眼睛縱橫比 (Eye Aspect Ratio)，用於疲勞偵測"""
    v1 = calculate_distance(eye_points[1], eye_points[5])
    v2 = calculate_distance(eye_points[2], eye_points[4])
    h = calculate_distance(eye_points[0], eye_points[3])
    if h == 0: 
        return 0.0
    return (v1 + v2) / (2.0 * h)

def validate_lighting_conditions(img_gray):
    """
    【專家校正】環境光品質檢驗
    計算整張影像的亮度與對比度，拒絕極端光源，避免陰影被誤判為黑眼圈。
    """
    mean_brightness = np.mean(img_gray)
    contrast = np.std(img_gray)
    
    if mean_brightness < 40 or mean_brightness > 215 or contrast < 15:
        return False, f"光源不良 (亮度: {mean_brightness:.1f}, 對比: {contrast:.1f})"
    return True, "光源良好"

# ==========================================
# 專家級影像特徵修正演算法 (升級版)
# ==========================================
def apply_adaptive_chromatic_adaptation(img_bgr, face_roi_mean=None):
    """
    【專家取代】自適應色偏對齊演算法
    取代傳統灰世界假設。若有提供臉部基準色，則以臉部為基準進行局部增益調整，
    避免背景顏色干擾白平衡判定。
    """
    img_float = img_bgr.astype(np.float32)
    b, g, r = cv2.split(img_float)
    
    if face_roi_mean is not None:
        target_val = (face_roi_mean[0] + face_roi_mean[1] + face_roi_mean[2]) / 3.0
        b_gain = target_val / (face_roi_mean[0] + 1e-6)
        g_gain = target_val / (face_roi_mean[1] + 1e-6)
        r_gain = target_val / (face_roi_mean[2] + 1e-6)
    else:
        mean_b, mean_g, mean_r = np.mean(b), np.mean(g), np.mean(r)
        mean_gray = (mean_b + mean_g + mean_r) / 3.0
        b_gain, g_gain, r_gain = mean_gray/mean_b, mean_gray/mean_g, mean_gray/mean_r
    
    b = np.clip(b * b_gain, 0, 255)
    g = np.clip(g * g_gain, 0, 255)
    r = np.clip(r * r_gain, 0, 255)
    
    return cv2.merge([b, g, r]).astype(np.uint8)

def apply_msr_algorithm(img):
    """
    MSR (Multi-Scale Retinex) 演算法：
    透過多尺度的低通濾波器來增強暗部細節，初步抵抗不良光線的干擾。
    """
    img_float = img.astype(np.float64) + 1.0
    retinex = np.zeros_like(img_float)
    for s in [15, 80, 250]:
        blur = cv2.GaussianBlur(img_float, (0, 0), s)
        retinex += np.log10(img_float) - np.log10(blur)
    retinex /= 3.0
    for i in range(3):
        retinex[:,:,i] = cv2.normalize(retinex[:,:,i], None, 0, 255, cv2.NORM_MINMAX)
    return np.uint8(retinex)

def analyze_dark_circles(image_file):
    """
    黑眼圈分析主程式：
    【專家核心修正】特徵取樣嚴格使用白平衡影像，並導入中位數(Median)統計法抵抗雜訊。
    """
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    orig_image = cv2.imdecode(file_bytes, 1)
    if orig_image is None:
        return None, "圖片讀取失敗，請確認檔案格式。"
        
    gray_image = cv2.cvtColor(orig_image, cv2.COLOR_BGR2GRAY)
    
    is_good_light, light_msg = validate_lighting_conditions(gray_image)
    if not is_good_light:
        return None, f"檢測失敗：{light_msg}。請移至光源明亮且均勻的地方再試一次。"
    
    wb_img = apply_adaptive_chromatic_adaptation(orig_image)
    enhanced_img = apply_msr_algorithm(wb_img)
    image_rgb = cv2.cvtColor(enhanced_img, cv2.COLOR_BGR2RGB) 
    
    img_float32 = wb_img.astype(np.float32) / 255.0
    image_lab_real = cv2.cvtColor(img_float32, cv2.COLOR_BGR2Lab)
    
    h, w, _ = enhanced_img.shape
    annotated_img = cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB).copy()
    
    mp_face_mesh = mp.solutions.face_mesh
    LEFT_EYE_ROI = [228, 229, 230, 231, 232, 233, 123]
    CHEEK_ROI = [205, 206, 207, 187, 147]

    with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True) as face_mesh:
        results = face_mesh.process(image_rgb)
        if not results.multi_face_landmarks:
            return None, "未偵測到臉部，請更換正面清晰照片。"
            
        lms = results.multi_face_landmarks[0]
        left_eye_pts = [(int(lms.landmark[i].x * w), int(lms.landmark[i].y * h)) for i in LEFT_EYE_ROI]
        
        def get_roi_stats(idx_list, color, label):
            """
            【專家修正】放棄 cv2.mean，改用 np.median 過濾睫毛與反光極端值
            """
            pts = np.array([[int(lms.landmark[i].x * w), int(lms.landmark[i].y * h)] for i in idx_list])
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask, [pts], 255)
            
            # 取出 Mask 內的有效像素
            L_vals = image_lab_real[:,:,0][mask == 255]
            a_vals = image_lab_real[:,:,1][mask == 255]
            b_vals = image_lab_real[:,:,2][mask == 255]
            
            # 使用中位數避免雜訊干擾
            median_L = np.median(L_vals) if len(L_vals) > 0 else 0
            median_a = np.median(a_vals) if len(a_vals) > 0 else 0
            median_b = np.median(b_vals) if len(b_vals) > 0 else 0
            
            cv2.polylines(annotated_img, [pts], True, color, 2)
            top_point = tuple(pts[pts[:, 1].argmin()])
            cv2.putText(annotated_img, label, (top_point[0], top_point[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            return median_L, median_a, median_b

        eye_L, eye_a, eye_b = get_roi_stats(LEFT_EYE_ROI, (255, 0, 0), "Z2(Eye)")
        cheek_L, cheek_a, cheek_b = get_roi_stats(CHEEK_ROI, (0, 255, 0), "ZC(Cheek)")
        
        # 計算特徵距離
        delta_E = math.sqrt((cheek_L - eye_L)**2 + (cheek_a - eye_a)**2 + (cheek_b - eye_b)**2)
        fatigue_index = eye_L / (cheek_L + 1e-6)
        
        safe_cheek_b = max(cheek_b, 1e-5) if cheek_b >= 0 else min(cheek_b, -1e-5)
        ita = math.atan((cheek_L - 50.0) / safe_cheek_b) * (180.0 / math.pi)
        
        dynamic_delta_E_thresh = np.interp(ita, [10.0, 41.0], [2.0, 3.5])
        dynamic_L_drop_thresh = np.interp(ita, [10.0, 41.0], [3.0, 5.0])
        
        has_dark_circles = False
        detected_type = "normal"

        if (delta_E > dynamic_delta_E_thresh) or ((cheek_L - eye_L) > dynamic_L_drop_thresh) or (fatigue_index < 0.85):
            has_dark_circles = True
            if eye_b < (cheek_b - 0.8) or eye_a > (cheek_a + 0.8):
                detected_type = "vascular" 
            else:
                detected_type = "pigmented" 

        return {
            "orig": cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB),
            "orig_bgr": orig_image,
            "left_eye_pts": left_eye_pts,
            "annotated_img": annotated_img,
            "has_dark_circles": has_dark_circles,
            "detected_type": detected_type,
            "metrics": {
                "eye_L": round(float(eye_L), 1), 
                "cheek_L": round(float(cheek_L), 1),
                "fatigue_index": round(float(fatigue_index), 3), 
                "delta_E": round(float(delta_E), 2),
                "ita": round(float(ita), 1),
                "dynamic_thresh": round(float(dynamic_delta_E_thresh), 2)
            }
        }, None