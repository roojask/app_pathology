import json
import os
import whisper
import time
from app import extract_data_15_sections
from evaluate_mapping import compare_data

DATASET_PATH = 'test_mapping_dataset.json'
AUDIO_DIR = 'audio_cases'

def evaluate_e2e(model_name):
    print(f"\n{'='*60}")
    print(f"🚀 Starting End-to-End Evaluation | Model: {model_name}")
    print(f"{'='*60}")

    print(f"Loading Whisper model '{model_name}'...")
    model = whisper.load_model(model_name)
    
    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        dataset = json.load(f)

    total_samples = len(dataset)
    total_expected_keys = 0
    total_matched_keys = 0
    start_time = time.time()

    for case in dataset:
        report_id = case.get("report_id")
        audio_path = os.path.join(AUDIO_DIR, f"{report_id}.mp3")
        expected_data = case.get("expected_output", {})

        if not os.path.exists(audio_path):
            print(f"Skipping {report_id}: Audio not found.")
            continue

        # 1. Transcribe
        result = model.transcribe(audio_path, language="en")
        hypothesis_text = result['text']

        # 2. Extract
        actual_data = extract_data_15_sections(hypothesis_text)

        # 3. Compare
        t_keys, m_keys, missing, incorrect, extra = compare_data(expected_data, actual_data)
        
        total_expected_keys += t_keys
        total_matched_keys += m_keys
        
        accuracy = (m_keys / t_keys * 100) if t_keys > 0 else 100.0
        print(f"ID: {report_id:30} | Match: {m_keys}/{t_keys} | Acc: {accuracy:6.2f}%")

    end_time = time.time()
    total_duration = end_time - start_time
    overall_accuracy = (total_matched_keys / total_expected_keys * 100) if total_expected_keys > 0 else 0.0

    print(f"\n{'='*60}")
    print(f"📊 SUMMARY - Model: {model_name}")
    print(f"{'='*60}")
    print(f"Total Samples: {total_samples}")
    print(f"Total Time   : {total_duration:.2f} seconds")
    print(f"Avg Time/Sample: {total_duration/total_samples:.2f} s")
    print(f"Overall Mapping Accuracy: {overall_accuracy:.2f}% ({total_matched_keys}/{total_expected_keys})")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    import os
    target_model = os.environ.get("WHISPER_MODEL", "base")
    evaluate_e2e(target_model)
