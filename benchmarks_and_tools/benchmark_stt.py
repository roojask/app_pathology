import os
import time
import json
import whisper
from faster_whisper import WhisperModel
from vosk import Model, KaldiRecognizer
from pydub import AudioSegment
import io
import wave
from jiwer import wer

# --- Configuration ---
DATASET_PATH = "test_wer_std.json"
WHISPER_MODELS = ["tiny", "base", "small"]
PROMPT = "Received in formalin. Modified radical mastectomy specimen. Skin ellipse. Nipple everted. Infiltrative firm yellow-white mass. Ulceration. Lymph nodes. Fibrosis. Margins. Quadrant."

def normalize_benchmark_text(text):
    import re
    t = text.lower()
    t = t.replace(" by ", " x ").replace(" times ", " x ")
    t = t.replace("centimeters", "cm").replace("centimeter", "cm")
    t = re.sub(r'[.,;:]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def run_whisper_benchmark():
    print("=== Whisper Multi-Model Benchmark ===")
    
    if not os.path.exists(DATASET_PATH):
        print(f"Error: Dataset {DATASET_PATH} not found.")
        return

    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    results = {}

    for model_name in WHISPER_MODELS:
        print(f"\nEvaluating Whisper Model: {model_name}")
        try:
            model = whisper.load_model(model_name)
        except Exception as e:
            print(f"Failed to load {model_name}: {e}")
            continue

        total_wer = 0.0
        total_time = 0.0
        count = 0

        for sample in dataset:
            audio_path = sample.get("audio_path")
            ground_truth = sample.get("ground_truth")
            
            if not os.path.exists(audio_path):
                continue

            start = time.time()
            res = model.transcribe(audio_path, language="en", initial_prompt=PROMPT)
            end = time.time()

            hypothesis = res["text"]
            
            gt_norm = normalize_benchmark_text(ground_truth)
            hyp_norm = normalize_benchmark_text(hypothesis)
            
            error = wer(gt_norm, hyp_norm)
            
            total_wer += error
            total_time += (end - start)
            count += 1
            print(f"  Sample {count}: WER {error:.2%}, Time {(end-start):.2f}s")

        if count > 0:
            avg_wer = (total_wer / count) * 100
            avg_time = total_time / count
            results[model_name] = {"avg_wer": avg_wer, "avg_time": avg_time}
            print(f">> Result for {model_name}: Avg WER {avg_wer:.2f}%, Avg Time {avg_time:.2f}s")

    return results

def run_faster_whisper_benchmark():
    print("\n=== Faster-Whisper (Base) Benchmark ===")
    
    if not os.path.exists(DATASET_PATH):
        return {}

    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    # Load faster-whisper base
    print("Loading faster-whisper base-en...")
    model = WhisperModel("base.en", device="cpu", compute_type="int8")

    total_wer = 0.0
    total_time = 0.0
    count = 0

    for sample in dataset:
        audio_path = sample.get("audio_path")
        ground_truth = sample.get("ground_truth")
        
        if not os.path.exists(audio_path): continue

        start = time.time()
        segments, _ = model.transcribe(audio_path, beam_size=5, initial_prompt=PROMPT)
        hypothesis = " ".join([seg.text for seg in segments])
        end = time.time()

        gt_norm = normalize_benchmark_text(ground_truth)
        hyp_norm = normalize_benchmark_text(hypothesis)
        
        error = wer(gt_norm, hyp_norm)
        total_wer += error
        total_time += (end - start)
        count += 1
        print(f"  Sample {count}: WER {error:.2%}, Time {(end-start):.2f}s")

    if count > 0:
        avg_wer = (total_wer / count) * 100
        avg_time = total_time / count
        print(f">> Result for faster-whisper (base): Avg WER {avg_wer:.2f}%, Avg Time {avg_time:.2f}s")
        return {"avg_wer": avg_wer, "avg_time": avg_time}
    return {}

def run_vosk_benchmark():
    print("\n=== Vosk Benchmark ===")
    VOSK_MODEL_PATH = "vosk-model"
    if not os.path.exists(VOSK_MODEL_PATH) or not os.path.exists(DATASET_PATH):
        return {}

    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    print("Loading Vosk model...")
    model = Model(VOSK_MODEL_PATH)

    total_wer = 0.0
    total_time = 0.0
    count = 0

    for sample in dataset:
        audio_path = sample.get("audio_path")
        ground_truth = sample.get("ground_truth")
        
        if not os.path.exists(audio_path): continue

        # Vosk needs wav with 16kHz, mono
        # We assume the wav files in the dataset are compatible or we'd need to convert
        # Since input_Breast.wav is 16k mono (usually), we try directly
        
        start = time.time()
        try:
            # ใช้ pydub โหลดไฟล์เสียง (รองรับทั้ง wav, mp3 และอื่นๆ)
            audio = AudioSegment.from_file(audio_path)
            audio = audio.set_frame_rate(16000).set_channels(1) # คอนเวิร์ตเป็น 16kHz Mono สำหรับ Vosk
            
            wave_stream = io.BytesIO()
            audio.export(wave_stream, format="wav")
            wave_stream.seek(0)
            
            wf = wave.open(wave_stream, "rb")
            rec = KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)
            
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                rec.AcceptWaveform(data)
            
            res_json = json.loads(rec.FinalResult())
            hypothesis = res_json.get("text", "")
            wf.close()
        except Exception as e:
            print(f"Vosk error for {audio_path}: {e}")
            continue
            
        end = time.time()

        gt_norm = normalize_benchmark_text(ground_truth)
        hyp_norm = normalize_benchmark_text(hypothesis)
        
        error = wer(gt_norm, hyp_norm)
        total_wer += error
        total_time += (end - start)
        count += 1
        print(f"  Sample {count}: WER {error:.2%}, Time {(end-start):.2f}s")

    if count > 0:
        avg_wer = (total_wer / count) * 100
        avg_time = total_time / count
        print(f">> Result for Vosk: Avg WER {avg_wer:.2f}%, Avg Time {avg_time:.2f}s")
        return {"avg_wer": avg_wer, "avg_time": avg_time}
    return {}

if __name__ == "__main__":
    results = {}
    RESULTS_FILE = "stt_benchmark_results.json"
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
        except: pass

    # Run Whisper if not already done
    whisper_results = run_whisper_benchmark()
    results.update(whisper_results)
    
    fw_res = run_faster_whisper_benchmark()
    if fw_res:
        results["faster-whisper (base)"] = fw_res
    
    vosk_res = run_vosk_benchmark()
    if vosk_res:
        results["vosk"] = vosk_res
    
    # Save results
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)
        
    print("\nBenchmark completed. Results saved to stt_benchmark_results.json")
