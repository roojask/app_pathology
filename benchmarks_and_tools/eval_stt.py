import time
from jiwer import wer
import whisper

# 1. โหลดโมเดล (ใช้โมเดล "small" ตามการตั้งค่าหลัก)
model = whisper.load_model("base") 

# 2. ข้อความเฉลยที่ถูกต้อง (Ground Truth) ของไฟล์เสียงนี้
ground_truth = "Received in formalin is a right modified radical mastectomy specimen measuring 18 by 9 by 6 centimeters. The skin ellipse, 15 by 7 centimeters, appears normal. The nipple is everted. There is an infiltrative firm yellow-white mass, 3.6 by 3 by 2.8 centimeters located in lower outer quadrant. Tumor is located 0.7 centimeters from deep margin, 3.5 centimeters from superior margin, 1 centimeter from inferior margin, 8 centimeters from medial margin, 5 centimeters from lateral margin, and 0.4 centimeters from skin. The remaining of breast tissue is unremarkable. Representative sections are submitted as A1-1 nipple, A2-1 to A4-1 equal mass, A5-1 equal deep resected margin with mass, A6-1 equal inferior resected margin with mass."

# 3. เริ่มจับเวลา
start_time = time.time()

# 4. ถอดความเสียง (ใช้ไฟล์ที่มีอยู่ในระบบ)
result = model.transcribe("sound/input_Breast.wav", initial_prompt="mastectomy, infiltrative, quadrant")
hypothesis = result["text"]

# 5. สิ้นสุดการจับเวลา
end_time = time.time()

# คำนวณผลลัพธ์
error_rate = wer(ground_truth.lower(), hypothesis.lower()) * 100
time_taken = end_time - start_time

print(f"คำถอดความที่ได้: {hypothesis}")
print(f"เวลาที่ใช้ประมวลผล: {time_taken:.2f} วินาที")
print(f"Word Error Rate (WER): {error_rate:.2f}%")