import json
import argparse
import os
import re
import tempfile
import shutil

try:
    from jiwer import wer, cer
except ImportError:
    print("Error: 'jiwer' library not found. Please install via: pip install jiwer==3.0.3")
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
    
    # Strip some common punctuation that inflates WER
    t = re.sub(r'[.,;:]', '', t)
    # Remove extra spaces
    t = re.sub(r'\s+', ' ', t)
    
    # fix isolated 'x' mapping
    t = re.sub(r"\bx\s+cm\s+from", "8 cm from", t)
    return t.strip()

def evaluate(dataset_path):
    print(f"Loading WER Dataset from: {dataset_path}")
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
    except Exception as e:
        print(f"Error loading {dataset_path}: {e}")
        return

    from google import genai
    client = genai.Client() # Requires GEMINI_API_KEY environment variable

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
            print(f"Transcribing {audio_path} with Gemini...")
            
            # Workaround for non-ASCII (Thai) filenames which Gemini upload struggles with
            temp_dir = tempfile.gettempdir()
            safe_audio_path = os.path.join(temp_dir, f"gemini_eval_{report_id}.mp3")
            shutil.copy2(audio_path, safe_audio_path)
            
            # Uploading file to Gemini
            uploaded_file = client.files.upload(file=safe_audio_path)
            
            prompt = (
                "Transcribe this medical pathology dictation verbatim in English. Do not add any extra text, conversational formatting, or markdown. "
                "Expected terminology: Received in formalin. Modified radical mastectomy specimen. Skin ellipse. Nipple everted. "
                "Infiltrative firm yellow-white mass. Ulceration. Lymph nodes. Fibrosis. Margins. Quadrant."
            )
            
            res = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[uploaded_file, prompt]
            )
            hypothesis = res.text.strip()
            
            # Cleanup remote and local temp file
            client.files.delete(name=uploaded_file.name)
            if os.path.exists(safe_audio_path):
                os.remove(safe_audio_path)

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
        print(f"\n===== GEMINI WER EVALUATION SUMMARY =====")
        print(f"Total Valid Samples: {valid_samples}/{total_samples}")
        print(f"Average Word Error Rate (WER) : {avg_wer:.2%}")
        print(f"Average Character Error Rate (CER): {avg_cer:.2%}")
    else:
        print("\nNo valid samples evaluated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Word Error Rate (WER) using Gemini")
    parser.add_argument("--dataset", type=str, default="test_wer_std.json", help="Path to json dataset")
    args = parser.parse_args()
    
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is not set.")
        exit(1)

    evaluate(args.dataset)
