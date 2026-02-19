import fitz
import sys
print("Start Open")
sys.stdout.flush()
try:
    doc = fitz.open("d:/app_pathology/assets/Breast_Gross_Template.pdf")
    print(f"Opened. Pages: {len(doc)}")
except Exception as e:
    print(f"Error: {e}")
print("End Open")
sys.stdout.flush()
