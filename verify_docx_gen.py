
import os
import fitz
from pdf2docx import Converter

# Mock PDF generation for testing
def create_test_pdf(filename):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Test PDF for DOCX Conversion", fontsize=20)
    
    # Draw some shapes (tick)
    shape = page.new_shape()
    shape.draw_line((100, 150), (110, 160))
    shape.draw_line((110, 160), (130, 130))
    shape.finish(color=(1, 0, 0), width=1.5)
    shape.commit()
    
    doc.save(filename)
    doc.close()
    print(f"Created test PDF: {filename}")

def test_conversion(pdf_file, docx_file):
    print(f"Converting {pdf_file} to {docx_file}...")
    try:
        cv = Converter(pdf_file)
        cv.convert(docx_file, start=0, end=None)
        cv.close()
        print(f"Conversion successful!")
        
        if os.path.exists(docx_file):
            size = os.path.getsize(docx_file)
            print(f"DOCX created. Size: {size} bytes")
            if size > 0:
                print("PASSED: File is not empty.")
            else:
                print("FAILED: File is empty.")
        else:
            print("FAILED: DOCX file not found.")
            
    except Exception as e:
        print(f"FAILED: Exception occurred: {e}")

if __name__ == "__main__":
    pdf_filename = "test_verify.pdf"
    docx_filename = "test_verify.docx"
    
    create_test_pdf(pdf_filename)
    test_conversion(pdf_filename, docx_filename)
    
    # Cleanup
    # try:
    #     os.remove(pdf_filename)
    #     os.remove(docx_filename)
    #     print("Cleanup done.")
    # except:
    #     pass
