import json
import argparse
import sys
import os
from evaluate_mapping import compare_data
from google import genai

class GeminiExtractor:
    def __init__(self):
        self.client = genai.Client()
    
    def extract(self, text):
        prompt = f"""
        You are an AI extracting pathology report data into a specific JSON schema.
        Extract the following medical text and map it to the corresponding JSON keys exactly as requested.
        Do not add any markdown formatting, only output valid JSON.
        
        Text to extract:
        {text}
        
        Rules and expected keys:
        - "s0_surgical_no": (string) e.g. "S-24-1234"
        - "s1_side": (string) "right" or "left"
        - "s2_proc": (string) "modified" or "simple" or "other"
        - "s3_dims": (array of strings) e.g. ["18", "9", "6"] from "specimen measuring 18 by 9 by 6"
        - "s5_dims": (array of strings) skin ellipse dimensions
        - "s5_appears_normal": (boolean) true if skin appears normal
        - "s6_check": (boolean) true if old surgical scar is mentioned
        - "s7_len": (string) scar length
        - "s7_locs": (array of strings) scar location e.g. ["upper", "inner"]
        - "s8_check": (boolean) true if ulceration mentioned
        - "s8_dims": (array of strings) ulceration dimensions
        - "s8_locs": (array of strings) ulceration locations
        - "s9_val": (array of strings) nipple status, e.g. ["everted", "inverted", "ulceration"]
        - "s10_infiltrative": (boolean) true if infiltrative mass
        - "s10_inf_dims": (array of strings) infiltrative mass dimensions
        - "s10_well": (boolean) true if well defined mass
        - "s10_well_dims": (array of strings) well defined mass dimensions
        - "s10_prev1": (boolean) true if previous surgical cavity
        - "s10_prev1_dims": (array of strings) previous surgical cavity dimensions
        - "s10_prev2": (boolean) true if residual mass is mentioned along with cavity
        - "s10_prev2_cavity_dims": (array of strings) cavity dims when residual mass is present
        - "s10_prev2_mass_dims": (array of strings) residual mass dims
        - "s10_grammar": (string) "is a", "is an", "are two", or "are multiple" depending on number of masses
        - "s10_5_quadrant_check": (boolean) true if quadrant is mentioned
        - "s10_5_quadrant_vals": (array of strings) quadrants, e.g. ["lower", "outer"]
        - "s10_5_scar": (boolean) true if located beneath scar
        - "s11_deep", "s11_superior", "s11_inferior", "s11_medial", "s11_lateral", "s11_skin": (string) margins distances. WARNING: "medium margin" means "medial margin".
        - "s12_check": (boolean) true if ratio mentioned
        - "s12_val_left", "s12_val_right": (strings) ratio values
        - "s13_type": (string) "unremarkable" or "other" for remaining tissue
        - "s14_check": (boolean) true if lymph nodes
        - "s14_min", "s14_max": (strings) lymph node sizes
        - "sections": (dictionary) exactly key-value pairs representing section mappings where value is {{"code": "A1-1", "extra": "with mass"}}. 
          Supported section keys: "= nipple", "= mass", "= old biopsy cavity with fibrosis", "= deep resected margin", "= nearest resected margin", "= sampling upper inner quadrant", "= sampling upper outer quadrant", "= sampling lower inner quadrant", "= sampling lower outer quadrant", "= sampling central region", "= axillary lymph nodes".

        Return ONLY a JSON object.
        """
        
        try:
            res = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt],
            )
            response_text = res.text.strip()
            # Remove markdown JSON wrappers if Gemini returns them
            if response_text.startswith("```json"):
                response_text = response_text[7:-3]
            elif response_text.startswith("```"):
                response_text = response_text[3:-3]
                
            return json.loads(response_text)
        except Exception as e:
            print(f"Error parsing Gemini output: {e}")
            return {}

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
    
    extractor = GeminiExtractor()
    print("-" * 50)
    
    for sample in dataset:
        report_id = sample.get("id", "Unknown")
        input_text = sample.get("input_text", "")
        expected_data = sample.get("expected_data", {})
        
        print(f"Processing Report ID: {report_id} with Gemini...")
        actual_data = extractor.extract(input_text)
        
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
    print(f"\n===== GEMINI MAPPING EVALUATION SUMMARY =====")
    print(f"Total Samples Tested: {total_samples}")
    print(f"Overall Key-Level Mapping Accuracy: {overall_accuracy:.2f}% ({total_matched_keys}/{total_expected_keys})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Mapping Accuracy using Gemini")
    parser.add_argument("--dataset", type=str, default="test_mapping_dataset.json", help="Path to json dataset")
    args = parser.parse_args()
    
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is not set.")
        exit(1)
        
    evaluate(args.dataset)
