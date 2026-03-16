import re
import spacy

# โหลดโมเดลภาษาอังกฤษขนาดเล็กของ spaCy (ถ้ายังไม่มีให้รัน: python -m spacy download en_core_web_sm)
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("กรุณารันคำสั่ง: python -m spacy download en_core_web_sm ก่อนรันสคริปต์")
    exit()

# ---------------------------------------------------------
# 1. ฟังก์ชันจำลองการสกัดข้อมูลด้วย Regex เพียงอย่างเดียว
# ---------------------------------------------------------
def extract_with_regex_only(text):
    # พยายามจับคู่ตัวเลข 3 แกน เช่น "3 x 4 x 5 cm" หรือ "3 by 4 by 5 cm"
    pattern = r'(\d+(?:\.\d+)?)\s*(?:x|by)\s*(\d+(?:\.\d+)?)\s*(?:x|by)\s*(\d+(?:\.\d+)?)\s*(?:cm|centimeters)'
    match = re.search(pattern, text.lower())
    
    if match:
        return f"{match.group(1)} x {match.group(2)} x {match.group(3)} cm"
    return "สกัดข้อมูลไม่สำเร็จ (Not Found)"

# ---------------------------------------------------------
# 2. ฟังก์ชันจำลองการสกัดข้อมูลด้วย Hybrid (Regex + spaCy)
# ---------------------------------------------------------
def extract_with_hybrid_nlp(text):
    doc = nlp(text.lower())
    
    # [ความฉลาดของ NLP 1]: จัดการเคส "พูดแก้คำผิดกลางอากาศ (Self-correction)"
    # spaCy ช่วยหาบริบทคำว่า "correction" หรือ "sorry" แล้วตัดข้อความเก่าทิ้ง
    correction_keywords = ["correction", "sorry", "wait"]
    for token in doc:
        if token.text in correction_keywords:
            # ตัดเอาเฉพาะข้อความ "หลัง" จากคำที่แก้ตัว
            text = text[token.idx:] 
            doc = nlp(text) # ประมวลผลใหม่
            break
            
    # ลองใช้ Regex ด่านแรก (บนประโยคที่ทำความสะอาดแล้ว)
    regex_result = extract_with_regex_only(text)
    if regex_result != "สกัดข้อมูลไม่สำเร็จ (Not Found)":
        return regex_result
        
    # [ความฉลาดของ NLP 2]: จัดการเคส "พูดแยกส่วน (Fragmented)"
    # ใช้ spaCy Dependency Parsing หาตัวเลขที่เกาะกับคำว่า length, width, depth
    dimensions = []
    for token in doc:
        if token.pos_ == "NUM":
            # ดูว่าตัวเลขนี้ไปขยาย (head) คำว่าอะไร เช่น ไปขยายคำว่า length หรือไม่
            if token.head.text in ["length", "width", "depth", "cm", "centimeters"]:
                dimensions.append(token.text)
                
    if len(dimensions) == 3:
        return f"{dimensions[0]} x {dimensions[1]} x {dimensions[2]} cm"
        
    return "สกัดข้อมูลไม่สำเร็จ (Not Found)"

# ---------------------------------------------------------
# 3. รันการทดสอบเปรียบเทียบ (Evaluation)
# ---------------------------------------------------------
test_cases = [
    {
        "case_name": "Case 01: ประโยคโครงสร้างปกติ (Baseline)",
        "text": "There is a firm yellow-white mass, measuring 3.6 by 3 by 2.8 centimeters located in the breast."
    },
    {
        "case_name": "Case 02: ประโยคพูดแยกส่วน (Fragmented/Out of order)",
        "text": "The mass length is 3.6 cm, the width is about 3 cm, and depth is 2.8 cm."
    },
    {
        "case_name": "Case 03: ประโยคแก้ไขคำผิดกลางอากาศ (Self-correction)",
        "text": "The mass size is 5 by 6 by 7 centimeters... oh wait, correction, the size is 3.6 by 3 by 2.8 centimeters."
    }
]

print("="*60)
print("เริ่มการทดสอบเปรียบเทียบโมเดล Information Extraction")
print("="*60)

for case in test_cases:
    print(f"\n[{case['case_name']}]")
    print(f"เสียงที่หมอพูด: \"{case['text']}\"")
    print("-" * 40)
    
    # รัน Regex
    regex_ans = extract_with_regex_only(case['text'])
    print(f"👉 ผลลัพธ์ Regex Only:  {regex_ans}")
    
    # รัน Hybrid
    hybrid_ans = extract_with_hybrid_nlp(case['text'])
    print(f"👉 ผลลัพธ์ Hybrid NLP:  {hybrid_ans}")

print("\n" + "="*60)