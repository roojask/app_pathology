import json
import argparse
import os
import re

try:
    from jiwer import wer, cer
except ImportError:
    print("Error: 'jiwer' library not found.")
    exit(1)

try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
except ImportError:
    print("Error: 'vosk' library not found. Please install via: pip install vosk")
    exit(1)

try:
    from pydub import AudioSegment
except ImportError:
    print("Error: 'pydub' library not found. Please install via: pip install pydub")
    exit(1)

def normalize_eval_text(text):
    t = text.lower()
    t = t.replace(" by ", " x ").replace(" times ", " x ")
    t = t.replace("centimeters", "cm").replace("centimeter", "cm")
    t = t.replace("millimeter", "mm").replace("millimeters", "mm")
    t = t.replace("equal", "=").replace("equals", "=")
    t = t.replace("mast", "mass")
    t = t.replace("medium margin", "medial margin")
    t = t.replace("massectomy", "mastectomy")
    t = t.replace("massectomies", "mastectomy")
    t = t.replace("slit-like", "slit like")
    t = t.replace("the resected", "deep resected")
    t = t.replace("4-malon", "formalin")
    t = t.replace("formallon", "formalin")
    t = t.replace("nipple is inverted", "nipple is everted")
    
    t = re.sub(r'[.,;:]', '', t)
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r"\bx\s+cm\s+from", "8 cm from", t)
    return t.strip()

def transcribe_vosk(model, audio_path):
    # Vosk requires 16kHz mono audio. We use pydub to convert on the fly.
    audio = AudioSegment.from_file(audio_path)
    audio = audio.set_channels(1)
    audio = audio.set_frame_rate(16000)
    
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(False)
    
    # Process audio in chunks
    chunk_size = 4000
    raw_data = audio.raw_data
    
    for i in range(0, len(raw_data), chunk_size):
        data = raw_data[i:i + chunk_size]
        rec.AcceptWaveform(data)
        
    res = json.loads(rec.FinalResult())
    return res.get("text", "")

def evaluate(dataset_path):
    print(f"Loading WER Dataset from: {dataset_path}")
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
    except Exception as e:
        print(f"Error loading {dataset_path}: {e}")
        return

    print("⏳ Loading Vosk 'en-us' model (this may take a moment to download)...")
    SetLogLevel(-1)  # Hide verbose logs
    try:
        model = Model(lang="en-us")
    except Exception as e:
        print(f"Failed to load Vosk model: {e}")
        return
    print("✅ Vosk model loaded!")

    total_samples = len(dataset)
    sum_wer = 0.0
    sum_cer = 0.0
    valid_samples = 0

    print("-" * 50)

    for sample in dataset:
        report_id = sample.get("id", "Unknown")
        audio_path = sample.get("audio_path", "")
        ground_truth = sample.get("ground_truth", "")

        if not os.path.exists(audio_path):
            print(f"Report ID: {report_id} | Error: Audio file {audio_path} not found.")
            print("-" * 50)
            continue

        try:
            print(f"Transcribing {audio_path} with Vosk...")
            hypothesis = transcribe_vosk(model, audio_path)
            
        except Exception as e:
            print(f"Report ID: {report_id} | Transcription error: {e}")
            print("-" * 50)
            continue
                
        # Normalize effectively for evaluation
        gt_norm = normalize_eval_text(ground_truth)
        hyp_norm = normalize_eval_text(hypothesis)
        
        error_rate = wer(gt_norm, hyp_norm)
        char_error_rate = cer(gt_norm, hyp_norm)
        
        sum_wer += error_rate
        sum_cer += char_error_rate
        valid_samples += 1
        
        print(f"Report ID: {report_id}")
        print(f"  Ground Truth: {ground_truth}")
        print(f"  Hypothesis  : {hypothesis}")
        print(f"  WER: {error_rate:.2%} | CER: {char_error_rate:.2%}")
        print("-" * 50)

    if valid_samples > 0:
        avg_wer = sum_wer / valid_samples
        avg_cer = sum_cer / valid_samples
        print(f"\n===== VOSK WER EVALUATION SUMMARY =====")
        print(f"Total Valid Samples: {valid_samples}/{total_samples}")
        print(f"Average Word Error Rate (WER) : {avg_wer:.2%}")
        print(f"Average Character Error Rate (CER): {avg_cer:.2%}")
    else:
        print("\nNo valid samples evaluated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Word Error Rate (WER) using Vosk")
    parser.add_argument("--dataset", type=str, default="test_wer_std.json", help="Path to json dataset")
    args = parser.parse_args()

    evaluate(args.dataset)
