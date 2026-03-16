
import json
import math

LAYOUT_PATH = "d:/app_pathology/layout_dump.json"
OUTPUT_CSS = "d:/app_pathology/generated_styles.css"

def get_bbox(data, text_snippet):
    """Finds the bbox of the first occurrence of text containing snippet."""
    for item in data:
        if text_snippet in item["text"]:
            return item["bbox"]
    return None

def get_checkbox_near(data, anchor_text, offset_x_range=(-30, 0), offset_y_range=(-5, 5)):
    """Finds a checkbox glyph near the anchor text."""
    anchor_bbox = get_bbox(data, anchor_text)
    if not anchor_bbox:
        return None
    
    # Anchor center
    ay = (anchor_bbox[1] + anchor_bbox[3]) / 2
    ax = anchor_bbox[0] # Left side of anchor text
    
    best_candidate = None
    min_dist = 9999
    
    for item in data:
        if "☐" in item["text"]:
            # Check center y alignment
            cy = (item["bbox"][1] + item["bbox"][3]) / 2
            cx = item["bbox"][0]
            
            dy = cy - ay
            dx = cx - ax
            
            if offset_y_range[0] <= dy <= offset_y_range[1]:
                 # Check horizontal proximity
                 # Usually checkbox is to the left
                 if offset_x_range[0] <= dx <= offset_x_range[1]:
                     dist = abs(dx) + abs(dy)
                     if dist < min_dist:
                         min_dist = dist
                         best_candidate = item["bbox"]
                         
    return best_candidate

def generate_css():
    with open(LAYOUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    styles = []
    
    def add_style(cls, bbox, type="text", width=None, adjust_x=0, adjust_y=0, absolute_override=None):
        if absolute_override:
            # Absolute override is [x0, y0, x1, y1] in PDF points
            x_pt = absolute_override[0]
            y_pt = absolute_override[1]
            w_pt = absolute_override[2] - absolute_override[0]
            h_pt = absolute_override[3] - absolute_override[1]
            
            # Scale to CSS pixels (2.0x)
            left = x_pt * 2.0
            top = y_pt * 2.0
            w_px = w_pt * 2.0
            h_px = h_pt * 2.0
            
            # BOX-SIZING FIX
            # Use border-box to contain the border within the defined width/height.
            # Border is 2px. We want 1px gap (whitespace) inside the border.
            # Total Extra Width = 2*(Border+Gap) = 2*(2+1) = 6px.
            # Total Extra Height = 2*(Border) = 4px.
            
            w_final = w_px + 6.0
            h_final = h_px + 4.0
            
            left_final = left - 3.0  # Shift left by half the extra width
            top_final = top - 2.0    # Shift top by half the extra height
            
            css = f".{cls} {{ position: absolute; box-sizing: border-box; left: {left_final:.1f}px; top: {top_final:.1f}px; width: {w_final:.1f}px; height: {h_final:.1f}px; }}"
            styles.append(css)
            return

        if not bbox:
            print(f"Warning: No bbox for {cls}")
            return
            
        # bbox is [x0, y0, x1, y1] in PDF points
        x_pt = bbox[0] + adjust_x
        y_pt = bbox[1] + adjust_y
        
        # Scale to CSS pixels (2.0x)
        # Apply similar logic for legacy items?
        # User complained about "Circles", which use absolute_override mainly.
        # But 'word_circle' type legacy items (like grammar) also need this.
        
        left = x_pt * 2.0 - 15.0 # Keep legacy shift for now
        top = y_pt * 2.0
        
        # Add box-sizing here too for consistency?
        # If I add box-sizing, the existing width overrides might shrink.
        # Let's add it only if type="word_circle" or override.
        # Actually safer to apply box-sizing: border-box generally if we want predictable sizes.
        # But for 'lines' (width=220), border is 1px.
        # Let's stick to fixing the Circles for now.
        
        css = f".{cls} {{ left: {left:.1f}px; top: {top:.1f}px;"
        
        if width:
            css += f" width: {width}px;"
        elif type == "word_circle":
             # Width is explicit or calculated from bbox
             if bbox and len(bbox) >= 4:
                 w_pt = bbox[2] - bbox[0]
                 w_px = w_pt * 2.0
                 # For legacy word_circle, also apply padding?
                 # Let's add generic padding
                 css += f" width: {w_px + 6.0:.1f}px; height: {(bbox[3]-bbox[1])*2.0 + 4.0:.1f}px; box-sizing: border-box;"
             if width: css += f" width: {width}px;"
             
        css += " }"
        styles.append(css)

    def get_dims_after_x(data, anchor_text):
        """Finds dimension inputs after 'anchor_text' by looking for 'x' markers."""
        anchor = get_bbox(data, anchor_text)
        if not anchor: return None
        
        # Look for 'x' that are below the anchor but on the same line (roughly)
        # Actually anchor might be the text BEFORE the dims.
        y_anchor = anchor[1]
        
        # Collect Xs on this line
        xs = []
        for item in data:
            if item["text"].strip() == "x" and abs(item["bbox"][1] - y_anchor) < 10:
                if item["bbox"][0] > anchor[2]: # Must be to the right
                    xs.append(item["bbox"])
        
        # Sort by x coordinate
        xs.sort(key=lambda b: b[0])
        
        dims = []
        if len(xs) >= 2:
            # Dim 0: Before 1st X.
            # Start from anchor end? or just some fixed width before 1st X.
            # Let's say it ends at x[0].left.
            x0 = xs[0]
            x1 = xs[1]
            
            # Dim 0
            # End is x0[0]. Start is x0[0] - 40?
            dims.append([x0[0]-45, x0[1], x0[0]-5, x0[3]])
            
            # Dim 1
            # Start is x0[2], End is x1[0]
            # Center it?
            left = x0[2] + 5
            dims.append([left, x0[1], left + 40, x0[3]])
            
            # Dim 2
            # Start is x1[2]
            left = x1[2] + 5
            dims.append([left, x0[1], left + 40, x0[3]])
            
        return dims

    # 1. Surgical Number
    # Text "Surgical Number S.........." bbox is [355, 42, 578, 53]
    # We want input to cover the dots. 
    # "Surgical Number S" is approx 100pt wide.
    s1_bbox = get_bbox(data, "Surgical Number")
    if s1_bbox:
        add_style("s1-surgical", s1_bbox, adjust_x=90, adjust_y=-2, width=220) # 220px width

    # 1.5 Side (Right / Left)
    # Anchor "( right / left )"
    # Using absolute override from extraction
    rl_box = get_bbox(data, "( right / left )")
    # if rl_box: ... we keep rl_box lookup just for get_bbox side effect if needed? No.
    # Just override.
    
    # right: 160.77, 90.75, 181.79, 100.57
    add_style("s1-right", None, absolute_override=[160.77, 90.75, 181.79, 100.57])
    # left: 188.75, 90.75, 202.82, 100.57
    add_style("s1-left", None, absolute_override=[188.75, 90.75, 202.82, 100.57])

    # 2. Procedure
    mod_box = get_checkbox_near(data, "modified radical")
    add_style("s3-check", mod_box, type="check", adjust_x=1, adjust_y=1)
    
    simp_box = get_checkbox_near(data, "simple mastectomy")
    add_style("s3-simple", simp_box, type="check", adjust_x=1, adjust_y=1)
    
    # 3. Measuring
    meas_bbox = get_bbox(data, "Measuring")
    if meas_bbox:
        # After "Measuring"
        # Dim 0
        add_style("s3-dim-0", meas_bbox, adjust_x=55, adjust_y=-2, width=45)
        # Dim 1
        add_style("s3-dim-1", meas_bbox, adjust_x=100, adjust_y=-2, width=45)
        # Dim 2
        add_style("s3-dim-2", meas_bbox, adjust_x=145, adjust_y=-2, width=45)
        
    # 4. Axillary
    ax_box = get_checkbox_near(data, "with axillary content")
    add_style("s4-check", ax_box, type="check", adjust_x=1, adjust_y=1)
    
    ax_text_bbox = get_bbox(data, "with axillary content")
    if ax_text_bbox:
        # After text, dims start
        # Text width approx 85pt?
        w_text = 90 
        add_style("s4-dim-0", ax_text_bbox, adjust_x=w_text+5, adjust_y=-2, width=45)
        add_style("s4-dim-1", ax_text_bbox, adjust_x=w_text+50, adjust_y=-2, width=45)
        add_style("s4-dim-2", ax_text_bbox, adjust_x=w_text+95, adjust_y=-2, width=45)

    # 5. Skin Ellipse
    skin_bbox = get_bbox(data, "The skin ellipse")
    if skin_bbox:
        # "The skin ellipse ," width ~ 70pt
        add_style("s5-dim-0", skin_bbox, adjust_x=75, adjust_y=-2, width=45)
        add_style("s5-dim-1", skin_bbox, adjust_x=135, adjust_y=-2, width=45)
    
    app_norm_box = get_checkbox_near(data, "appears normal")
    add_style("s5-check", app_norm_box, type="check", adjust_x=1, adjust_y=1)
    
    # NEW: "appears normal ..................."
    app_norm_text = get_bbox(data, "appears normal")
    if app_norm_text:
         # Text ends at ~320. Input starts ~325.
         # Force Y adjustment if needed.
         # appears normal text is usually at Y~150.
         # CSS generator multiplies Y by scale (approx 2.08?). 150*2 = 300.
         # Current: 296.8.
         # Let's trust get_bbox but ensure width is nice.
         add_style("s5-appears-input", [app_norm_text[2]+5, app_norm_text[1], 0, 0], adjust_y=-4, width=300)
    
    # 6. Scars
    old_scar_box = get_checkbox_near(data, "shows an old surgical scar")
    add_style("s6-check", old_scar_box, type="check", adjust_x=1, adjust_y=1)
    
    scar_text_bbox = get_bbox(data, "shows an old surgical scar")
    if scar_text_bbox:
        # "shows an old surgical scar ........."
        # Input over dots.
        # "shows an old surgical scar " width ~ 110pt
        add_style("s6-len", scar_text_bbox, adjust_x=115, adjust_y=-2, width=50)

    # Locations (Scar)
    # text: "at ( areola / upper / lower / inner / outer ) ( quadrant )"
    # New Exact Coords (Y~171.51)
    
    # areola: 272.17, 171.51, 297.19, 181.57
    add_style("s6-loc-areola", None, absolute_override=[272.17, 171.51, 297.19, 181.57])
    # upper: 304.65, 171.51, 327.66, 181.57
    add_style("s6-loc-upper", None, absolute_override=[304.65, 171.51, 327.66, 181.57])
    # lower: 335.19, 171.51, 356.66, 181.57
    add_style("s6-loc-lower", None, absolute_override=[335.19, 171.51, 356.66, 181.57])
    # inner: 364.11, 171.51, 384.23, 181.57
    add_style("s6-loc-inner", None, absolute_override=[364.11, 171.51, 384.23, 181.57])
    # outer: 391.65, 171.51, 412.05, 181.57
    add_style("s6-loc-outer", None, absolute_override=[391.65, 171.51, 412.05, 181.57])

    # Ulceration
    ulc_box = get_checkbox_near(data, "shows an ulceration")
    add_style("s6-ulc-check", ulc_box, type="check", adjust_x=1, adjust_y=1)
    
    ulc_text = get_bbox(data, "shows an ulceration")
    if ulc_text:
        # "shows an ulceration ...... x ......"
        add_style("s6-ulc-dim-0", ulc_text, adjust_x=95, adjust_y=-2, width=40)
        add_style("s6-ulc-dim-1", ulc_text, adjust_x=140, adjust_y=-2, width=40)
        
        # Ulceration Locations
        # New Exact Coords (Y~192.75)
        
        # areola: 265.35, 192.75, 290.26, 202.81
        add_style("s8-loc-areola", None, absolute_override=[265.35, 192.75, 290.26, 202.81])
        # upper: 297.82, 192.75, 320.85, 202.81
        add_style("s8-loc-upper", None, absolute_override=[297.82, 192.75, 320.85, 202.81])
        # lower: 328.28, 192.75, 349.84, 202.81
        add_style("s8-loc-lower", None, absolute_override=[328.28, 192.75, 349.84, 202.81])
        # inner: 357.28, 192.75, 377.31, 202.81
        add_style("s8-loc-inner", None, absolute_override=[357.28, 192.75, 377.31, 202.81])
        # outer: 384.75, 192.75, 405.36, 202.81
        add_style("s8-loc-outer", None, absolute_override=[384.75, 192.75, 405.36, 202.81])

    # Nipple
    # User says "Still not ticked". This implies they want the CHECKBOX ticked.
    # Earlier instruction was "Circle word", but visual evidence suggests Box.
    # Reverting to CHECKBOX style for Nipple.
    ev_box = get_checkbox_near(data, "is everted")
    add_style("s9-everted", ev_box, type="check", adjust_x=1, adjust_y=1)
    
    inv_box = get_checkbox_near(data, "shows inverted")
    add_style("s9-inverted", inv_box, type="check", adjust_x=1, adjust_y=1)
    
    ulc_nip_box = get_checkbox_near(data, "shows ulceration")
    if not ulc_nip_box:
         # Try finding text "shows ulceration" and look left
         ulc_nip_text = get_bbox(data, "shows ulceration")
         if ulc_nip_text and ulc_nip_text[1] > 200: # Ensure it's nipple section (lower down)
              # Box is ~20pt left
               add_style("s9-ulc", [ulc_nip_text[0]-20, ulc_nip_text[1], 0, 0], type="check", adjust_x=1, adjust_y=1)
    else:
         add_style("s9-ulc", ulc_nip_box, type="check", adjust_x=1, adjust_y=1)

    # Nipple Ulceration Text (New)
    # Find "shows ulceration" specifically in the nipple area (Y > 200)
    for item in data:
        if "shows ulceration" in item["text"] and item["bbox"][1] > 200:
             # Text "shows ulceration" starts at bbox[0].
             # The bbox includes dots "......".
             # We want input to start after "shows ulceration".
             # Est width of "shows ulceration" ~ 90px.
             # Box starts ~252. So input should start ~342-345.
             # bbox[0] is 252.4. + 95 = 347.4.
             add_style("s9-ulc-text", [item["bbox"][0]+95, item["bbox"][1], 0, 0], adjust_y=-2, width=300)
             break

    # Mass 1 (Infiltrative)
    # Use new logic
    dims_inf = get_dims_after_x(data, "infiltrative")
    if dims_inf:
        add_style("s10-inf-dim-0", dims_inf[0], adjust_y=-2)
        add_style("s10-inf-dim-1", dims_inf[1], adjust_y=-2)
        add_style("s10-inf-dim-2", dims_inf[2], adjust_y=-2)
    else:
        # Fallback
        inf_box = get_checkbox_near(data, "infiltrative")
        if inf_box:
           y_inf = inf_box[1] 
           add_style("s10-inf-dim-0", [300, y_inf, 0, 0], adjust_y=-2, width=40)
           add_style("s10-inf-dim-1", [340, y_inf, 0, 0], adjust_y=-2, width=40)
           add_style("s10-inf-dim-2", [380, y_inf, 0, 0], adjust_y=-2, width=40)
    
    inf_check_box = get_checkbox_near(data, "infiltrative")
    add_style("s10-inf-check", inf_check_box, type="check", adjust_x=1, adjust_y=1)

    # Mass 2 (Well defined)
    dims_wd = get_dims_after_x(data, "well – defined")
    if not dims_wd: dims_wd = get_dims_after_x(data, "well - defined")
    
    if dims_wd:
        add_style("s10-well-dim-0", dims_wd[0], adjust_y=-2)
        add_style("s10-well-dim-1", dims_wd[1], adjust_y=-2)
        add_style("s10-well-dim-2", dims_wd[2], adjust_y=-2)
        
    def_box = get_checkbox_near(data, "well")
    if not def_box: def_box = get_checkbox_near(data, "well – defined")
    add_style("s10-well-check", def_box, type="check", adjust_x=1, adjust_y=1)

    # Prev 1
    # text "previous  surgical  cavity  with  adjacent  fibrous  tissue , ............. x ............. x ............. cm."
    # The first one might NOT have dimensions in some templates, but user says it does.
    # User Request: "previous surgical cavity with adjacent fibrous tissue , ............. x ............. x ............. cm."
    
    # Let's try to find 'x's for this line too.
    # Prev 1 anchor is "previous surgical cavity" (First hit)
    p1_text = get_bbox(data, "previous  surgical  cavity") 
    # Use exact string match from PDF text extraction if possible?
    
    dims_p1 = get_dims_after_x(data, "previous  surgical  cavity")
    if dims_p1:
        add_style("s10-prev1-dim-0", dims_p1[0], adjust_y=-2)
    # Prev 1
    # Hardcoded robust placement based on Y~295 -> 291 (Up a bit)
    # Text starts at X=78.50. Dims are at the end.
    # User says "Right a tiny bit", "Move up".
    # Previous 320 -> 340.
    y_p1 = 291.0
    add_style("s10-prev1-dim-0", [340, y_p1, 0, 0], adjust_y=-2, width=40)
    add_style("s10-prev1-dim-1", [390, y_p1, 0, 0], adjust_y=-2, width=40)
    add_style("s10-prev1-dim-2", [440, y_p1, 0, 0], adjust_y=-2, width=40)

    p1_box = get_checkbox_near(data, "previous  surgical  cavity")
    add_style("s10-prev1-check", p1_box, type="check", adjust_x=1, adjust_y=1)

    # Prev 2 (Cavity again)
    # Hardcoded robust placement based on Y~315 -> 311
    y_p2 = 311.0
    add_style("s10-prev2-check", [78, y_p2, 90, y_p2+10], type="check", adjust_x=1, adjust_y=1)
    
    # Prev 2 Dims (Same X as Prev 1)
    # Move Right to 340
    add_style("s10-prev2-c-dim-0", [340, y_p2, 0, 0], adjust_y=-2, width=40)
    add_style("s10-prev2-c-dim-1", [390, y_p2, 0, 0], adjust_y=-2, width=40)
    add_style("s10-prev2-c-dim-2", [440, y_p2, 0, 0], adjust_y=-2, width=40)  
            
    # Residual Mass
    # User says "Left 2 bits".
    # Y 329.
    # Previous 220 -> 190.
    y_res = 329.0 
    
    # Left more: 220 -> 190
    add_style("s10-prev2-mass_dims_0", [190, y_res, 0, 0], adjust_y=-2, width=40)
    add_style("s10-prev2-mass_dims_1", [240, y_res, 0, 0], adjust_y=-2, width=40)
    add_style("s10-prev2-mass_dims_2", [290, y_res, 0, 0], adjust_y=-2, width=40)

    # 10.5 Location

    
    # 10.5 Location
    bn_box = get_checkbox_near(data, "beneath the nipple")
    add_style("s10-5-nipple", bn_box, type="check", adjust_x=1, adjust_y=1)
    
    bs_box = get_checkbox_near(data, "beneath the scar")
    add_style("s10-5-scar", bs_box, type="check", adjust_x=1, adjust_y=1)
    
    cen_box = get_checkbox_near(data, "in the central portion")
    add_style("s10-5-central", cen_box, type="check", adjust_x=1, adjust_y=1)
    
    # Quadrants
    # "in ( upper / lower / inner / outer ) quadrant ."
    # 1. The Checkbox
    quad_main_box = get_checkbox_near(data, "in ( upper")
    if quad_main_box:
         add_style("s10-5-quad-check", quad_main_box, type="check", adjust_x=1, adjust_y=1)

    # Empty Checkbox Line below (Y~388 overlap s10-5 circles, but to the right?)
    # Debug says Block 21 (Y=376) has "☐ ............................."
    # It's ON THE SAME LINE, to the right.
    # "in ( upper / ... ) quadrant .   ☐ ..................................."
    # Quadrant circle ends X~412. "quadrant ." ends X~450 (est).
    # Empty Checkbox Line below (Y~388 overlap s10-5 circles, but to the right?)
    # Quadrant circle ends X~412. "quadrant ." ends X~450 (est).
    # Screenshot shows 305 is too far LEFT. Needs to move RIGHT ~8-10px.
    # Also looks slightly HIGH.
    # Try X=313, Y=381.
    y_q = 381.0
    add_style("s10-5-other-check", [313, y_q, 325, y_q+10], type="check", adjust_x=1, adjust_y=1)
    # Text input after checkbox
    add_style("s10-5-other-text", [333, y_q, 0, 0], adjust_y=-2, width=300)

    # 2. The Words (Circle) - s10.5
    # "in ( upper / lower / inner / outer )"
    # New Exact Coords (Y~378.54)
    
    add_style("s10-5-upper", None, absolute_override=[136.31 - 1.0, 378.54, 159.34 - 1.0, 388.60])
    add_style("s10-5-lower", None, absolute_override=[166.77 - 1.0, 378.54, 188.34 - 1.0, 388.60])
    add_style("s10-5-inner", None, absolute_override=[195.77 - 1.0, 378.54, 215.79 - 1.0, 388.60])
    add_style("s10-5-outer", None, absolute_override=[223.23 - 1.0, 378.54, 243.84 - 1.0, 388.60])
    
    # Needs to clear the 'old' search logic
    quad_line_box = None # Bypass old logic check below if any
    
    if quad_line_box: 
         pass # Old logic disabled
        
        # Other ...
        # dots_q = None
        # for item in data:
        #     if "\u2026" in item["text"] and abs(item["bbox"][1] - y_q) < 5:
        #          if item["bbox"][0] > x_start + 140:
        #              dots_q = item["bbox"]
        #              break
        # if dots_q:
        #      add_style("s10-5-other", dots_q, adjust_y=-2, width=300)


    # Margins
    # Deep (66, 416)
    box_deep = get_bbox(data, "cm. from deep margin")
    if box_deep:
        # Input to LEFT. text starts at 66.
        # ".................................... cm. from deep margin"
        # The dots are LIKELY part of the text OR separate?
        # Line 1511: text ".................................... cm. from deep margin ,"
        # So bbox starts at 66.
        # We need to place input OVER the dots.
        # Dots take up first ~ 100pt?
        # Width of "...................................."
        add_style("s11-deep", box_deep, adjust_x=5, adjust_y=-2, width=150)

    # Superior (311, 418)
    box_sup = get_bbox(data, "cm. from superior margin")
    if box_sup:
         add_style("s11-superior", box_sup, adjust_x=5, adjust_y=-2, width=150)
        
    # Inferior (66, 437)
    box_inf = get_bbox(data, "cm. from inferior margin")
    if box_inf:
        add_style("s11-inferior", box_inf, adjust_x=5, adjust_y=-2, width=150)

    # Medial (311, 437)
    box_med = get_bbox(data, "cm. from medial margin")
    if box_med:
        add_style("s11-medial", box_med, adjust_x=5, adjust_y=-2, width=150)

    # Lateral (66, 455)
    box_lat = get_bbox(data, "cm. from lateral margin")
    if box_lat:
        add_style("s11-lateral", box_lat, adjust_x=5, adjust_y=-2, width=150)

    # Skin (311, 455)
    box_skin = get_bbox(data, "cm. from skin") # text "and .................................... cm. from skin ."
    if box_skin:
        # "and " is at start.
        # "and " ~ 20pt.
        add_style("s11-skin", box_skin, adjust_x=25, adjust_y=-2, width=150)
    # Grammar (is a / is an / are two / are multiple)
    gram_box = get_bbox(data, "( is a /")
    
    # is a: 74.02, 232.23, 91.24, 242.05
    add_style("s10-gram-0", None, absolute_override=[74.02, 232.23, 91.24, 242.05])
    # is an: 98.46, 232.23, 123.01, 242.05
    add_style("s10-gram-1", None, absolute_override=[98.46, 232.23, 123.01, 242.05])
    # are two: 131.23, 232.23, 165.73, 242.05
    add_style("s10-gram-2", None, absolute_override=[131.23, 232.23, 165.73, 242.05])
    # are multiple: 172.95, 232.23, 227.18, 242.05
    add_style("s10-gram-3", None, absolute_override=[172.95, 232.23, 227.18, 242.05])
    
    # Grammar Text (The dots after)
    gram_dots = get_bbox(data, "\u2026\u2026\u2026\u2026\u2026\u2026") 
    if not gram_dots or gram_dots[1] < 200:
         if gram_box:
             y_target = gram_box[1]
             for item in data:
                 if "\u2026" in item["text"] and abs(item["bbox"][1] - y_target) < 10:
                     gram_dots = item["bbox"]
                     break
    if gram_dots:
        add_style("s10-gram-text", gram_dots, adjust_y=-2, width=300)

    # ... Procedure Other... (unchanged)
    # Procedure - Other
    simp_box = get_checkbox_near(data, "simple mastectomy")
    if simp_box:
        y_simp = simp_box[1]
        other_proc_box = None
        for item in data:
            if "☐" in item["text"]:
                bx = item["bbox"]
                if abs(bx[1] - y_simp) < 10 and bx[0] > (simp_box[0] + 100):
                    other_proc_box = bx
                    break
        if other_proc_box:
            add_style("s3-other-check", other_proc_box, type="check", adjust_x=1, adjust_y=1)
            add_style("s3-other-text", other_proc_box, adjust_x=25, adjust_y=-2, width=300)

    # Footer
    box_prosec = get_bbox(data, "Prosecutor")
    if box_prosec:
        # Text is ".....................Prosecutor"
        # bbox[0] is start of dots. We want input there.
        # old was -150 (too far left).
        add_style("footer-prosecutor", box_prosec, adjust_x=5, adjust_y=-2, width=260)

    box_date = get_bbox(data, "Date")
    if box_date:
        add_style("footer-date", box_date, adjust_x=30, adjust_y=-2, width=120)

    # Uninvolved Parenchyma
    uninv_box = get_bbox(data, "The uninvolved breast parenchyma")
    if uninv_box:
        uninv_check = get_checkbox_near(data, "The uninvolved breast parenchyma")
        add_style("s12-check", uninv_check, type="check", adjust_x=1, adjust_y=1)
        # Shift slightly left from 365/405 -> Try 355/395
        add_style("s12-val-left", uninv_box, adjust_x=355, adjust_y=-2, width=30)
        add_style("s12-val-right", uninv_box, adjust_x=395, adjust_y=-2, width=30)

    # Remaining Tissue
    rem_box = get_checkbox_near(data, "is unremarkable")
    add_style("s13-unremarkable", rem_box, type="check", adjust_x=1, adjust_y=1)
    
    if rem_box:
        add_style("s13-other-check", [rem_box[0] + 88, rem_box[1], 0, 0], type="check", adjust_y=0)
        add_style("s13-other-text", [rem_box[0] + 100, rem_box[1], 0, 0], adjust_y=-4, width=280)

    # Lymph Nodes
    # "There are multiple lymph nodes ranging from ...... cm . to ...... cm ."
    ln_check = get_checkbox_near(data, "There are multiple lymph nodes")
    add_style("s14-check", ln_check, type="check", adjust_x=1, adjust_y=1)
    
    ln_text = get_bbox(data, "There are multiple lymph nodes")
    if ln_text:
        # Bbox is full line
        # Start of dots 1: After "ranging from "
        # "There are multiple lymph nodes ranging from " ~ 45 chars ~ 200pt+?
        # Let's use get_dims_after_x? No, no X here.
        # Just use offsets from LN text start.
        # "There are multiple lymph nodes ranging from " ~ 240pt. (Text starts at 50, first dots at ~290?)
        # Let's try finding the dots again...
        # But dots are "...................................."
        # Line 1303: "text": "There are multiple lymph nodes ranging from .................................... cm . to .................................... cm . in diameter."
        # This one is HARDER because it's a single text block.
        # Estimate:
        # "There are multiple lymph nodes ranging from " width ~ 220pt
        # Dots 1 width ~ 100pt
        # " cm . to " ~ 40pt
        # Dots 2 width ~ 100pt
        
        start_x = ln_text[0]
        dot1_x = start_x + 220 
        add_style("s14-min", [dot1_x, ln_text[1], 0, 0], adjust_y=-2, width=100)
        
        dot2_x = dot1_x + 100 + 40
        add_style("s14-max", [dot2_x, ln_text[1], 0, 0], adjust_y=-2, width=100)

    # Representative Sections
    # Anchors:
    # "= nipple"
    # "= mass"
    # "= old biopsy cavity with fibrosis"
    # etc.
    
    def add_rep_sec(name, anchor_text):
         box = get_bbox(data, anchor_text)
         if box:
             # Input to the left of the text
             # Text starts at box[0]
             # box[0] is the start of dots.
             # Width? "~ 140pt?"
             add_style(name, box, adjust_x=0, adjust_y=-2, width=140)



    add_rep_sec("sec-nipple", "= nipple")
    add_rep_sec("sec-mass", "= mass")
    add_rep_sec("sec-cavity", "= old biopsy cavity with fibrosis")
    add_rep_sec("sec-deep", "= deep resected margin")
    add_rep_sec("sec-nearest", "= nearest resected margin")
    add_rep_sec("sec-ui", "= sampling upper inner quadrant")
    add_rep_sec("sec-uo", "= sampling upper outer quadrant")
    add_rep_sec("sec-li", "= sampling lower inner quadrant")
    add_rep_sec("sec-lo", "= sampling lower outer quadrant")
    add_rep_sec("sec-central", "= sampling central region")
    add_rep_sec("sec-axillary", "= axillary lymph nodes")
    
    # NEW: Nearest Resected Margin RIGHT side
    # Y~600.
    # Text "nearest resected margin ," ends at 240.
    # Input starts at 250.
    # Move UP a bit: 600.5 -> 595.0
    y_nrm = 595.0
    add_style("s11-margin-right", [250, y_nrm, 0, 0], adjust_y=-2, width=300)

    import os
    output_css_path = os.path.join(os.path.dirname(__file__), "static", "generated_styles.css")
    with open(output_css_path, "w", encoding="utf-8") as f:
        f.write("\n".join(styles))
        print(f"Generated {len(styles)} styles to {output_css_path}")

if __name__ == "__main__":
    generate_css()
