# ใช้ Python 3.11 ที่มีขนาดเล็ก
FROM python:3.11-slim

# ตั้งค่าโฟลเดอร์ทำงานในระบบ Cloud
WORKDIR /app

# อัปเดตระบบและติดตั้ง FFmpeg (จำเป็นมากสำหรับ Whisper)
RUN apt-get update && \
	apt-get install -y ffmpeg && \
	apt-get clean && \
	rm -rf /var/lib/apt/lists/*

# ก๊อปปี้ไฟล์ทั้งหมดในโปรเจกต์เรา ขึ้นไปบน Cloud
COPY . .

# ติดตั้งไลบรารีจาก requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# โหลดสมองกล NLP (spaCy) ล่วงหน้า
RUN python -m spacy download en_core_web_sm

# เปิด Port 7860
EXPOSE 7860

# คำสั่งรันแอปพลิเคชัน
CMD ["python", "app.py"]