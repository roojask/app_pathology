import json
import os

DATASET_PATH = 'test_mapping_dataset.json'
AUDIO_DIR = 'audio_cases'
OUTPUT_PATH = 'eval_stt_cases.json'

with open(DATASET_PATH, 'r', encoding='utf-8') as f:
    dataset = json.load(f)

eval_data = []

for case in dataset:
    report_id = case.get("report_id")
    transcription = case.get("transcription")
    audio_path = os.path.join(AUDIO_DIR, f"{report_id}.mp3")
    
    if os.path.exists(audio_path):
        eval_data.append({
            "id": report_id,
            "audio_path": os.path.abspath(audio_path),
            "ground_truth": transcription
        })
    else:
        print(f"Warning: Audio file not found for {report_id}")

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(eval_data, f, indent=4, ensure_ascii=False)

print(f"✅ Created {OUTPUT_PATH} with {len(eval_data)} samples.")
