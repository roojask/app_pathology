
import fitz
from pathlib import Path

BASE_DIR = Path("d:/app_pathology")
ASSETS_DIR = BASE_DIR / "assets"
PDF_PATH = ASSETS_DIR / "Breast_Gross_Template.pdf"
IMG_PATH = ASSETS_DIR / "template_bg.png"

def generate_bg():
    if not PDF_PATH.exists():
        print(f"Error: {PDF_PATH} not found.")
        return

    doc = fitz.open(PDF_PATH)
    page = doc[0]
    
    # 2.0 zoom factor for high resolution (approx 150-200 dpi equivalent)
    # The default 72 dpi is too blurry for valid text reading
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    
    pix.save(IMG_PATH)
    print(f"Saved background image to {IMG_PATH}")
    print(f"Dimensions: {pix.width}x{pix.height}")

if __name__ == "__main__":
    generate_bg()
