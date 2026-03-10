import json
import argparse
import sys
from app import extract_data_15_sections

def compare_data(expected, actual):
    """
    Compares the expected dictionary with the actual extracted dictionary.
    Returns (total_keys, matched_keys, missing_keys, incorrect_keys, extra_keys)
    """
    total_keys = len(expected)
    matched_keys = 0
    missing_keys = []
    incorrect_keys = []
    extra_keys = []
    
    for key, expected_val in expected.items():
        if key not in actual:
            missing_keys.append(key)
        else:
            actual_val = actual[key]
            if expected_val == actual_val:
                matched_keys += 1
            else:
                incorrect_keys.append((key, expected_val, actual_val))
                
    for key in actual:
        if key not in expected and key != "_low_confidence":
            extra_keys.append(key)
            
    return total_keys, matched_keys, missing_keys, incorrect_keys, extra_keys

def evaluate(dataset_path):
    print(f"Loading Mapping Dataset from: {dataset_path}")
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
    except Exception as e:
        print(f"Error loading {dataset_path}: {e}")
        return
        
    total_samples = len(dataset)
    total_expected_keys = 0
    total_matched_keys = 0
    
    print("-" * 50)
    
    for sample in dataset:
        report_id = sample.get("id", "Unknown")
        input_text = sample.get("input_text", "")
        expected_data = sample.get("expected_data", {})
        
        # Run extraction
        actual_data = extract_data_15_sections(input_text)
        
        # Compare
        t_keys, m_keys, missing, incorrect, extra = compare_data(expected_data, actual_data)
        
        total_expected_keys += t_keys
        total_matched_keys += m_keys
        
        percent_acc = (m_keys / t_keys * 100) if t_keys > 0 else 100.0
        
        print(f"Report ID: {report_id} | Accuracy: {percent_acc:.2f}% ({m_keys}/{t_keys})")
        if missing:
            print(f"  [!] Missing Keys: {missing}")
        if incorrect:
            print("  [!] Incorrect Values:")
            for k, e_val, a_val in incorrect:
                print(f"      - {k}: Expected {e_val}, Got {a_val}")
        if extra:
            print(f"  [?] Extra Keys Extracted (Not in ground truth): {extra}")
        print("-" * 50)
            
    overall_accuracy = (total_matched_keys / total_expected_keys * 100) if total_expected_keys > 0 else 0.0
    print(f"\n===== EVALUATION SUMMARY =====")
    print(f"Total Samples Tested: {total_samples}")
    print(f"Overall Key-Level Mapping Accuracy: {overall_accuracy:.2f}% ({total_matched_keys}/{total_expected_keys})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Mapping Accuracy against Ground Truth")
    parser.add_argument("--dataset", type=str, default="mock_mapping_dataset.json", help="Path to json dataset")
    args = parser.parse_args()
    
    evaluate(args.dataset)
