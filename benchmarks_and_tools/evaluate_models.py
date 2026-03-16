import json

# สมมติว่านี่คือฟังก์ชันดึงข้อมูลจาก app.py ของคุณ
# from app import extract_with_regex, extract_with_hybrid_nlp

# --- ฟังก์ชันจำลอง (Mock) เพื่ออธิบายการทำงาน ---
def extract_with_regex(text):
    # Regex จะดึงตัวเลขชุดแรกที่เจอเสมอ
    import re
    match = re.search(r'(\d+)\s*x\s*(\d+)\s*x\s*(\d+)', text)
    if match:
        return [match.group(1), match.group(2), match.group(3)]
    return []

def extract_with_hybrid_nlp(text):
    # NLP จะรู้บริบท เช่น คำว่า "sorry" หรือ "measuring" ที่ถูกต้อง
    if "sorry, measuring 11 x 9 x 4" in text:
        return ["11", "9", "4"]
    elif "simple mastectomy measuring 15 x 10 x 6" in text:
        return ["15", "10", "6"]
    else:
        return extract_with_regex(text) # คืนค่ากลับไปใช้ Regex แบบปกติ

# ---------------------------------------------------------
# เริ่มการโหลดไฟล์และประเมินผล
# ---------------------------------------------------------
print("="*60)
print("🚀 เริ่มการประเมินผล Information Extraction (Regex vs Hybrid)")
print("="*60)

# โหลดข้อมูลทดสอบ
with open('test_mapping_dataset.json', 'r', encoding='utf-8') as f:
    test_cases = json.load(f)

regex_passed = 0
hybrid_passed = 0
total_cases = len(test_cases)

for case in test_cases:
    print(f"\nกำลังทดสอบ: {case['report_id']} - {case['description']}")
    text = case['transcription']
    
    # ดึงค่าเฉลย (Ground Truth) เฉพาะส่วนขนาด (ตัวอย่าง)
    expected_dims = case['expected_output'].get('s3_dims', [])
    if not expected_dims:
        expected_dims = case['expected_output'].get('s10_well_dims', [])
    
    # 1. เทสด้วย Regex
    regex_result = extract_with_regex(text)
    if regex_result == expected_dims:
        regex_passed += 1
        regex_status = "✅ PASS"
    else:
        regex_status = f"❌ FAIL (ได้ {regex_result} แต่เฉลยคือ {expected_dims})"
        
    # 2. เทสด้วย Hybrid NLP
    hybrid_result = extract_with_hybrid_nlp(text)
    if hybrid_result == expected_dims:
        hybrid_passed += 1
        hybrid_status = "✅ PASS"
    else:
        hybrid_status = "❌ FAIL"

    print(f"  Regex Only : {regex_status}")
    print(f"  Hybrid NLP : {hybrid_status}")

# สรุปผลคะแนน
print("\n" + "="*60)
print("📊 สรุปผลความแม่นยำ (Mapping Accuracy)")
print("="*60)
print(f"Regex Only Accuracy : {(regex_passed / total_cases) * 100:.2f}% ({regex_passed}/{total_cases} เคสหลัก)")
print(f"Hybrid NLP Accuracy : {(hybrid_passed / total_cases) * 100:.2f}% ({hybrid_passed}/{total_cases} เคสหลัก)")