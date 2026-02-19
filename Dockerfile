FROM python:3.9

# 1. [เพิ่มตรงนี้] ติดตั้ง ffmpeg ในฐานะ Root ก่อน (สำคัญมาก!)
USER root
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

# 2. สร้าง User ใหม่ตามกฎ Hugging Face
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
	PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# 3. ลง Library Python
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. ก๊อปปี้ไฟล์งาน
COPY --chown=user . .

# 5. สร้างโฟลเดอร์สำหรับเก็บไฟล์
RUN mkdir -p uploads outputs

# 6. เปิดพอร์ต 7860
EXPOSE 7860

CMD ["python", "app.py"]