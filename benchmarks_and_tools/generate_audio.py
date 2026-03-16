import json
import os
import asyncio
import edge_tts

# 1. โหลดไฟล์ JSON
DATASET_PATH = 'test_mapping_dataset.json'

with open(DATASET_PATH, 'r', encoding='utf-8') as f:
    dataset = json.load(f)

# 2. สร้างโฟลเดอร์สำหรับเก็บไฟล์เสียงจำลอง
OUTPUT_DIR = "audio_cases"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 3. กำหนดลิสต์ของเสียง (ชาย และ หญิง)
VOICES = [
    "en-US-ChristopherNeural",  # เสียงผู้ชาย (ค่อนข้างทุ้ม)
    "en-US-AriaNeural"          # เสียงผู้หญิง (ชัดเจน เป็นทางการ)
]

async def generate_all_audios():
    print(f"Found {len(dataset)} cases. Starting audio generation...")
    
    # ใช้ enumerate เพื่อดึงตัวเลขลำดับรอบ (index) ออกมาด้วย
    for index, case in enumerate(dataset):
        report_id = case.get("report_id", f"unknown_case_{index}")
        text = case.get("transcription", "")
        
        if not text:
            continue
            
        output_file = os.path.join(OUTPUT_DIR, f"{report_id}.mp3")
        
        # ใช้เครื่องหมาย % (หารเอาเศษ) เพื่อสลับเสียงชาย/หญิง ตามลำดับเคส
        # index คู่ จะได้เสียงชาย (0, 2, 4...) / index คี่ จะได้เสียงหญิง (1, 3, 5...)
        voice = VOICES[index % 2]
        
        # เช็คว่ารอบนี้กำลังใช้เสียงใคร เพื่อเอาไป Print บอกที่หน้าจอ
        gender_label = "Male" if "Christopher" in voice else "Female"
        
        print(f"Generating [{gender_label}] -> {output_file}")
        
        # ลดความเร็วลง 5% เพื่อให้เหมือนหมออ่านผลช้าๆ ชัดๆ
        communicate = edge_tts.Communicate(text, voice, rate="-5%")
        
        await communicate.save(output_file)

if __name__ == "__main__":
    asyncio.run(generate_all_audios())
    print("\n✅ เสร็จสิ้น! ไฟล์เสียง (ชาย-หญิง) ทั้งหมดถูกบันทึกอยู่ในโฟลเดอร์ 'audio_cases' แล้ว")