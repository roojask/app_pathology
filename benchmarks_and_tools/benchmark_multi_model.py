import json
import os
import time
import argparse
import re
import torch
import vosk
import whisper
from jiwer import wer, cer

# For Vosk audio conversion
from pydub import AudioSegment
import wave

# Normalization logic from original evaluate_wer.py
def normalize_eval_text(text):
    if not text: return ""
    t = text.lower()
    t = t.replace(" by ", " x ").replace(" times ", " x ")
    t = t.replace("centimeters", "cm").replace("centimeter", "cm")
    t = t.replace("millimeter", "mm").replace("millimeters", "mm")
    t = t.replace("equal", "=").replace("equals", "=")
    t = t.replace("mast", "mass")
    t = t.replace("medium margin", "medial margin")
    t = t.replace("massectomy", "mastectomy")
    t = t.replace("slit-like", "slit like")
    t = t.replace("the resected", "deep resected")
    t = re.sub(r'[.,;:]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def transcribe_openai(model, audio_path, prompt=None):
    result = model.transcribe(audio_path, language="en", initial_prompt=prompt)
    return result["text"]

def transcribe_faster(model, audio_path):
    segments, info = model.transcribe(audio_path, beam_size=5)
    return " ".join([segment.text for segment in segments])

def transcribe_vosk(model, audio_path):
    # Vosk needs 16000Hz Mono PCM
    audio = AudioSegment.from_file(audio_path)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    temp_wav = "temp_vosk.wav"
    audio.export(temp_wav, format="wav")
    
    wf = wave.open(temp_wav, "rb")
    rec = vosk.KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)
    
    results = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            part = json.loads(rec.Result())
            results.append(part.get("text", ""))
    
    final = json.loads(rec.FinalResult())
    results.append(final.get("text", ""))
    
    wf.close()
    if os.path.exists(temp_wav): os.remove(temp_wav)
    return " ".join(results).strip()

def run_benchmark(model_type, dataset_path, vosk_model_path=None):
    print(f"\n🚀 Running Benchmark for: {model_type}")
    
    with open(dataset_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    # Load Model
    start_load = time.time()
    model = None
    prompt = None
    
    if model_type == "vosk":
        model = vosk.Model(vosk_model_path)
    elif model_type.startswith("openai-"):
        m_name = model_type.replace("openai-", "")
        if m_name == "small-prompt":
            m_name = "small"
            prompt = "Received in formalin. Modified radical mastectomy specimen. Skin ellipse. Nipple everted. Infiltrative firm yellow-white mass. Poorly circumscribed yellow-white lesion. Ulceration. Lymph nodes. Fibrosis. Margins. Quadrant."
        model = whisper.load_model(m_name)
    elif model_type == "faster-base-int8":
        from faster_whisper import WhisperModel
        # CPU INT8
        model = WhisperModel("base", device="cpu", compute_type="int8")
    
    load_time = time.time() - start_load
    print(f"✅ Model loaded in {load_time:.2f}s")

    results_summary = []
    total_samples = len(dataset)
    sum_wer = 0
    sum_cer = 0
    total_time = 0

    for i, sample in enumerate(dataset):
        audio_path = sample["audio_path"]
        gt = sample["ground_truth"]
        
        start_t = time.time()
        if model_type == "vosk":
            hyp = transcribe_vosk(model, audio_path)
        elif model_type.startswith("openai-"):
            hyp = transcribe_openai(model, audio_path, prompt)
        elif model_type == "faster-base-int8":
            hyp = transcribe_faster(model, audio_path)
        
        duration = time.time() - start_t
        total_time += duration
        
        gt_norm = normalize_eval_text(gt)
        hyp_norm = normalize_eval_text(hyp)
        
        w = wer(gt_norm, hyp_norm)
        c = cer(gt_norm, hyp_norm)
        
        sum_wer += w
        sum_cer += c
        
        print(f"[{i+1}/{total_samples}] {sample['id']}: WER={w:.2%} | Time={duration:.2f}s")
        
    avg_wer = sum_wer / total_samples
    avg_cer = sum_cer / total_samples
    avg_speed = total_time / total_samples

    print(f"\n📊 {model_type} SUMMARY:")
    print(f"   Avg WER  : {avg_wer:.2%}")
    print(f"   Avg CER  : {avg_cer:.2%}")
    print(f"   Avg Speed: {avg_speed:.2f}s/sample")
    
    return {
        "model": model_type,
        "wer": avg_wer,
        "cer": avg_cer,
        "avg_speed": avg_speed,
        "load_time": load_time
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--dataset", type=str, default="eval_stt_cases.json")
    parser.add_argument("--vosk_path", type=str, default="vosk-model/vosk-model-small-en-us-0.15")
    args = parser.parse_args()
    
    res = run_benchmark(args.model, args.dataset, args.vosk_path)
    
    # Save to a log file
    log_file = "benchmark_results_all.json"
    all_res = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            all_res = json.load(f)
    
    # Update or append
    updated = False
    for i, r in enumerate(all_res):
        if r["model"] == res["model"]:
            all_res[i] = res
            updated = True
            break
    if not updated:
        all_res.append(res)
        
    with open(log_file, "w") as f:
        json.dump(all_res, f, indent=4)
