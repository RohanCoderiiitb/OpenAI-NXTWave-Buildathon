"""
Health Report Analyzer using Gemini 1.5 Pro
Features:
- PDF & Image Upload Support
- Multilingual Output (User Selectable)
- Robust JSON Parsing
"""

import os
import json
import time
import re
from pathlib import Path
from typing import Dict, Any
import google.generativeai as genai

class GeminiHealthReportAnalyzer:
    """
    Analyzes health reports using Google's Gemini models.
    Supports direct PDF/Image upload and Multilingual output.
    """
    
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-pro"):
        if not api_key:
            raise ValueError("API Key is required for Gemini.")
            
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(model_name)
        
    def _parse_text_to_json(self, raw_text: str) -> Dict[str, Any]:
        """Fallback parser for markdown text."""
        result = {
            "extracted_values": {},
            "abnormalities": {},
            "explanation": "",
            "diet_plan_1_week": {},
            "disclaimer": ""
        }
        
        # Extract test results
        test_pattern = r'\* ([^:]+): ([\d.]+\s*[^\(]+)\s*\((\w+)\)'
        for match in re.finditer(test_pattern, raw_text):
            result["extracted_values"][match.group(1).strip()] = {
                "value": match.group(2).strip(),
                "status": match.group(3).strip()
            }
        
        # Extract abnormality explanations
        abn_section = re.search(r'\*\*Abnormality Explanations:\*\*(.*?)\*\*Diet Plan', raw_text, re.DOTALL)
        if abn_section:
            for match in re.finditer(r'\* ([^:]+): ([^\n]+)', abn_section.group(1)):
                result["abnormalities"][match.group(1).strip()] = match.group(2).strip()
        
        # Generic explanation fallback
        result["explanation"] = "Analysis completed."
        
        # Extract diet plan (Robust to language changes if keys are kept English)
        day_pattern = r'\* \*\*Day (\d+):\*\*(.*?)(?=\* \*\*Day|\*\*Disclaimer|$)'
        for match in re.finditer(day_pattern, raw_text, re.DOTALL):
            day_num = match.group(1)
            content = match.group(2)
            day_key = f"day{day_num}"
            
            result["diet_plan_1_week"][day_key] = {
                "breakfast": self._extract_meal(content, "Breakfast"),
                "lunch": self._extract_meal(content, "Lunch"),
                "dinner": self._extract_meal(content, "Dinner"),
                "snacks": self._extract_meal(content, "Snacks")
            }
        
        # Extract disclaimer
        disclaimer = re.search(r'\*\*Disclaimer:\*\*(.*?)$', raw_text, re.DOTALL)
        if disclaimer:
            result["disclaimer"] = disclaimer.group(1).strip()
            
        return result

    def _extract_meal(self, content, meal_name):
        """Helper to extract meal text regardless of language label if formatted correctly."""
        # We assume the model keeps "Breakfast:" label or we look for the line
        match = re.search(f'{meal_name}: ([^\n]+)', content, re.IGNORECASE)
        return match.group(1).strip() if match else ""
    
    def _clean_json_response(self, raw_text: str) -> str:
        """Clean markdown formatting."""
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            parts = raw_text.split("```")
            if len(parts) >= 3:
                raw_text = parts[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:].strip()
        return raw_text.strip()
    
    def analyze(self, file_path: str, target_language: str = "English") -> Dict[str, Any]:
        """
        Analyze a health report with language selection.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        print(f"📄 Loading file: {file_path.name}")
        print("☁️ Uploading file to Gemini...")
        uploaded_file = genai.upload_file(file_path)
        
        while uploaded_file.state.name == "PROCESSING":
            print("⏳ Waiting for file processing...")
            time.sleep(2)
            uploaded_file = genai.get_file(uploaded_file.name)
            
        if uploaded_file.state.name == "FAILED":
            raise ValueError("File processing failed.")
            
        print(f"✅ File ready. Analyzing in {target_language}...")
        
        # --- UPDATED PROMPT WITH LANGUAGE INSTRUCTION ---
        prompt = f"""Analyze this health report and return a JSON object in {target_language}.

IMPORTANT INSTRUCTIONS FOR LANGUAGE:
1. **JSON KEYS MUST BE IN ENGLISH**: Keep keys like "extracted_values", "diet_plan_1_week", "day1", "breakfast" strictly in English so my code can parse them.
2. **JSON VALUES MUST BE IN {target_language.upper()}**: Translate all explanations, meal names, advice, and the disclaimer into {target_language}.
3. **MEAL NAMES**: If the target language is an Indian language (e.g., Hindi, Telugu), write the dish name in that script (e.g., "इडली सांभर" instead of "Idli Sambar").

-------------------------------------------------------------------
RULES:
1. Extract REAL values from the report. Do not use placeholders.
2. Diet plan must be specific to the medical condition found in the report.
3. Use authentic Indian meals suitable for the condition.
-------------------------------------------------------------------

REQUIRED JSON FORMAT:
{{
  "extracted_values": {{
    "Test Name": {{"value": "X units", "status": "low/normal/high"}}
  }},
  "abnormalities": {{
    "Test Name": "Explanation in {target_language}"
  }},
  "explanation": "Summary in {target_language}",
  "diet_plan_1_week": {{
    "day1": {{"breakfast":"Meal in {target_language}", "lunch":"...", "dinner":"...", "snacks":"..."}},
    "day2": {{"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."}},
    "day3": {{"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."}},
    "day4": {{"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."}},
    "day5": {{"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."}},
    "day6": {{"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."}},
    "day7": {{"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."}}
  }},
  "disclaimer": "Medical disclaimer in {target_language}"
}}

Return ONLY the JSON.
"""

        try:
            response = self.model.generate_content(
                [uploaded_file, prompt],
                generation_config={"temperature": 0.1}
            )
            raw_text = response.text
        except Exception as e:
            raise RuntimeError(f"Gemini API request failed: {e}")

        # Parse Response
        try:
            cleaned_text = self._clean_json_response(raw_text)
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            print("⚠️ JSON parse failed, attempting fallback...")
            try:
                return self._parse_text_to_json(raw_text)
            except:
                with open("debug_response.txt", "w", encoding='utf-8') as f:
                    f.write(raw_text)
                raise RuntimeError("Failed to parse response. Check debug_response.txt")

def main():
    print("\n" + "="*60)
    print("🏥 GEMINI HEALTH REPORT ANALYZER")
    print("="*60 + "\n")
    
    api_key = "AIzaSyAKpTaEyiwC1lx3OeZskoUdyf3E7BSyQ1s"
    if not api_key:
        print("❌ Error: GOOGLE_API_KEY not found.")
        return

    # --- 1. LANGUAGE SELECTION FEATURE ---
    print("Available Languages: English, Hindi, Telugu, Tamil, Kannada, Marathi, Bengali, etc.")
    lang_input = input("Enter your preferred language (default: English): ").strip()
    target_lang = lang_input if lang_input else "English"
    
    model_name = "gemini-2.5-pro"
    
    report_path = "health_report.pdf" 
    if not Path(report_path).exists():
        print(f"\n❌ ERROR: File not found: {report_path}")
        return
    
    try:
        analyzer = GeminiHealthReportAnalyzer(api_key=api_key, model_name=model_name)
        
        # Pass language to analyze method
        result = analyzer.analyze(report_path, target_language=target_lang)
        
        print("\n" + "="*60)
        print("✅ ANALYSIS COMPLETE")
        print("="*60 + "\n")
        
        # Print JSON to console (ensure utf-8 for Indian languages)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Save to file
        output_file = f"analysis_result_{target_lang}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Results saved to: {output_file}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()