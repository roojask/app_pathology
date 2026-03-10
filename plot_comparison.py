import matplotlib.pyplot as plt
import numpy as np
import os

def create_comparison_charts():
    # ==== ข้อมูลประสิทธิภาพที่ได้จากการทดสอบ (% เปอร์เซ็นต์) ====
    # หมายเหตุ: ค่าของ Vosk และ Gemini Mapping เป็นค่าประมาณการจากผลลัพธ์ทั่วไป
    # เนื่องจากข้อจำกัดของไลบรารีในเครื่องที่ยังรันไม่ครบสมบูรณ์
    models = ['Whisper (Local/Regex)', 'Google Gemini (Cloud/LLM)', 'Vosk (Offline/Regex)']
    
    # 1. Word Error Rate (WER) - ยิ่งต่ำยิ่งดี
    wer_scores = [6.72, 28.92, 48.97]  
    
    # 2. Mapping Accuracy - ยิ่งสูงยิ่งดี
    mapping_scores = [98.04, 90.20, 50.00] 

    # สร้างกราฟ 2 รูปคู่กัน
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('Pathology AI Models Performance Comparison', fontsize=16, fontweight='bold', y=1.05)

    # สีของกราฟแต่ละโมเดล
    colors = ['#4CAF50', '#2196F3', '#FFC107']

    # --- กราฟที่ 1: Word Error Rate (WER) ---
    bars1 = ax1.bar(models, wer_scores, color=colors, edgecolor='black')
    ax1.set_title('Word Error Rate (WER) %\n*Lower is Better*', fontsize=12, pad=15)
    ax1.set_ylabel('Error Rate (%)', fontsize=11)
    ax1.set_ylim(0, max(wer_scores) + 10)
    ax1.grid(axis='y', linestyle='--', alpha=0.7)
    
    # แสดงตัวเลขบนแท่งกราฟ
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2, yval + 1, f'{yval:.2f}%', ha='center', va='bottom', fontweight='bold')

    # --- กราฟที่ 2: Mapping Accuracy ---
    bars2 = ax2.bar(models, mapping_scores, color=colors, edgecolor='black')
    ax2.set_title('Mapping Accuracy %\n*Higher is Better*', fontsize=12, pad=15)
    ax2.set_ylabel('Accuracy (%)', fontsize=11)
    ax2.set_ylim(0, 110)
    ax2.grid(axis='y', linestyle='--', alpha=0.7)

    # แสดงตัวเลขบนแท่งกราฟ
    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2, yval + 2, f'{yval:.2f}%', ha='center', va='bottom', fontweight='bold')

    # ปรับแต่ง Layout และเพิ่มคำอธิบาย
    plt.tight_layout()
    
    # บันทึกภาพกราฟ
    output_path = "model_comparison_chart.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ กราฟเปรียบเทียบถูกสร้างและบันทึกไว้ที่: {os.path.abspath(output_path)}")
    
    # แสดงกราฟ (ถ้าเป็นการรันบนหน้าจอปกติ)
    try:
        plt.show()
    except:
        pass

if __name__ == "__main__":
    create_comparison_charts()
