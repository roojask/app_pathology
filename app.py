import os
import json
import re
import uuid
import datetime
from pathlib import Path
import fitz # PyMuPDF
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except ImportError:
    print("WARNING: spacy is not installed. NLP fallback will be disabled.")
    nlp = None
except OSError:
    print("WARNING: en_core_web_sm model not found. NLP fallback will be disabled.")
    nlp = None

from flask import Flask, render_template, request, send_from_directory, redirect, url_for, flash
import whisper
from pdf2docx import Converter

# --- New Imports for DB & Auth ---
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

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

# ==========================================
# --- Database & Authentication Setup ---
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(150), nullable=True)
    histories = db.relationship('FormHistory', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class FormHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    surgical_number = db.Column(db.String(100), nullable=True)
    form_data = db.Column(db.Text, nullable=False) # Store JSON string of data dict
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# ==========================================

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
    t = re.sub(r"\bx\s+(?:cm|centimeters?)\s+from", "8 cm from", t)
    # --- Specific Fixes (แก้คำผิด) ---
    t = t.replace("mast", "mass") 
    t = t.replace("medium margin", "medial margin")
    t = t.replace("massectomy", "mastectomy")
    t = t.replace("slit-like", "slit like")
    t = t.replace("the resected", "deep resected")
    
    # FIX: แก้ ASR error "nipple is inverted" -> "nipple is everted"
    t = t.replace("nipple is inverted", "nipple is everted")
    
    return t

def format_section_code(code):
    code = re.sub(r"\b(to|and|-)\b", " - ", code, flags=re.IGNORECASE)
    code = re.sub(r"([A-Za-z]\d+)([A-Za-z])", r"\1 \2", code)
    code = code.upper()
    
    parts = re.split(r"[;,]", code)
    formatted_parts = []
    for p in parts:
        if not p: continue
        sub_parts = re.split(r"[\s\-]+", p.strip())
        formatted_sub = []
        for sp in sub_parts:
            sp = sp.strip()
            if not sp: continue
            if re.match(r"^[A-Z]\d{2,}$", sp):
                sp = f"{sp[0]}{sp[1]}-{sp[2:]}"
            formatted_sub.append(sp)
        formatted_parts.append("-".join(formatted_sub))
    return ",".join(formatted_parts)

def extract_data_15_sections(text):
    t = normalize_text(text)
    data = {"_low_confidence": []}

    m = re.search(r"surgical number\s+([a-zA-Z0-9\/-]+)", t)
    if m: data["s0_surgical_no"] = m.group(1).upper()

    if "right" in t: data["s1_side"] = "right"
    elif "left" in t: data["s1_side"] = "left"

    if "modified radical" in t: data["s2_proc"] = "modified"
    elif "simple mastectomy" in t: data["s2_proc"] = "simple"
    else:
        m = re.search(r"procedure is (.+)", t)
        if m: 
            data["s2_proc"] = "other"
            data["s2_other_text"] = m.group(1).strip()
            data["_low_confidence"].append("s2_other_text")

    m = re.search(r"specimen measuring\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
    if m: data["s3_dims"] = [m.group(1), m.group(2), m.group(3)]
    elif "measuring" in t:
        data["_low_confidence"].extend(["s3_dims_0", "s3_dims_1", "s3_dims_2"])
        
    if "axillary content" in t:
        data["s4_check"] = True
        m = re.search(r"axillary content.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
        if m: data["s4_dims"] = [m.group(1), m.group(2), m.group(3)]

    m = re.search(r"skin ellipse.*?\s+([\d.]+)\s*x\s*([\d.]+)", t)
    if m: data["s5_dims"] = [m.group(1), m.group(2)]

    if "appears normal" in t: data["s5_appears_normal"] = True

    if "scar" in t:
        data["s6_check"] = True 
        m = re.search(r"scar\s+([\d.]+)\s*cm", t)
        if m: data["s7_len"] = m.group(1)
        
        scar_idx = t.find("scar")
        if scar_idx != -1:
            context = t[scar_idx:scar_idx+100]
            locs = []
            for l in ["upper", "lower", "inner", "outer", "areola"]:
                if l in context: locs.append(l)
            if locs: data["s7_locs"] = locs

    ulcer_match = re.search(r"ulceration", t)
    if ulcer_match:
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

    s9_vals = []
    t_lower = t.lower()
    if "nipple" in t_lower:
         if "everted" in t_lower: s9_vals.append("everted")
         if "inverted" in t_lower: s9_vals.append("inverted")
         
         for m in re.finditer("ulceration", t_lower):
              start = m.start()
              context = t_lower[max(0, start-50):start]
              if "nipple" in context:
                   if "ulceration" not in s9_vals: s9_vals.append("ulceration")
              elif "shows" in context and "an" not in context[-5:]: 
                   if "ulceration" not in s9_vals: s9_vals.append("ulceration")
    
    if s9_vals: data["s9_val"] = s9_vals

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

    if "previous surgical cavity" in t:
        if "residual mass" not in t:
            mass_count += 1
            data["s10_prev1"] = True
            mass_types.append("prev1")
            m = re.search(r"previous surgical cavity.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
            if m: data["s10_prev1_dims"] = [m.group(1), m.group(2), m.group(3)]
        else:
            mass_count += 2
            data["s10_prev1"] = True
            mass_types.append("prev1")
            m1 = re.search(r"previous surgical cavity.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
            if m1: data["s10_prev1_dims"] = [m1.group(1), m1.group(2), m1.group(3)]
            
            data["s10_prev2"] = True
            mass_types.append("prev2")
            if m1: data["s10_prev2_cavity_dims"] = [m1.group(1), m1.group(2), m1.group(3)]
            m2 = re.search(r"residual mass.*?\s+([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)", t)
            if not m2:
                 m2 = re.search(r"residual mass.*?([\d.]+)\s*(?:x|by)\s*([\d.]+)\s*(?:x|by)\s*([\d.]+)", t)
            if m2: data["s10_prev2_mass_dims"] = [m2.group(1), m2.group(2), m2.group(3)]

    if mass_count == 1:
        data["s10_grammar"] = "is an" if mass_types[0] == "infiltrative" else "is a"
    elif mass_count == 2:
        data["s10_grammar"] = "are two"
    elif mass_count > 2:
        data["s10_grammar"] = "are multiple"

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

    t = t.replace("comma", ",")
    t = t.replace("  ", " ") 
    
    m = re.search(r"(?<!tumor is\s)located.*?(?:in|at)\s+(?!(?:the)?\s*(?:upper|lower|inner|outer|central|nipple|scar))(.+?)(?:\.|$|tumor)", t)
    if m:
        candidate = m.group(1).strip()
        if len(candidate) > 2 and "margin" not in candidate and not re.match(r"^[\d\s.,]+$", candidate):
             data["s10_5_other"] = candidate

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

    m = re.search(r"ratio.*?\b(\d+)\s*(?::|to)\s*(\d+)", t)
    if m: 
        data["s12_check"] = True
        data["s12_val_left"] = m.group(1)
        data["s12_val_right"] = m.group(2)

    if "unremarkable" in t:
        data["s13_type"] = "unremarkable"
    elif "remaining of breast tissue" in t:
         m = re.search(r"remaining of breast tissue (?:is|shows) (.+)", t)
         if m: 
             data["s13_type"] = "other"
             data["s13_text"] = m.group(1).split('.')[0].split(',')[0]

    if "lymph node" in t:
        data["s14_check"] = True
        m = re.search(r"ranging from\s+([\d.]+).*?to\s+([\d.]+)", t)
        if m: 
            data["s14_min"] = m.group(1)
            data["s14_max"] = m.group(2)

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
    
    if "representative sections are submitted as" in t and not data["sections"]:
        data["_low_confidence"].extend(["sec_nipple", "sec_mass", "sec_old_biopsy", "sec_deep_margin"])

    for anchor, keywords in section_map.items():
        found = False
        for kw in keywords:
            pattern1 = rf"((?:[a-zA-Z]\s?-?\s?\d+(?:[-\s]?\d+)*(?:\s*(?:to|and|-|,)\s*)*)+)(?:\s*(?:=|equals?|is|-|old|sampling|submitted as|with))*\s*{kw}"
            pattern2 = rf"{kw}(?:\s*(?:=|equals?|is|-|old|sampling|submitted as|with))*\s*((?:[a-zA-Z]\s?-?\s?\d+(?:[-\s]?\d+)*(?:\s*(?:to|and|-|,)\s*)*)+)"
            
            for pat in [pattern1, pattern2]:
                m = re.search(pat, t)
                if m:
                    raw_code = m.group(1)
                    clean_code = re.sub(r"\b(old|is|sampling|with)\b", "", raw_code, flags=re.IGNORECASE).strip()
                    clean_code = clean_code.rstrip(".,")
                    formatted_code = format_section_code(clean_code)
                    
                    extra_text = ""
                    if "nearest resected" in anchor or "deep resected" in anchor:
                        suffix_match = re.search(rf"{kw}\s*(margin)?\s+(with\s+[^,.]+)", t)
                        if suffix_match:
                            extra_text = suffix_match.group(2).strip()
                        else:
                            suffix_match = re.search(rf"{raw_code}.*?{kw}\s*(margin)?\s+(with\s+[^,.]+)", t)
                            if suffix_match:
                                extra_text = suffix_match.group(2).strip()

                    data["sections"][anchor] = {
                        "code": formatted_code,
                        "extra": extra_text
                    }
                    found = True
                    break
        if found: continue

    if nlp is not None:
        data = enhance_extraction_with_nlp(t, data)

    return data

def enhance_extraction_with_nlp(text, data):
    doc = nlp(text)
    
    if "s3_dims" not in data and "measuring" in text:
        dims = []
        for token in doc:
            if token.like_num or re.match(r'^[\d.]+$', token.text):
                dims.append(token.text)
                if len(dims) == 3:
                    break
        if len(dims) == 3:
            data["s3_dims"] = dims
                
    margins_to_check = {
        "deep": "s11_deep", "superior": "s11_superior", "inferior": "s11_inferior", 
        "medial": "s11_medial", "lateral": "s11_lateral", "skin": "s11_skin"
    }
    
    for margin_word, key in margins_to_check.items():
        if key not in data:
            for token in doc:
                if margin_word in token.text.lower():
                    window_start = max(0, token.i - 5)
                    window_tokens = doc[window_start:token.i]
                    for w in window_tokens:
                        if w.like_num or re.match(r'^[\d.]+$', w.text):
                            data[key] = w.text
                    
    return data

# =========================================================
# --- ฟังก์ชัน: ตรวจสอบความมั่นใจและเตือนจุดผิดพลาด ---
# =========================================================
def generate_confidence_flags(extracted_data):
    """
    ตรวจสอบข้อมูลที่สกัดมาได้ หากพบว่าน่าจะผิดพลาด ขาดหาย หรือ Regex หาไม่เจอ 
    ให้คืนค่า True เพื่อส่งไปแจ้งเตือนบนหน้าเว็บ (ไฮไลต์สีเหลือง)
    """
    flags = {}
    
    # 1. เช็ค Surgical Number (ถ้าหาไม่เจอ)
    if not extracted_data.get("s0_surgical_no") or extracted_data.get("s0_surgical_no").strip() == "":
        flags["s0_surgical_no"] = True

    # 2. เช็คขนาดชิ้นเนื้อ (ถ้าหาไม่เจอ ขาดบางมิติ หรือไม่มีตัวเลขเลย)
    s3_dims = extracted_data.get("s3_dims", [])
    if not s3_dims or len(s3_dims) < 3 or not any(char.isdigit() for char in str(s3_dims)):
        flags["s3_dims"] = True

    # 3. เช็คขนาดก้อนเนื้อ (ถ้าพบว่าระบุก้อนเนื้อ แต่ดันลืมพูดขนาด หรือ AI ฟังไม่ออก)
    has_mass = extracted_data.get("s10_infiltrative") or extracted_data.get("s10_well")
    if has_mass:
        inf_dims = extracted_data.get("s10_inf_dims", [])
        well_dims = extracted_data.get("s10_well_dims", [])
        
        if extracted_data.get("s10_infiltrative") and (not inf_dims or len(inf_dims) < 3):
            flags["mass_dimensions"] = True
            
        if extracted_data.get("s10_well") and (not well_dims or len(well_dims) < 3):
            flags["mass_dimensions"] = True

    return flags

# --- Drawing Functions ---
RED = (1, 0, 0)
BLUE = (0, 0, 1)

def draw_tick(page, anchor_text, offset_x=-15, offset_y=5, search_instance=0):
    hits = page.search_for(anchor_text)
    if not hits: 
        hits = page.search_for(anchor_text.replace("(", "( ")) 
    if not hits or len(hits) <= search_instance: return
    
    rect = hits[search_instance]
    start_pt = fitz.Point(rect.x0 + offset_x + 2, rect.y1 - offset_y)
    
    shape = page.new_shape()
    bottom_pt = fitz.Point(start_pt.x + 3, start_pt.y + 4)
    end_pt = fitz.Point(start_pt.x + 8, start_pt.y - 6)
    
    shape.draw_line(start_pt, bottom_pt)
    shape.draw_line(bottom_pt, end_pt)
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
            search_rect = fitz.Rect(0, r.y0 - 2, page.rect.width, r.y1 + 10)
    hits = page.search_for(target_word, clip=search_rect)
    if not hits: return
    best_hit = hits[0]
    rect = best_hit

    shape = page.new_shape()
    padding_x = 2
    padding_y = 1
    shape.draw_oval(fitz.Rect(rect.x0 - padding_x, rect.y0 - padding_y, rect.x1 + padding_x, rect.y1 + padding_y))
    shape.finish(color=RED, width=1.5)
    shape.commit()

def circle_multiline(page, loc_list, context_anchor, padding_x=5, padding_y=4, shift_x=0, shift_y=0):
    for loc in loc_list:
        draw_circle(page, loc, context_anchor=context_anchor)

def write_text(page, anchor_text, text, offset_x=5, offset_y=-3, align_left=False):
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
    if not hits or len(hits) <= instance: return
    rect = hits[instance]
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
    doc = fitz.open(template_path)
    page = doc[0]

    if data.get("s0_surgical_no"): write_text(page, "Surgical Number S", data["s0_surgical_no"], offset_x=90)
    if data.get("s1_side"): draw_circle(page, data["s1_side"], context_anchor="Received in formalin")
    if data.get("s2_proc") == "modified": draw_tick(page, "modified radical mastectomy")
    elif data.get("s2_proc") == "simple": draw_tick(page, "simple mastectomy")
    elif data.get("s2_proc") == "other":
        hits = page.search_for("simple mastectomy specimen")
        if hits:
            anchor = hits[0]
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
            else: draw_tick(page, "simple mastectomy", offset_x=220)
        else: draw_tick(page, "simple mastectomy", offset_x=220)
        if data.get("s2_other_text"): write_text(page, "simple mastectomy", data["s2_other_text"], offset_x=240)
        
    if data.get("s3_dims"): write_spaced_dims(page, "Measuring", data["s3_dims"], start_offset=15, gap=40)
    if data.get("s4_check"):
        draw_tick(page, "with axillary content")
        if data.get("s4_dims"): write_spaced_dims(page, "with axillary content", data["s4_dims"], start_offset=15, gap=40)
    if data.get("s5_dims"): write_spaced_dims(page, "The skin ellipse", data["s5_dims"], start_offset=20, gap=40)
    
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
            else: draw_tick(page, "appears normal", offset_x=-20)
        else: draw_tick(page, "appears normal", offset_x=-20)

    if data.get("s6_check"):
        draw_tick(page, "shows an old surgical scar")
        if data.get("s7_len"): write_text(page, "cm in length", data["s7_len"], offset_x=15, align_left=True)
        if data.get("s7_locs"): circle_multiline(page, data["s7_locs"], context_anchor="shows an old surgical scar")

    if data.get("s8_check"):
        draw_tick(page, "shows an ulceration")
        if data.get("s8_dims"): write_spaced_dims(page, "shows an ulceration", data["s8_dims"], start_offset=25, gap=55)
        if data.get("s8_locs"): circle_multiline(page, data["s8_locs"], context_anchor="shows an ulceration")
    
    if data.get("s9_val"):
        vals = data["s9_val"]
        if isinstance(vals, str): vals = [vals]
        if "everted" in vals: draw_tick(page, "is everted", offset_x=-15)
        if "inverted" in vals: draw_tick(page, "shows inverted", offset_x=-20)
        if "ulceration" in vals:
            n_hits = page.search_for("The nipple")
            target_rect = None
            if n_hits:
                row_y = n_hits[0].y0
                u_hits = page.search_for("ulceration")
                for h in u_hits:
                    if h.y0 >= row_y - 5 and h.y0 < row_y + 40:
                        target_rect = h
                        break
            if target_rect:
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
                 else: draw_tick(page, "shows ulceration", search_instance=-1)
            else: draw_tick(page, "shows ulceration", search_instance=-1)

    if data.get("s10_grammar"): draw_circle(page, data["s10_grammar"], context_anchor="There (")

    if data.get("s10_infiltrative"):
        draw_tick(page, "infiltrative")
        if data.get("s10_inf_dims"): write_spaced_dims(page, "yellow white mass", data["s10_inf_dims"], start_offset=30, gap=45)

    if data.get("s10_well"):
        draw_tick(page, "well")
        if data.get("s10_well_dims"): write_spaced_dims(page, "slit like appearance", data["s10_well_dims"], start_offset=30, gap=42)

    if data.get("s10_prev1"):
        draw_tick(page, "previous surgical cavity", search_instance=0)
        if data.get("s10_prev1_dims"): write_spaced_dims(page, "adjacent fibrous tissue", data["s10_prev1_dims"], start_offset=35, instance=0, gap=45)

    if data.get("s10_prev2"):
        draw_tick(page, "previous surgical cavity", search_instance=1)
        if data.get("s10_prev2_cavity_dims"): write_spaced_dims(page, "adjacent fibrous tissue", data["s10_prev2_cavity_dims"], start_offset=25, instance=1, gap=45, y_offset=-3)
        if data.get("s10_prev2_mass_dims"): write_spaced_dims(page, "residual mass", data["s10_prev2_mass_dims"], start_offset=30, gap=45, y_offset=-3, instance=-1)

    if data.get("s10_5_nipple"): draw_tick(page, "beneath the nipple")
    if data.get("s10_5_scar"): draw_tick(page, "beneath the scar")
    if data.get("s10_5_central"): draw_tick(page, "in the central portion")
    
    if data.get("s10_5_quadrant_check"):
        anchor_hits = page.search_for("in ( upper")
        if not anchor_hits:
             anchor_hits = [r for r in page.search_for("in (") if page.search_for("upper", clip=fitz.Rect(r.x1, r.y0-5, page.rect.width, r.y1+5))]
        
        box_rect = None
        if anchor_hits:
            anchor = anchor_hits[0]
            clip_left = fitz.Rect(0, anchor.y0 - 2, anchor.x0, anchor.y1 + 2)
            box_hits = page.search_for("☐", clip=clip_left)
            
            if box_hits: box_rect = box_hits[-1]
            else: box_rect = fitz.Rect(anchor.x0 - 18, anchor.y0, anchor.x0 - 8, anchor.y1)
        
        if box_rect:
            center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
            shape = page.new_shape()
            p1 = fitz.Point(center.x - 4, center.y - 2)
            p2 = fitz.Point(center.x, center.y + 4)
            p3 = fitz.Point(center.x + 5, center.y - 6)
            shape.draw_line(p1, p2)
            shape.draw_line(p2, p3)
            shape.finish(color=RED, width=1.5)
            shape.commit()
            
            if data.get("s10_5_quadrant_vals"):
                for q in data["s10_5_quadrant_vals"]:
                     q_pad_x = 5
                     if q in ["inner", "outer"]: q_pad_x = 4
                     circle_multiline(page, [q], context_anchor="in ( upper", padding_x=q_pad_x, padding_y=4, shift_x=0, shift_y=0)

    if data.get("s10_5_other"):
         anchor_hits = page.search_for("in (")
         if anchor_hits:
             anchor = anchor_hits[0]
             line_rect = fitz.Rect(anchor.x1, anchor.y0 - 5, page.rect.width, anchor.y1 + 5)
             q_hits = page.search_for("quadrant", clip=line_rect)
             
             if q_hits:
                 q_rect = q_hits[0]
                 right_clip = fitz.Rect(q_rect.x1, q_rect.y0 - 5, page.rect.width, q_rect.y1 + 5)
                 box_hits = page.search_for("☐", clip=right_clip)
                 
                 target_box = box_hits[0] if box_hits else fitz.Rect(q_rect.x1 + 35, q_rect.y0, q_rect.x1 + 45, q_rect.y1)
                 
                 if target_box:
                    center = fitz.Point((target_box.x0 + target_box.x1)/2, (target_box.y0 + target_box.y1)/2)
                    shape = page.new_shape()
                    shape.draw_line(fitz.Point(center.x - 4, center.y - 2), fitz.Point(center.x, center.y + 4))
                    shape.draw_line(fitz.Point(center.x, center.y + 4), fitz.Point(center.x + 5, center.y - 6))
                    shape.finish(color=RED, width=1.5)
                    shape.commit()
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
        write_text(page, "nearest resected margin", data["s11_margin_right"], align_left=True, offset_x=10)

    if data.get("s12_check"):
        draw_tick(page, "The uninvolved breast")
        hits = page.search_for("ratio of approximately")
        if hits:
            rect = hits[0]
            colon_x = rect.x1 + 30
            if data.get("s12_val_left"): page.insert_text(fitz.Point(colon_x - 15, rect.y1 - 3), str(data["s12_val_left"]), fontsize=10, fontname="helv", color=BLUE)
            if data.get("s12_val_right"): page.insert_text(fitz.Point(colon_x + 10, rect.y1 - 3), str(data["s12_val_right"]), fontsize=10, fontname="helv", color=BLUE)

    if data.get("s13_type") == "unremarkable": 
        hits = page.search_for("is unremarkable")
        if hits:
            anchor = hits[0]
            clip_left = fitz.Rect(anchor.x0 - 50, anchor.y0 - 5, anchor.x0, anchor.y1 + 5)
            box_hits = page.search_for("☐", clip=clip_left)
            if box_hits:
                box_rect = box_hits[-1]
                center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
                shape = page.new_shape()
                shape.draw_line(fitz.Point(center.x - 4, center.y - 2), fitz.Point(center.x, center.y + 4))
                shape.draw_line(fitz.Point(center.x, center.y + 4), fitz.Point(center.x + 5, center.y - 6))
                shape.finish(color=RED, width=1.5)
                shape.commit()
            else: draw_tick(page, "is unremarkable", offset_x=-20) 
    elif data.get("s13_type") == "other":
        hits = page.search_for("is unremarkable")
        if hits:
            anchor = hits[0]
            right_clip = fitz.Rect(anchor.x1, anchor.y0 - 5, page.rect.width, anchor.y1 + 5)
            box_hits = page.search_for("☐", clip=right_clip)
            if box_hits:
                box_rect = box_hits[0]
                center = fitz.Point((box_rect.x0 + box_rect.x1)/2, (box_rect.y0 + box_rect.y1)/2)
                shape = page.new_shape()
                shape.draw_line(fitz.Point(center.x - 4, center.y - 2), fitz.Point(center.x, center.y + 4))
                shape.draw_line(fitz.Point(center.x, center.y + 4), fitz.Point(center.x + 5, center.y - 6))
                shape.finish(color=RED, width=1.5)
                shape.commit()
            else: draw_tick(page, "is unremarkable", offset_x=100)
        
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
                    page.insert_text(fitz.Point(rect.x1 + 40, rect.y1 - 3), f", {item['extra']}", fontsize=10, fontname="helv", color=BLUE)
        else: write_text(page, anchor, item, align_left=True, offset_x=10)

    if data.get("footer_prosecutor"): write_text(page, "Prosecutor", data["footer_prosecutor"], offset_x=-170)
        
    if data.get("footer_date"): write_text(page, "Date", data["footer_date"], offset_x=20)
    else: write_text(page, "Date", datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), offset_x=20)

    doc.save(output_path)
    doc.close()


# =========================================================
# --- Routes For Auth & History ---
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        
        user_exists = User.query.filter_by(username=username).first()
        email_exists = User.query.filter_by(email=email).first()
        
        if user_exists:
            flash("Username already exists.", "danger")
        elif email_exists:
            flash("Email already exists.", "danger")
        else:
            new_user = User(username=username, email=email, name=name)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for('login'))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_or_email = request.form.get("username")
        password = request.form.get("password")
        
        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password.", "danger")
            
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        if user:
            print(f"Password reset link generated for {email}")
            flash('A password reset link has been sent to your email address (simulated).', 'info')
            return redirect(url_for('login'))
        else:
            flash('Email address not found.', 'danger')
            
    return render_template("forgot_password.html")

@app.route("/history")
@login_required
def history():
    user_histories = FormHistory.query.filter_by(user_id=current_user.id).order_by(FormHistory.timestamp.desc()).all()
    return render_template("history.html", histories=user_histories)

@app.route("/history/load/<int:history_id>")
@login_required
def load_history(history_id):
    history_record = FormHistory.query.get_or_404(history_id)
    
    if history_record.user_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('history'))
        
    try:
        data = json.loads(history_record.form_data)
    except Exception as e:
        print(f"Error loading JSON data: {e}")
        flash("Error loading form data.", "danger")
        return redirect(url_for('history'))
        
    flags = generate_confidence_flags(data) # Calculate yellow flags for loaded history
    flash("History loaded successfully.", "success")
    return render_template("index.html", data=data, flags=flags, transcription="[Loaded from History]")


# =========================================================
# --- Main Application Routes ---
# =========================================================

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        transcription = None
        
        if request.form.get('transcription_text'):
            transcription = request.form.get('transcription_text')
            print(f"Received Direct Transcription: {transcription}")

        audio_file = request.files.get('audio_file')
        if audio_file and audio_file.filename != '':
            from werkzeug.utils import secure_filename
            filename = secure_filename(audio_file.filename)
            audio_path = UPLOAD_DIR / filename 
            audio_file.save(audio_path)
            print(f"Audio saved to {audio_path}")

            try:
                import threading
                if not hasattr(app, "model_lock"):
                     app.model_lock = threading.Lock()
                     
                # พจนานุกรมคำศัพท์สำหรับการใบ้คำให้ Whisper ช่วยลด WER ได้ 0-5%
                pathology_prompt = (
                    "Received in formalin. Modified radical mastectomy specimen. "
                    "Simple mastectomy. Skin ellipse. The nipple is everted, inverted, shows ulceration. "
                    "Infiltrative firm yellow-white mass. Well-defined firm white mass with slit-like appearance. "
                    "Previous surgical cavity with adjacent fibrous tissue. Residual mass. "
                    "Beneath the nipple, beneath the scar, subareola. "
                    "Upper inner quadrant, lower outer quadrant. "
                    "Deep margin, superior margin, inferior margin, medial margin, lateral margin. "
                    "Uninvolved breast parenchyma. Lymph nodes ranging from. "
                    "Representative sections are submitted as. Nipple, mass, old biopsy cavity."
                )

                with app.model_lock:
                    transcription_result = model.transcribe(
                        str(audio_path), 
                        language="en", 
                        initial_prompt=pathology_prompt
                    ) 
                transcription = transcription_result['text']
                transcription = normalize_text(transcription) 
                print(f"Transcription from Audio: {transcription}")
            except Exception as e:
                print(f"Error during transcription: {e}")
                transcription = "Error during transcription"

        data = {}
        flags = {}
        if transcription:
             data = extract_data_15_sections(transcription)
             flags = generate_confidence_flags(data) 
        
        return render_template('index.html', transcription=transcription, data=data, flags=flags)

    return render_template("index.html")

@app.route("/generate", methods=["GET", "POST"])
def generate_pdf():
    if request.method == "GET":
        return redirect(url_for("index"))

    form_data = request.form
    data = {}
    
    for field in ["s0_surgical_no", "s1_side", "s2_proc", "s2_other_text", "s7_len", 
                  "s9_ulcer_text", "s10_grammar", "s10_5_other",
                  "s11_deep", "s11_superior", "s11_inferior", "s11_medial", "s11_lateral", "s11_skin", "s11_margin_right",
                  "s12_val_left", "s12_val_right", "s13_type", "s13_text", "s14_min", "s14_max",
                  "footer_prosecutor", "footer_date"]:
        if form_data.get(field):
            data[field] = form_data.get(field)

    for key in ["s7_locs", "s8_locs", "s10_5_quadrant_vals", "s9_val"]:
        vals = request.form.getlist(key)
        if vals: data[key] = vals

    for dim_key in ["s3_dims", "s4_dims", "s5_dims", "s8_dims", 
                    "s10_inf_dims", "s10_well_dims", "s10_prev1_dims", 
                    "s10_prev2_cavity_dims", "s10_prev2_mass_dims"]:
        dims = []
        d0 = form_data.get(f"{dim_key}_0")
        d1 = form_data.get(f"{dim_key}_1")
        d2 = form_data.get(f"{dim_key}_2")
        
        if d0: dims.append(d0)
        if d1: dims.append(d1)
        if d2: dims.append(d2)
        
        if dims: data[dim_key] = dims

    for chk in ["s4_check", "s5_appears_normal", "s6_check", "s7_check", "s8_check", 
                "s10_infiltrative", "s10_well", "s10_prev1", "s10_prev2",
                "s10_5_nipple", "s10_5_scar", "s10_5_central",
                "s12_check", "s14_check"]:
        if form_data.get(chk):
            data[chk] = True
            
    for key in ["s7_locs", "s8_locs", "s10_5_quadrant_vals"]:
        vals = request.form.getlist(key)
        if vals: data[key] = vals

    if data.get("s10_5_quadrant_vals"):
        data["s10_5_quadrant_check"] = True

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
            extra = ""
            if "nearest" in anchor or "deep" in anchor:
                safe_key_extra = form_name.replace("sec_", "sec_extra_")
                extra = form_data.get(safe_key_extra, "")
            data["sections"][anchor] = {"code": code, "extra": extra}

    import time
    uid = uuid.uuid4().hex
    timestamp = int(time.time())
    pdf_filename = f"final_{uid}_{timestamp}.pdf"
    docx_filename = f"final_{uid}_{timestamp}.docx"
    
    pdf_path = OUTPUT_DIR / pdf_filename
    docx_path = OUTPUT_DIR / docx_filename
    
    if not PDF_TEMPLATE_PATH.exists():
        return f"Error: Template not found at {PDF_TEMPLATE_PATH}"
        
    process_pdf_15_sections(PDF_TEMPLATE_PATH, pdf_path, data)
    
    try:
        convert_to_docx(str(pdf_path), str(docx_path))
    except Exception as e:
        print(f"Error converting to DOCX: {e}")
        docx_filename = None 
        
    flags = generate_confidence_flags(data)
    
    # --- บันทึกลง Database หากมีการล็อกอิน ---
    if current_user.is_authenticated:
        s_no = data.get("s0_surgical_no", "Unknown")
        history_record = FormHistory(
            user_id=current_user.id,
            surgical_number=s_no,
            form_data=json.dumps(data)
        )
        db.session.add(history_record)
        db.session.commit()
    
    return render_template("index.html", 
                           pdf_filename=pdf_filename, 
                           docx_filename=docx_filename,
                           transcription=form_data.get("transcription"),
                           data=data, flags=flags)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7861)