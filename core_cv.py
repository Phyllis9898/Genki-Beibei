import cv2
import numpy as np
import mediapipe as mp
import math

def calculate_distance(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def validate_lighting_conditions(img_gray):
    mean_brightness = np.mean(img_gray)
    contrast = np.std(img_gray)
    if mean_brightness < 40 or mean_brightness > 215 or contrast < 15:
        return False, f"光源不良 (亮度: {mean_brightness:.1f}, 對比: {contrast:.1f})"
    return True, "光源良好"

def apply_adaptive_chromatic_adaptation(img_bgr):
    img_float = img_bgr.astype(np.float32)
    b, g, r = cv2.split(img_float)
    mean_b, mean_g, mean_r = np.mean(b), np.mean(g), np.mean(r)
    mean_gray = (mean_b + mean_g + mean_r) / 3.0
    b_gain, g_gain, r_gain = mean_gray/(mean_b+1e-6), mean_gray/(mean_g+1e-6), mean_gray/(mean_r+1e-6)
    return cv2.merge([np.clip(b*b_gain,0,255), np.clip(g*g_gain,0,255), np.clip(r*r_gain,0,255)]).astype(np.uint8)

def analyze_dark_circles(image_file):
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    orig_image = cv2.imdecode(file_bytes, 1)
    if orig_image is None: return None, "圖片讀取失敗。"
        
    gray_image = cv2.cvtColor(orig_image, cv2.COLOR_BGR2GRAY)
    is_good_light, light_msg = validate_lighting_conditions(gray_image)
    if not is_good_light: return None, f"檢測失敗：{light_msg}"
    
    wb_img = apply_adaptive_chromatic_adaptation(orig_image)
    image_rgb = cv2.cvtColor(wb_img, cv2.COLOR_BGR2RGB) 
    image_lab_real = cv2.cvtColor(wb_img.astype(np.float32)/255.0, cv2.COLOR_BGR2Lab)
    
    h, w, _ = orig_image.shape
    annotated_img = cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB).copy()
    
    mp_face_mesh = mp.solutions.face_mesh
    LEFT_EYE_ROI = [228, 229, 230, 231, 232, 233, 123]
    RIGHT_EYE_ROI = [448, 449, 450, 451, 452, 453, 342] # 新增右眼 ROI
    CHEEK_ROI = [205, 206, 207, 187, 147]

    with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True) as face_mesh:
        results = face_mesh.process(image_rgb)
        if not results.multi_face_landmarks: return None, "未偵測到臉部。"
            
        lms = results.multi_face_landmarks[0]
        
        def get_roi_stats(idx_list, color, label):
            pts = np.array([[int(lms.landmark[i].x * w), int(lms.landmark[i].y * h)] for i in idx_list])
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask, [pts], 255)
            L_vals = image_lab_real[:,:,0][mask == 255]
            if len(L_vals) < 30: return None # 樣本量門檻
            
            cv2.polylines(annotated_img, [pts], True, color, 2)
            return np.median(L_vals), np.median(image_lab_real[:,:,1][mask == 255]), np.median(image_lab_real[:,:,2][mask == 255])

        l_stats = get_roi_stats(LEFT_EYE_ROI, (255,0,0), "L")
        r_stats = get_roi_stats(RIGHT_EYE_ROI, (255,255,0), "R")
        c_stats = get_roi_stats(CHEEK_ROI, (0,255,0), "C")
        
        if not all([l_stats, r_stats, c_stats]): return None, "採樣像素不足，請確保臉部清晰。"

        # 雙眼平均策略
        eye_L = (l_stats[0] + r_stats[0]) / 2.0
        eye_a = (l_stats[1] + r_stats[1]) / 2.0
        eye_b = (l_stats[2] + r_stats[2]) / 2.0
        cheek_L, cheek_a, cheek_b = c_stats
        
        # Delta E 公式： $$ \Delta E = \sqrt{(L_c - L_e)^2 + (a_c - a_e)^2 + (b_c - b_e)^2} $$[cite: 11]
        delta_E = math.sqrt((cheek_L - eye_L)**2 + (cheek_a - eye_a)**2 + (cheek_b - eye_b)**2)
        fatigue_index = eye_L / (cheek_L + 1e-6)
        ita = math.atan((cheek_L - 0.5) / (max(abs(cheek_b), 1e-5))) * (180.0 / math.pi)
        
        dynamic_delta_E_thresh = np.interp(np.clip(ita, 10, 41), [10.0, 41.0], [2.0, 3.5])
        has_dark_circles = delta_E > dynamic_delta_E_thresh or fatigue_index < 0.85
        detected_type = "vascular" if (eye_b < cheek_b - 0.003) else "pigmented"

        return {
            "orig": cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB),
            "orig_bgr": orig_image,
            "annotated_img": annotated_img,
            "has_dark_circles": has_dark_circles,
            "detected_type": detected_type,
            "metrics": {"delta_E": round(float(delta_E*100), 2), "ita": round(float(ita), 1)}
        }, None