import os
import re
import uuid
import datetime
from pathlib import Path
from flask import Flask, render_template, request, send_from_directory, redirect, url_for, flash
import fitz  # PyMuPDF
import whisper
from pdf2docx import Converter

# --- Config ---
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
ASSETS_DIR = BASE_DIR / "assets"
TEMPLATE_DIR = BASE_DIR / "templates"

PDF_TEMPLATE_PATH = ASSETS_DIR / "Breast_Gross_Template.pdf"

for p in [UPLOAD_DIR, OUTPUT_DIR, ASSETS_DIR, TEMPLATE_DIR]:
    p.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = "pathology-secret"

print("⏳ Loading Whisper model...")
model = whisper.load_model(os.environ.get("WHISPER_MODEL", "small"))
print("✅ Whisper model loaded!")

# --- 1. Helper Functions ---

def normalize_text(text):
    t = text.lower()
    t = t.replace(" by ", " x ").replace(" times ", " x ")
    t = t.replace("centimeters", "cm").replace("centimeter", "cm")
    t = t.replace("millimeter", "mm").replace("millimeters", "mm")
    t = t.replace("equal", "=").replace("equals", "=")
    
    # FIX: แก้ ASR ฟัง "8" เป็น "x" ในบริบทระยะห่าง (เช่น x cm from)
    # ใช้ Regex \b เพื่อให้แน่ใจว่าเป็นตัว x เดี่ยวๆ ไม่ใช่ส่วนหนึ่งของคำอื่น
    t = re.sub(r"\bx\s+(?:cm|centimeters?)\s+from", "8 cm from", t)
    # --- Specific Fixes (แก้คำผิด) ---
    t = t.replace("mast", "mass") 
    t = t.replace("medium margin", "medial margin")
    t = t.replace("massectomy", "mastectomy")
    t = t.replace("slit-like", "slit like")
    t = t.replace("the resected", "deep resected")
    
    # FIX: แก้ ASR error "nipple is inverted" -> "nipple is everted"
    # เพื่อให้ติ๊กช่อง "is everted" ตามที่ user ต้องการ
    t = t.replace("nipple is inverted", "nipple is everted")
    
    return t

def format_section_code(code):
    """Format codes: A21 -> A2-1, A2-1 to A4-1 -> A2-1-A4-1"""
    code = re.sub(r"\b(to|and)\b", "-", code, flags=re.IGNORECASE)
    code = code.upper().replace(" ", "")
    parts = re.split(r"[-;,]", code)
    formatted_parts = []
    for p in parts:
        if not p: continue
        if re.match(r"^[A-Z]\d{2,}$", p):
            p = f"{p[0]}{p[1]}-{p[2:]}"
        formatted_parts.append(p)
    return "-".join(formatted_parts)

def extract_data_15_sections(text):
    t = normalize_text(text)
    data = {}

    # 0. Surgical Number
    # Pattern: "surgical number S-XX-XXXX" or similar
    m = re.search(r"surgical number\s+([a-zA-Z0-9\/-]+)", t)
    if m: data["s0_surgical_no"] = m.group(1).upper()

    # 1. Side
    if "right" in t: data["s1_side"] = "right"
    elif "left" in t: data["s1_side"] = "left"

    # 2. Procedure
    if "modified radical" in t: data["s2_proc"] = "modified"
    elif "simple mastectomy" in t: data["s2_proc"] = "simple"
    else:
        m = re.search(r"procedure is (.+)", t)
        if m: 
            data["s2_proc"] = "other"
            data["s2_other_text"] = m.group(1).strip()

    # 3. Measuring
    m = re.search(r"specimen measuring\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
    if m: data["s3_dims"] = [m.group(1), m.group(2), m.group(3)]

    # 4. Axillary
    if "axillary content" in t:
        data["s4_check"] = True
        m = re.search(r"axillary content.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
        if m: data["s4_dims"] = [m.group(1), m.group(2), m.group(3)]

    # 5. Skin Ellipse
    m = re.search(r"skin ellipse.*?\s+([\d.]+)\s*x\s*([\d.]+)", t)
    if m: data["s5_dims"] = [m.group(1), m.group(2)]

    # 6. Appears Normal
    if "appears normal" in t: data["s5_appears_normal"] = True

    # 7. Scar
    if "scar" in t:
        data["s6_check"] = True  # FIX: Map to s6_check to match HTML

        m = re.search(r"scar\s+([\d.]+)\s*cm", t)
        if m: data["s7_len"] = m.group(1)
        
        scar_idx = t.find("scar")
        if scar_idx != -1:
            context = t[scar_idx:scar_idx+100]
            locs = []
            for l in ["upper", "lower", "inner", "outer", "areola"]:
                if l in context: locs.append(l)
            if locs: data["s7_locs"] = locs

    # 8. Ulceration
    ulcer_match = re.search(r"ulceration", t)
    if ulcer_match:
        # Preceding check for nipple
        # Find newline before ulcer
        start_idx = t.rfind("\n", 0, ulcer_match.start())
        if start_idx == -1: start_idx = 0
            
        preceding = t[start_idx:ulcer_match.start()]
        if "nipple" not in preceding:
            data["s8_check"] = True
            m = re.search(r"ulceration\s+([\d.]+)\s*x\s*([\d.]+)", t)
            if m: data["s8_dims"] = [m.group(1), m.group(2)]
            
            context = t[ulcer_match.start():ulcer_match.end()+100]
            locs = []
            for l in ["upper", "lower", "inner", "outer", "areola"]:
                if l in context: locs.append(l)
            if locs: data["s8_locs"] = locs

    # 9. Nipple (Logic updated for s9_val list)
    s9_vals = []
    t_lower = t.lower()
    if "nipple" in t_lower:
         if "everted" in t_lower: s9_vals.append("everted")
         if "inverted" in t_lower: s9_vals.append("inverted")
         
         # Check specifically for "nipple shows ulceration" or close proximity
         # Find all occurrences of "ulceration"
         for m in re.finditer("ulceration", t_lower):
              start = m.start()
              # Check 50 chars before
              context = t_lower[max(0, start-50):start]
              if "nipple" in context or "shows" in context: 
                   # "The nipple shows ulceration" -> context has "nipple shows "
                   # "shows ulceration" -> context has "shows " (but this might match S8 too?)
                   # S8 is "shows an ulceration". S9 is typically just "shows ulceration".
                   # Let's be safe: if "nipple" is in context, OR if "shows" is there AND "an" is NOT (to avoid S8).
                   if "nipple" in context:
                        if "ulceration" not in s9_vals: s9_vals.append("ulceration")
                   elif "shows" in context and "an" not in context[-5:]: 
                        # "shows an ulceration" vs "shows ulceration"
                        if "ulceration" not in s9_vals: s9_vals.append("ulceration")
    
    if s9_vals: data["s9_val"] = s9_vals

    # 10. Mass
    mass_count = 0
    mass_types = []

    if "infiltrative" in t.lower():
        mass_count += 1
        data["s10_infiltrative"] = True
        mass_types.append("infiltrative")
        m = re.search(r"infiltrative.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t, re.IGNORECASE)
        if m: data["s10_inf_dims"] = [m.group(1), m.group(2), m.group(3)]

    if "well" in t and "defined" in t:
        mass_count += 1
        data["s10_well"] = True
        mass_types.append("well")
        m = re.search(r"well.*?defined.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
        if m: data["s10_well_dims"] = [m.group(1), m.group(2), m.group(3)]

    if "previous surgical cavity" in t and "residual mass" not in t:
        mass_count += 1
        data["s10_prev1"] = True
        mass_types.append("prev1")
        m = re.search(r"previous surgical cavity.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
        if m: data["s10_prev1_dims"] = [m.group(1), m.group(2), m.group(3)]

    if "residual mass" in t:
        mass_count += 1
        data["s10_prev2"] = True
        mass_types.append("prev2")
        m1 = re.search(r"previous surgical cavity.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
        if m1: data["s10_prev2_cavity_dims"] = [m1.group(1), m1.group(2), m1.group(3)]
        m2 = re.search(r"residual mass.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
        if not m2:
             # Try simpler pattern: just numbers near residual mass
             # e.g. "residual mass 1.5 x 2 x 3"
             m2 = re.search(r"residual mass.*?([\d.]+)\s*(?:x|by)\s*([\d.]+)\s*(?:x|by)\s*([\d.]+)", t)
        if m2: data["s10_prev2_mass_dims"] = [m2.group(1), m2.group(2), m2.group(3)]

    if mass_count == 1:
        data["s10_grammar"] = "is an" if mass_types[0] == "infiltrative" else "is a"
    elif mass_count == 2:
        data["s10_grammar"] = "are two"
    elif mass_count > 2:
        data["s10_grammar"] = "are multiple"

    # 10.5 Location (FIX: Search 'located in ... quadrant' in full text)
    if "beneath the nipple" in t: data["s10_5_nipple"] = True
    if "beneath the scar" in t: data["s10_5_scar"] = True
    if "central" in t and "portion" in t: data["s10_5_central"] = True
    
    locs = []
    tumor_loc_match = re.search(r"(?:tumor|mass|located).*?(\bin\s+(?:the\s+)?(?:upper|lower|inner|outer)[\w\s]*?quadrant)", t)
    
    if tumor_loc_match:
        loc_text = tumor_loc_match.group(1)
        for q in ["upper", "lower", "inner", "outer"]:
            if q in loc_text:
                data["s10_5_quadrant_check"] = True
                locs.append(q)
    
    if locs: data["s10_5_quadrant_vals"] = locs

    # Other location
    # If there is text in "located" block that isn't just quadrants/nipple/scar/central
    # Simple heuristic: grab text after "located" or "located in" that is not captured above
    # Or matches user request pattern: "located in ... (other text)"
    # Let's try to capture "located in [OTHER]" if it doesn't match standard quadrants
    t = t.replace("comma", ",")
    t = t.replace("  ", " ") # Clean up spaces
    
    # 1. Helper Functions ---
    # ... (existing content) ...
    # FIX: Exclude "Tumor follows..." or similar
    # Logic: Look for "located in/at X". X must not be one of the standard keywords.
    # Also stop at "Tumor" or "."
    m = re.search(r"(?<!tumor is\s)located.*?(?:in|at)\s+(?!(?:the)?\s*(?:upper|lower|inner|outer|central|nipple|scar))(.+?)(?:\.|$|tumor)", t)
    if m:
        candidate = m.group(1).strip()
        # Further filter: Candidate shouldn't be just numbers or margin info
        if len(candidate) > 2 and "margin" not in candidate and not re.match(r"^[\d\s.,]+$", candidate):
             data["s10_5_other"] = candidate

    # 11. Margins
    margins = ["deep", "superior", "inferior", "medial", "lateral", "skin"]
    for m_name in margins:
        regex = rf"([\d.]+)\s*cm\s*(?:from|at)?\s*{m_name}\s*margin"
        m = re.search(regex, t)
        if not m: regex = rf"{m_name}\s*margin\s*(?:is)?\s*([\d.]+)\s*cm"
        m = re.search(regex, t)
        if m: data[f"s11_{m_name}"] = m.group(1)
        if m_name == "skin":
            m_skin = re.search(r"([\d.]+)\s*cm\s*from\s*skin", t)
            if m_skin: data["s11_skin"] = m_skin.group(1)

    # 12. Ratio
    m = re.search(r"ratio.*?\b(\d+)\s*(?::|to)\s*(\d+)", t)
    if m: 
        data["s12_check"] = True
        data["s12_val_left"] = m.group(1)
        data["s12_val_right"] = m.group(2)

    # 13. Remaining Tissue
    if "unremarkable" in t:
        data["s13_type"] = "unremarkable"
    elif "remaining of breast tissue" in t:
         m = re.search(r"remaining of breast tissue (?:is|shows) (.+)", t)
         if m: 
             data["s13_type"] = "other"
             data["s13_text"] = m.group(1).split('.')[0].split(',')[0]

    # 14. Lymph Nodes
    if "lymph node" in t:
        data["s14_check"] = True
        m = re.search(r"ranging from\s+([\d.]+).*?to\s+([\d.]+)", t)
        if m: 
            data["s14_min"] = m.group(1)
            data["s14_max"] = m.group(2)

    # 15. Sections
    section_map = {
        "= nipple": ["nipple"], 
        "= mass": ["mass"], 
        "= old biopsy cavity with fibrosis": ["fibrosis", "biopsy cavity", "old biopsy"], 
        "= deep resected margin": ["deep resected", "deep margin", "the resected"], 
        "= nearest resected margin": ["nearest resected", "nearest margin", "inferior resected", "superior resected"], 
        "= sampling upper inner quadrant": ["upper inner", "superior inner", "superior medial"], 
        "= sampling upper outer quadrant": ["upper outer", "superior outer", "superior lateral"], 
        "= sampling lower inner quadrant": ["lower inner", "inferior inner", "inferior medial"], 
        "= sampling lower outer quadrant": ["lower outer", "inferior outer", "inferior lateral"], 
        "= sampling central region": ["central"], 
        "= axillary lymph nodes": ["axillary"]
    }
    data["sections"] = {}
    for anchor, keywords in section_map.items():
        found = False
        for kw in keywords:
            # Pattern 1: A1, A2 = nipple
            pattern1 = rf"((?:[a-zA-Z]\s?-?\s?\d+(?:[-\s]?\d+)*(?:\s*(?:to|and|-|,)\s*)*)+)\s*(?:=|equals?|is|-|old|sampling|submitted as|with)?\s*{kw}"
            # Pattern 2: nipple = A1, A2 or nipple is A1
            pattern2 = rf"{kw}\s*(?:=|equals?|is|-|old|sampling|submitted as|with)?\s*((?:[a-zA-Z]\s?-?\s?\d+(?:[-\s]?\d+)*(?:\s*(?:to|and|-|,)\s*)*)+)"
            
            for pat in [pattern1, pattern2]:
                m = re.search(pat, t)
                if m:
                    raw_code = m.group(1)
                    clean_code = re.sub(r"\b(old|to|and|is|sampling|with)\b", "", raw_code, flags=re.IGNORECASE).strip()
                    # Clean up trailing punctuation if Pattern 2 matched text at end of sentence
                    clean_code = clean_code.rstrip(".,")
                    formatted_code = format_section_code(clean_code)
                    
                    extra_text = ""
                    if "nearest resected" in anchor or "deep resected" in anchor:
                        # Try to capture "with ..." after the code or keyword
                        suffix_match = re.search(rf"{kw}.*?{raw_code}\s+(with\s+[^,.]+)", t)
                        if not suffix_match: # Try after keyword if Pattern 1
                            suffix_match = re.search(rf"{raw_code}.*?{kw}\s+(with\s+[^,.]+)", t)
                            
                        if suffix_match:
                            extra_text = suffix_match.group(1).strip()
    
                    data["sections"][anchor] = {
                        "code": formatted_code,
                        "extra": extra_text
                    }
                    found = True
                    break
        if found: continue
    return data

# --- Drawing Functions ---

# --- FIX: Define Colors ---
RED = (1, 0, 0)
BLUE = (0, 0, 1)

def draw_tick(page, anchor_text, offset_x=-15, offset_y=5, search_instance=0):
    hits = page.search_for(anchor_text)
    if not hits: 
        hits = page.search_for(anchor_text.replace("(", "( ")) 
    if not hits or len(hits) <= search_instance: return
    
    rect = hits[search_instance]
    start_pt = fitz.Point(rect.x0 + offset_x + 2, rect.y1 - offset_y)
    
    # --- FIX: Checkmark Shape & Color ---
    # ใช้ 2 เส้นขีดให้เป็นตัว V (Tick) ชัดเจน ไม่ปิด path
    shape = page.new_shape()
    
    # จุดหักมุม (ก้นตัว V)
    bottom_pt = fitz.Point(start_pt.x + 3, start_pt.y + 4)
    # จุดปลาย (หางตัว V ชี้ขึ้น)
    end_pt = fitz.Point(start_pt.x + 8, start_pt.y - 6)
    
    shape.draw_line(start_pt, bottom_pt)
    shape.draw_line(bottom_pt, end_pt)
    
    # ใช้ finish() แบบ stroke เพื่อวาดเส้น ไม่เติมสี (ไม่เป็นสามเหลี่ยมทึบ)
    shape.finish(color=RED, width=1.5) 
    shape.commit()

def draw_circle(page, target_word, context_anchor=None):
    search_rect = None
    if context_anchor:
        ctx_hits = page.search_for(context_anchor)
        if not ctx_hits:
              ctx_hits = page.search_for(context_anchor.replace("(", "( "))
        if ctx_hits:
            r = ctx_hits[0]
            # STRICTER SEARCH RECT: Only look at the same line (slightly up/down for variance)
            # Avoid looking at the line above (y0 - 20 was too much)
            search_rect = fitz.Rect(0, r.y0 - 2, page.rect.width, r.y1 + 10)
    hits = page.search_for(target_word, clip=search_rect)
    if not hits: return
    best_hit = hits[0]
    rect = best_hit
    # DEBUG LOG
    print(f"DEBUG_DRAW: Word='{target_word}', Rect={rect}")

    # DEBUG: Draw raw detection box in GREEN - REMOVED

    # Draw the Red Circle directly on the detection rect
    shape = page.new_shape()
    # Expand slightly for visual comfort (text shouldn't touch the line)
    padding_x = 2
    padding_y = 1
    shape.draw_oval(fitz.Rect(rect.x0 - padding_x, rect.y0 - padding_y, rect.x1 + padding_x, rect.y1 + padding_y))
    
    # --- Circle stays RED ---
    shape.finish(color=RED, width=1.5)
    shape.commit()

def circle_multiline(page, loc_list, context_anchor, padding_x=5, padding_y=4, shift_x=0, shift_y=0):
    # Pass padding/shift params if needed, but for now just use draw_circle
    for loc in loc_list:
        draw_circle(page, loc, context_anchor=context_anchor)

def write_text(page, anchor_text, text, offset_x=5, offset_y=-3, align_left=False):
    # ... (no change here)
    hits = page.search_for(anchor_text)
    if not hits: return
    rect = hits[0]
    x = rect.x1 + offset_x
    if align_left:
        width = len(str(text)) * 6
        x = rect.x0 - width - offset_x
    y = rect.y1 + offset_y
    page.insert_text(fitz.Point(x, y), str(text), fontsize=10, fontname="helv", color=BLUE)

def write_spaced_dims(page, anchor_text, dims_list, start_offset=45, gap=40, instance=0, y_offset=-3):
    if not dims_list: return
    hits = page.search_for(anchor_text)
    if not hits or len(hits) <= instance: 
        print(f"DEBUG_DIMS: Anchor '{anchor_text}' NOT FOUND or instance {instance} out of range. Hits: {len(hits) if hits else 0}")
        return
    rect = hits[instance]
    print(f"DEBUG_DIMS: Anchor '{anchor_text}' Found. Rect: {rect}. Instance: {instance}")
    current_x = rect.x1 + start_offset
    y = rect.y1 + y_offset
    
    for val in dims_list:
        page.insert_text(fitz.Point(current_x, y), str(val), fontsize=10, fontname="helv", color=BLUE)
        current_x += gap

def convert_to_docx(pdf_file, docx_file):
    cv = Converter(pdf_file)
    cv.convert(docx_file, start=0, end=None)
    cv.close()

def process_pdf_15_sections(template_path, output_path, data):
    print(f"!!! PDF GENERATION STARTED for {output_path} !!!")
    doc = fitz.open(template_path)
    page = doc[0]

    # DEBUG: Explicit Text Mark REMOVED

    
    # (Removed Giant Red Block)

    # DEBUG: Visual Verification of Update
    
    with open("debug_log.txt", "a") as f:
        f.write(f"\n--- GEN {datetime.datetime.now()} ---\n")
        f.write(f"s10_prev2_cavity_dims: {data.get('s10_prev2_cavity_dims')}\n")
        f.write(f"s10_prev2_mass_dims: {data.get('s10_prev2_mass_dims')}\n")
        f.write(f"s13: {data.get('s13_type')} {data.get('s13_text')}\n")

    if data.get("s0_surgical_no"):
        # Adjust position as needed based on template
        write_text(page, "Surgical Number S", data["s0_surgical_no"], offset_x=90)

    # Sections 1-9
    if data.get("s1_side"): draw_circle(page, data["s1_side"], context_anchor="Received in formalin")
    if data.get("s2_proc") == "modified": draw_tick(page, "modified radical mastectomy")
    elif data.get("s2_proc") == "simple": draw_tick(page, "simple mastectomy")
    elif data.get("s2_proc") == "other":
        # Robust fix: Find "simple mastectomy specimen", then find box to its RIGHT
        hits = page.search_for("simple mastectomy specimen")
        if hits:
            anchor = hits[0]
            # Clip right
            clip_right = fitz.Rect(anchor.x1, anchor.y0 - 5, page.rect.width, anchor.y1 + 5)
            box_hits = page.search_for("☐", clip=clip_right)
            if box_hits:
                box_rect = box_hits[0]
                center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
                shape = page.new_shape()
                p1 = fitz.Point(center.x - 4, center.y - 2)
                p2 = fitz.Point(center.x, center.y + 4)
                p3 = fitz.Point(center.x + 5, center.y - 6)
                shape.draw_line(p1, p2)
                shape.draw_line(p2, p3)
                shape.finish(color=RED, width=1.5)
                shape.commit()
            else:
                 draw_tick(page, "simple mastectomy", offset_x=220)
        else:
             draw_tick(page, "simple mastectomy", offset_x=220)
             
        if data.get("s2_other_text"): write_text(page, "simple mastectomy", data["s2_other_text"], offset_x=240)
    if data.get("s3_dims"): write_spaced_dims(page, "Measuring", data["s3_dims"], start_offset=15, gap=40)
    if data.get("s4_check"):
        draw_tick(page, "with axillary content")
        if data.get("s4_dims"): write_spaced_dims(page, "with axillary content", data["s4_dims"], start_offset=15, gap=40)
    if data.get("s5_dims"): write_spaced_dims(page, "The skin ellipse", data["s5_dims"], start_offset=20, gap=40)
    
    # FIX: Correct key s5_appears_normal
    if data.get("s5_appears_normal"):
        hits = page.search_for("appears normal")
        if hits:
            anchor = hits[0]
            clip_left = fitz.Rect(anchor.x0 - 50, anchor.y0 - 5, anchor.x0, anchor.y1 + 5)
            box_hits = page.search_for("☐", clip=clip_left)
            if box_hits:
                box_rect = box_hits[-1]
                center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
                shape = page.new_shape()
                p1 = fitz.Point(center.x - 4, center.y - 2)
                p2 = fitz.Point(center.x, center.y + 4)
                p3 = fitz.Point(center.x + 5, center.y - 6)
                shape.draw_line(p1, p2)
                shape.draw_line(p2, p3)
                shape.finish(color=RED, width=1.5)
                shape.commit()
            else:
                 draw_tick(page, "appears normal", offset_x=-20)
        else:
             draw_tick(page, "appears normal", offset_x=-20)

    # FIX: Scar uses s6_check
    if data.get("s6_check"):
        draw_tick(page, "shows an old surgical scar")
        # Text alignment: Anchor to "cm in length" and write to the LEFT of start point
        # "shows an old surgical scar ......... cm"
        # We want the number ON the dots, just before "cm".
        if data.get("s7_len"): 
            write_text(page, "cm in length", data["s7_len"], offset_x=15, align_left=True)
        if data.get("s7_locs"): circle_multiline(page, data["s7_locs"], context_anchor="shows an old surgical scar")

    if data.get("s8_check"):
        draw_tick(page, "shows an ulceration")
        # Adjust start_offset for ulceration dims
        if data.get("s8_dims"): write_spaced_dims(page, "shows an ulceration", data["s8_dims"], start_offset=25, gap=55)
        if data.get("s8_locs"): circle_multiline(page, data["s8_locs"], context_anchor="shows an ulceration")
    
    if data.get("s9_val"):
        vals = data["s9_val"]
        if isinstance(vals, str): vals = [vals]
        
        if "everted" in vals: draw_tick(page, "is everted", offset_x=-15)
        if "inverted" in vals: draw_tick(page, "shows inverted", offset_x=-20)
        
        if "ulceration" in vals:
            # Robust Search for Nipple > Ulceration
            n_hits = page.search_for("The nipple")
            target_rect = None
            if n_hits:
                row_y = n_hits[0].y0
                # Search for "ulceration" below this line
                u_hits = page.search_for("ulceration")
                for h in u_hits:
                    if h.y0 >= row_y - 5 and h.y0 < row_y + 40:
                        target_rect = h
                        break
            
            if target_rect:
                 # Find Checkbox to LEFT of text
                 clip_left = fitz.Rect(target_rect.x0 - 80, target_rect.y0 - 5, target_rect.x0, target_rect.y1 + 5)
                 box_hits = page.search_for("☐", clip=clip_left)
                 if box_hits:
                     b = box_hits[-1]
                     center = fitz.Point((b.x0 + b.x1)/2, (b.y0 + b.y1)/2)
                     shape = page.new_shape()
                     shape.draw_line(fitz.Point(center.x-4, center.y-2), fitz.Point(center.x, center.y+4))
                     shape.draw_line(fitz.Point(center.x, center.y+4), fitz.Point(center.x+5, center.y-6))
                     shape.finish(color=RED, width=1.5)
                     shape.commit()
                 else:
                     draw_tick(page, "shows ulceration", search_instance=-1)
            else:
                 # Fallback
                 draw_tick(page, "shows ulceration", search_instance=-1)
            
            if data.get("s9_ulcer_text"):
                 # Write text on dots if needed (offset to right of "shows ulceration")
                 # Just use simple offset for now if user entered text
                 pass

    # 10. Mass
    if data.get("s10_grammar"): draw_circle(page, data["s10_grammar"], context_anchor="There (")

    if data.get("s10_infiltrative"):
        draw_tick(page, "infiltrative")
        if data.get("s10_inf_dims"):
            # FIX: Use "yellow white mass" as anchor for better precision
            # "yellow white mass" ends, then comma, then space. Offset ~25 should hit first blank.
            write_spaced_dims(page, "yellow white mass", data["s10_inf_dims"], start_offset=30, gap=45)

    if data.get("s10_well"):
        draw_tick(page, "well")
        if data.get("s10_well_dims"): write_spaced_dims(page, "slit like appearance", data["s10_well_dims"], start_offset=30, gap=42)

    if data.get("s10_prev1"):
        draw_tick(page, "previous surgical cavity", search_instance=0)
        if data.get("s10_prev1_dims"): write_spaced_dims(page, "adjacent fibrous tissue", data["s10_prev1_dims"], start_offset=35, instance=0, gap=45)

    if data.get("s10_prev2"):
        draw_tick(page, "previous surgical cavity", search_instance=1)
        # Shift Y up slightly for adjacent
        if data.get("s10_prev2_cavity_dims"): 
            # Anchor: "adjacent fibrous tissue"
            # Text: "...adjacent fibrous tissue , ......... x"
            # Let's use "adjacent fibrous tissue" explicitly.
            # FIX: Use instance=1 because "adjacent fibrous tissue" appears in the previous line too!
            write_spaced_dims(page, "adjacent fibrous tissue", data["s10_prev2_cavity_dims"], start_offset=25, instance=1, gap=45, y_offset=-3)
        
        # Shift Y up MORE for residual mass
        if data.get("s10_prev2_mass_dims"): 
             # Anchor: "residual mass" (more robust)
             # In PDF: "... residual mass , ......... x"
             # Dots start after comma.
             write_spaced_dims(page, "residual mass", data["s10_prev2_mass_dims"], start_offset=30, gap=45, y_offset=-3, instance=-1)

    # 10.5 Location (Fixed Anchor)
    if data.get("s10_5_nipple"): draw_tick(page, "beneath the nipple")
    if data.get("s10_5_scar"): draw_tick(page, "beneath the scar")
    if data.get("s10_5_central"): draw_tick(page, "in the central portion")
    
    if data.get("s10_5_quadrant_check"):
        # ROBUST FIX: Locate the "in ( upper" text, then find the ☐ glyph to its left.
        # Debugging showed "in (" is at x~121.
        
        # 1. Find the anchor line text
        anchor_hits = page.search_for("in ( upper")
        if not anchor_hits:
             # Fallback: try just "in (" and verify "upper" is near
             anchor_hits = [r for r in page.search_for("in (") if page.search_for("upper", clip=fitz.Rect(r.x1, r.y0-5, page.rect.width, r.y1+5))]
        
        box_rect = None
        if anchor_hits:
            anchor = anchor_hits[0]
            # 2. Search for "☐" to the LEFT of the anchor
            # Define a clip rect to the left: x=0 to x=anchor.x0
            clip_left = fitz.Rect(0, anchor.y0 - 2, anchor.x0, anchor.y1 + 2)
            box_hits = page.search_for("☐", clip=clip_left)
            
            if box_hits:
                # The closest one to the text is the last one (rightmost in the left clip)
                box_rect = box_hits[-1]
            else:
                # Fallback if glyph not found: Approximate based on x0 (x - 18)
                # "in (" is at 121.3. Box is likely around 103-105.
                box_rect = fitz.Rect(anchor.x0 - 18, anchor.y0, anchor.x0 - 8, anchor.y1)
        
        if box_rect:
            # Draw tick centered on the box
            # Box is usually ~10x10.
            center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
            
            # V-shape tick
            shape = page.new_shape()
            # Start slightly left-up
            p1 = fitz.Point(center.x - 4, center.y - 2)
            p2 = fitz.Point(center.x, center.y + 4)
            p3 = fitz.Point(center.x + 5, center.y - 6)
            
            shape.draw_line(p1, p2)
            shape.draw_line(p2, p3)
            shape.finish(color=RED, width=1.5)
            shape.commit()
            
            # Circles
            if data.get("s10_5_quadrant_vals"):
                # Use the anchor line y-bounds for clipping circles
                clip_rect = fitz.Rect(0, anchor.y0 - 10, page.rect.width, anchor.y1 + 10)
                for q in data["s10_5_quadrant_vals"]:
                     # Apply tweaks for quadrants
                     q_pad_x = 5
                     q_sh_x = 0
                     if q == "inner": q_pad_x = 4
                     if q == "outer": q_pad_x = 4
                     
                     circle_multiline(page, [q], context_anchor="in ( upper", 
                                     padding_x=q_pad_x, padding_y=4, shift_x=q_sh_x, shift_y=0)

    if data.get("s10_5_other"):
         # Anchor: "quadrant" (end of the line)
         # Find "quadrant" at roughly same Y as the quadrant check (or just search "quadrant" followed by box)
         # Debug output showed 'quadrant' at x~254 (for this line).
         
         # Strategy: Find "quadrant" that is to the right of "in ("
         # or just "quadrant ." in the text
         
         # 1. Find anchor "in (" to establish Y-level
         anchor_hits = page.search_for("in (")
         if anchor_hits:
             anchor = anchor_hits[0]
             # 2. Look for "quadrant" on this line
             line_rect = fitz.Rect(anchor.x1, anchor.y0 - 5, page.rect.width, anchor.y1 + 5)
             q_hits = page.search_for("quadrant", clip=line_rect)
             
             if q_hits:
                 q_rect = q_hits[0]
                 # 3. Look for box to the RIGHT of quadrant
                 right_clip = fitz.Rect(q_rect.x1, q_rect.y0 - 5, page.rect.width, q_rect.y1 + 5)
                 box_hits = page.search_for("☐", clip=right_clip)
                 
                 target_box = None
                 if box_hits:
                     target_box = box_hits[0]
                 else:
                     # Fallback offset: quadrant ends ~290. Box is at ~320?
                     target_box = fitz.Rect(q_rect.x1 + 35, q_rect.y0, q_rect.x1 + 45, q_rect.y1)
                 
                 if target_box:
                    # Tick
                    center = fitz.Point((target_box.x0 + target_box.x1)/2, (target_box.y0 + target_box.y1)/2)
                    shape = page.new_shape()
                    p1 = fitz.Point(center.x - 4, center.y - 2)
                    p2 = fitz.Point(center.x, center.y + 4)
                    p3 = fitz.Point(center.x + 5, center.y - 6)
                    shape.draw_line(p1, p2)
                    shape.draw_line(p2, p3)
                    shape.finish(color=RED, width=1.5)
                    shape.commit()
                    
                    # Write Text
                    # Dotted line starts after box
                    page.insert_text(fitz.Point(target_box.x1 + 5, target_box.y1 - 2), str(data["s10_5_other"]), fontsize=10, fontname="helv", color=BLUE)

    margin_anchors = {
        "s11_deep": "cm. from deep margin", "s11_superior": "cm. from superior margin",
        "s11_inferior": "cm. from inferior margin", "s11_medial": "cm. from medial margin",
        "s11_lateral": "cm. from lateral margin", "s11_skin": "cm. from skin"
    }
    for key, anchor in margin_anchors.items():
        val = data.get(key)
        if val: write_text(page, anchor, val, align_left=True, offset_x=10)

    if data.get("s11_margin_right"):
        # Anchor check: "nearest resected margin" (on right)
        # But we don't have that anchor clearly defined in margin_anchors.
        # Let's use "nearest resected margin"
        write_text(page, "nearest resected margin", data["s11_margin_right"], align_left=True, offset_x=10)

    if data.get("s12_check"):
        draw_tick(page, "The uninvolved breast")
        hits = page.search_for("ratio of approximately")
        if hits:
            rect = hits[0]
            colon_x = rect.x1 + 30
            # --- FIX: Text color to BLUE ---
            if data.get("s12_val_left"): page.insert_text(fitz.Point(colon_x - 15, rect.y1 - 3), str(data["s12_val_left"]), fontsize=10, fontname="helv", color=BLUE)
            if data.get("s12_val_right"): page.insert_text(fitz.Point(colon_x + 10, rect.y1 - 3), str(data["s12_val_right"]), fontsize=10, fontname="helv", color=BLUE)

    if data.get("s13_type") == "unremarkable": 
        # Tick the FIRST box on this line (left of "is unremarkable")
        # Robust search for box
        hits = page.search_for("is unremarkable")
        if hits:
            anchor = hits[0]
            # Clip left
            clip_left = fitz.Rect(anchor.x0 - 50, anchor.y0 - 5, anchor.x0, anchor.y1 + 5)
            box_hits = page.search_for("☐", clip=clip_left)
            if box_hits:
                # Use the one closest to text (rightmost in clip)
                box_rect = box_hits[-1]
                center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
                shape = page.new_shape()
                p1 = fitz.Point(center.x - 4, center.y - 2)
                p2 = fitz.Point(center.x, center.y + 4)
                p3 = fitz.Point(center.x + 5, center.y - 6)
                shape.draw_line(p1, p2)
                shape.draw_line(p2, p3)
                shape.finish(color=RED, width=1.5)
                shape.commit()
            else:
                draw_tick(page, "is unremarkable", offset_x=-20) 
    elif data.get("s13_type") == "other":
        # Tick the SECOND box on this line (right of "is unremarkable")
        # Strategy: Find "is unremarkable", then find box to its right.
        hits = page.search_for("is unremarkable")
        if hits:
            anchor = hits[0]
            # Define clip rect to the right of the text
            right_clip = fitz.Rect(anchor.x1, anchor.y0 - 5, page.rect.width, anchor.y1 + 5)
            box_hits = page.search_for("☐", clip=right_clip)
            if box_hits:
                box_rect = box_hits[0] # The first box to the right
                # Draw tick on this box
                center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
                shape = page.new_shape()
                p1 = fitz.Point(center.x - 4, center.y - 2)
                p2 = fitz.Point(center.x, center.y + 4)
                p3 = fitz.Point(center.x + 5, center.y - 6)
                shape.draw_line(p1, p2)
                shape.draw_line(p2, p3)
                shape.finish(color=RED, width=1.5)
                shape.commit()
            else:
                 # Fallback offset
                 draw_tick(page, "is unremarkable", offset_x=100)
        
        if data.get("s13_text"): write_text(page, "is unremarkable", data["s13_text"], offset_x=120)

    if data.get("s14_check"):
        draw_tick(page, "There are multiple lymph nodes")
        if data.get("s14_min"): write_text(page, "ranging from", data["s14_min"])
        if data.get("s14_max"): write_text(page, "cm . to", data["s14_max"])

    for anchor, item in data.get("sections", {}).items():
        if isinstance(item, dict):
            write_text(page, anchor, item["code"], align_left=True, offset_x=10)
            if item["extra"]:
                hits = page.search_for(anchor)
                if hits:
                    rect = hits[0]
                    # --- FIX: Text color to BLUE ---
                    page.insert_text(fitz.Point(rect.x1 + 40, rect.y1 - 3), f", {item['extra']}", fontsize=10, fontname="helv", color=BLUE)
        else:
            write_text(page, anchor, item, align_left=True, offset_x=10)

    # Footer
    if data.get("footer_prosecutor"): 
        # "Prosecutor" search might find the word.
        # Layout dump: ".................................................Prosecutor"
        # We want text on the dots.
        # Start of dots is ~166 pt left of end of "Prosecutor".
        # Try offset_x = -170 relative to x1 of "Prosecutor".
        write_text(page, "Prosecutor", data["footer_prosecutor"], offset_x=-170)
        
    if data.get("footer_date"):
        # Write user-provided date if available, else current time
        write_text(page, "Date", data["footer_date"], offset_x=20)
    else:
        current_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        write_text(page, "Date", current_time, offset_x=20)

    doc.save(output_path)
    doc.close()

# --- Routes ---

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        transcription = None
        
        # 1. Handle Direct Text Input (from Web Audio API)
        if request.form.get('transcription_text'):
            transcription = request.form.get('transcription_text')
            print(f"Received Direct Transcription: {transcription}")

        # 2. Handle Audio Upload (Fallback/Alternative)
        audio_file = request.files.get('audio_file')
        if audio_file and audio_file.filename != '':
            # Use secure_filename for safety
            from werkzeug.utils import secure_filename
            filename = secure_filename(audio_file.filename)
            audio_path = UPLOAD_DIR / filename # Using UPLOAD_DIR for consistency
            audio_file.save(audio_path)
            print(f"Audio saved to {audio_path}")

            try:
                # FIX: Audio Transcription Lock to prevent KV cache collision
                import threading
                if not hasattr(app, "model_lock"):
                     app.model_lock = threading.Lock()
                     
                with app.model_lock:
                    transcription_result = model.transcribe(str(audio_path), language="en") # Added language="en" for consistency
                transcription = transcription_result['text']
                print(f"Transcription from Audio: {transcription}")
            except Exception as e:
                print(f"Error during transcription: {e}")
                transcription = "Error during transcription"

        # 3. Process Transcription (if any)
        data = {}
        if transcription:
             data = extract_data_15_sections(transcription)
        
        # Render with extracted data
        return render_template('index.html', transcription=transcription, data=data)

    return render_template("index.html")

@app.route("/generate", methods=["GET", "POST"])
def generate_pdf():
    if request.method == "GET":
        return redirect(url_for("index"))

    # 1. Reconstruct Data from Form
    form_data = request.form
    data = {}
    
    # Simple strings
    # ADDED: footer_prosecutor, footer_date, s11_margin_right
    # Note: s9_val moved to list handling below
    for field in ["s0_surgical_no", "s1_side", "s2_proc", "s2_other_text", "s7_len", 
                  "s9_ulcer_text", "s10_grammar", "s10_5_other",
                  "s11_deep", "s11_superior", "s11_inferior", "s11_medial", "s11_lateral", "s11_skin", "s11_margin_right",
                  "s12_val_left", "s12_val_right", "s13_type", "s13_text", "s14_min", "s14_max",
                  "footer_prosecutor", "footer_date"]:
        if form_data.get(field):
            data[field] = form_data.get(field)

    # List Checkboxes that might have multiple values (Locations, s9_val)
    for key in ["s7_locs", "s8_locs", "s10_5_quadrant_vals", "s9_val"]:
        vals = request.form.getlist(key)
        if vals: data[key] = vals

    # Dimensions (lists)
    for dim_key in ["s3_dims", "s4_dims", "s5_dims", "s8_dims", 
                    "s10_inf_dims", "s10_well_dims", "s10_prev1_dims", 
                    "s10_prev2_cavity_dims", "s10_prev2_mass_dims"]:
        dims = []
        # Check indices 0, 1, 2
        d0 = form_data.get(f"{dim_key}_0")
        d1 = form_data.get(f"{dim_key}_1")
        d2 = form_data.get(f"{dim_key}_2")
        
        if d0: dims.append(d0)
        if d1: dims.append(d1)
        if d2: dims.append(d2)
        
        if dims: data[dim_key] = dims

    # Checkboxes (presence = True)
    for chk in ["s4_check", "s5_appears_normal", "s6_check", "s7_check", "s8_check", 
                "s10_infiltrative", "s10_well", "s10_prev1", "s10_prev2",
                "s10_5_nipple", "s10_5_scar", "s10_5_central",
                "s12_check", "s14_check"]:
        if form_data.get(chk):
            data[chk] = True
            
    # List Checkboxes (Locations)
    for key in ["s7_locs", "s8_locs", "s10_5_quadrant_vals"]:
        vals = request.form.getlist(key)
        if vals: data[key] = vals

    # Infer quadrant check if values are selected
    if data.get("s10_5_quadrant_vals"):
        data["s10_5_quadrant_check"] = True

    # Sections (Nested Dict)
    data["sections"] = {}
    section_map = {
        "= nipple": "sec_nipple",
        "= mass": "sec_mass",
        "= old biopsy cavity with fibrosis": "sec_old_biopsy",
        "= deep resected margin": "sec_deep_margin",
        "= nearest resected margin": "sec_nearest_margin",
        "= sampling upper inner quadrant": "sec_upper_inner",
        "= sampling upper outer quadrant": "sec_upper_outer",
        "= sampling lower inner quadrant": "sec_lower_inner",
        "= sampling lower outer quadrant": "sec_lower_outer",
        "= sampling central region": "sec_central",
        "= axillary lymph nodes": "sec_axillary"
    }
    
    for anchor, form_name in section_map.items():
        code = form_data.get(form_name)
        if code:
            # Always structure as a dict {code, extra} for consistency with template .get('code') logic
            extra = ""
            if "nearest" in anchor or "deep" in anchor:
                # Also safe name for extra
                safe_key_extra = form_name.replace("sec_", "sec_extra_")
                extra = form_data.get(safe_key_extra, "")
            data["sections"][anchor] = {"code": code, "extra": extra}

    # 3. Generate PDF
    import time
    uid = uuid.uuid4().hex
    timestamp = int(time.time())
    pdf_filename = f"final_{uid}_{timestamp}.pdf"
    docx_filename = f"final_{uid}_{timestamp}.docx"
    
    pdf_path = OUTPUT_DIR / pdf_filename
    docx_path = OUTPUT_DIR / docx_filename
    
    # Ensure template exists
    if not PDF_TEMPLATE_PATH.exists():
        return f"Error: Template not found at {PDF_TEMPLATE_PATH}"
        
    process_pdf_15_sections(PDF_TEMPLATE_PATH, pdf_path, data)
    
    # 3.5 Convert to DOCX
    try:
        convert_to_docx(str(pdf_path), str(docx_path))
    except Exception as e:
        print(f"Error converting to DOCX: {e}")
        docx_filename = None # Fallback if conversion fails
    
    # 4. Show Result in the SAME editor page (Split View)
    # Pass data back so inputs remain filled
    return render_template("index.html", 
                           pdf_filename=pdf_filename, 
                           docx_filename=docx_filename,
                           transcription=form_data.get("transcription"),
                           data=data)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7861)