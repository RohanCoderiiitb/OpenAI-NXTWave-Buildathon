"""
Health Report Analyzer using Local LLaMA Vision Model via Ollama
Clean version with text-to-JSON fallback parser
"""

import os
import json
import base64
import requests
from pathlib import Path
from typing import Dict, Any
import re
from PIL import Image
import io

class LocalHealthReportAnalyzer:
    """
    Analyzes health reports using locally-hosted Ollama models.
    No API keys required - runs completely on your machine.
    """
    
    def __init__(self, model_name: str = "llama3.2-vision:11b", base_url: str = "http://localhost:11434"):
        """
        Initialize the analyzer.
        
        Args:
            model_name: Name of the Ollama model to use
            base_url: URL where Ollama is running
        """
        self.model_name = model_name
        self.base_url = base_url
        self.api_endpoint = f"{base_url}/api/chat"
        
    def _convert_pdf_to_images(self, pdf_path: str) -> list:
        """Convert PDF to images using pdf2image."""
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(pdf_path, dpi=200)
            print(f"✅ Converted PDF to {len(images)} image(s)")
            return images
        except ImportError:
            raise ImportError(
                "pdf2image not installed. Install with: pip install pdf2image pillow\n"
                "Also install poppler: https://github.com/oschwartz10612/poppler-windows/releases/"
            )
    
    def _encode_image_pil(self, image: Image.Image) -> str:
        """Encode PIL Image to base64."""
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def _encode_image_file(self, file_path: str) -> str:
        """Encode image file to base64."""
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def _parse_text_to_json(self, raw_text: str) -> Dict[str, Any]:
        """
        Parse the markdown-style response into JSON format.
        This is a fallback when the model doesn't return JSON.
        """
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
            test_name = match.group(1).strip()
            value = match.group(2).strip()
            status = match.group(3).strip()
            result["extracted_values"][test_name] = {
                "value": value,
                "status": status
            }
        
        # Extract abnormality explanations
        abn_section = re.search(r'\*\*Abnormality Explanations:\*\*(.*?)\*\*Diet Plan', raw_text, re.DOTALL)
        if abn_section:
            abn_pattern = r'\* ([^:]+): ([^\n]+)'
            for match in re.finditer(abn_pattern, abn_section.group(1)):
                test_name = match.group(1).strip()
                explanation = match.group(2).strip()
                result["abnormalities"][test_name] = explanation
        
        # Generate explanation
        result["explanation"] = "The blood report shows several values outside normal ranges that require attention and dietary modifications."
        
        # Extract diet plan
        day_pattern = r'\* \*\*Day (\d+):\*\*(.*?)(?=\* \*\*Day|\*\*Disclaimer|$)'
        for match in re.finditer(day_pattern, raw_text, re.DOTALL):
            day_num = match.group(1)
            day_content = match.group(2)
            
            day_key = f"day{day_num}"
            result["diet_plan_1_week"][day_key] = {
                "breakfast": "",
                "lunch": "",
                "dinner": "",
                "snacks": ""
            }
            
            # Extract meals
            breakfast = re.search(r'Breakfast: ([^\n]+)', day_content)
            lunch = re.search(r'Lunch: ([^\n]+)', day_content)
            dinner = re.search(r'Dinner: ([^\n]+)', day_content)
            snacks = re.search(r'Snacks: ([^\n]+)', day_content)
            
            if breakfast:
                result["diet_plan_1_week"][day_key]["breakfast"] = breakfast.group(1).strip()
            if lunch:
                result["diet_plan_1_week"][day_key]["lunch"] = lunch.group(1).strip()
            if dinner:
                result["diet_plan_1_week"][day_key]["dinner"] = dinner.group(1).strip()
            if snacks:
                result["diet_plan_1_week"][day_key]["snacks"] = snacks.group(1).strip()
        
        # Extract disclaimer
        disclaimer = re.search(r'\*\*Disclaimer:\*\*(.*?)$', raw_text, re.DOTALL)
        if disclaimer:
            result["disclaimer"] = disclaimer.group(1).strip()
        else:
            result["disclaimer"] = "This is not medical advice. Consult a licensed healthcare professional."
        
        return result
    
    def _clean_json_response(self, raw_text: str) -> str:
        """Clean markdown formatting from JSON response."""
        raw_text = raw_text.strip()
        
        # Remove markdown code blocks
        if raw_text.startswith("```"):
            parts = raw_text.split("```")
            if len(parts) >= 3:
                raw_text = parts[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:].strip()
        
        return raw_text.strip()
    
    def analyze(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze a health report PDF or image.
        
        Args:
            file_path: Path to the health report file
            
        Returns:
            Dictionary containing analysis results
        """
        # Validate file exists
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        print(f"📄 Loading file: {file_path.name}")
        
        # Determine file type and encode
        file_ext = file_path.suffix.lower()
        
        if file_ext == '.pdf':
            print("📋 PDF detected - converting to image...")
            try:
                images = self._convert_pdf_to_images(str(file_path))
                image_base64 = self._encode_image_pil(images[0])
            except Exception as e:
                print(f"⚠️ PDF conversion failed: {e}")
                print("💡 Trying direct PDF encoding...")
                image_base64 = self._encode_image_file(str(file_path))
        else:
            print("🖼️ Image file detected")
            image_base64 = self._encode_image_file(str(file_path))
        
        print(f"✅ File encoded successfully")
        
        # Construct the prompt - India-focused version
        prompt = """Analyze this blood report image and return ONLY a single, complete JSON object.  
Do NOT include any extra text, markdown, comments, or explanations outside the JSON.

The JSON example shown below is ONLY a SAMPLE of the STRUCTURE.  
You MUST NOT copy the sample values, numbers, meals, or explanations.  
You MUST extract the REAL values from the uploaded report and generate UNIQUE diet plans.

-------------------------------------------------------------------

IMPORTANT RULES YOU MUST FOLLOW:

1. **DO NOT copy any of the sample test values**  
   - Example values like "145 mg/dL", "7.8%", etc. are ONLY placeholders.  
   - Your output MUST contain ONLY the values extracted from the actual uploaded report.

2. **DO NOT copy any sample meals from Day 1 or Day 2**  
   - These are ONLY examples of FORMAT and STYLE.  
   - Do NOT repeat the same dishes.  
   - Days 3–7 must contain FRESH, UNIQUE, ORIGINAL Indian meals.

3. **DIET MUST MATCH THE PERSON'S ACTUAL MEDICAL CONDITION**  
   - If the report shows high glucose → give diabetes-friendly meals.  
   - If high cholesterol → low-oil, high-fiber meals.  
   - If anemia → iron-rich Indian meals.  
   - If kidney issues → low-salt, low-potassium diet.  
   - Always tailor the diet to the abnormalities you detected.

4. **ALL meal suggestions MUST be realistic, authentic Indian dishes.**  
   Use ONLY:
   - Indian grains (jowar, bajra, ragi, wheat)
   - Dal, sabzi, roti, rice, idli, dosa, pongal, upma, poha, thepla, kadhi
   - Traditional snacks: roasted chana, sprouts, makhana
   - Healthy Indian preparations: steaming, roasting, light tadka
   - Indian spices: haldi, jeera, dhaniya, ajwain, methi

5. **Use Hindi-English mix for explanations if needed**  
   Make it friendly, simple, and easy for a patient to understand.

-------------------------------------------------------------------

The output should be of the following JSON format:

{
  "extracted_values": {
    "Test Name": {"value": "X units", "status": "low/normal/high/unknown"}
  },
  "abnormalities": {
    "Test Name": "Short simple explanation in Hinglish"
  },
  "explanation": "Overall summary of the person’s health condition based on the report.",
  "diet_plan_1_week": {
    "day1": {"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."},
    "day2": {"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."},
    "day3": {"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."},
    "day4": {"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."},
    "day5": {"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."},
    "day6": {"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."},
    "day7": {"breakfast":"...", "lunch":"...", "dinner":"...", "snacks":"..."}
  },
  "disclaimer": "यह चिकित्सा सलाह नहीं है। कृपया किसी लाइसेंस प्राप्त स्वास्थ्य पेशेवर से परामर्श करें। This is not medical advice."
}

-------------------------------------------------------------------

REPEAT:  
- Do NOT copy values from the sample.  
- Do NOT repeat sample dishes.  
- Extract ONLY from the actual report.  
- Generate diet specifically tailored to the patient's REAL medical issues.

Return ONLY the JSON object.
"""
        
        # Prepare the request payload
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_base64]
                }
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 3000
            }
        }
        
        print(f"🧠 Analyzing with {self.model_name}...")
        print("⏳ This may take 30-90 seconds depending on your hardware...")
        
        # Make the API request to Ollama
        try:
            response = requests.post(
                self.api_endpoint,
                json=payload,
                timeout=900
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise RuntimeError("❌ Cannot connect to Ollama. Make sure Ollama is running!")
        except requests.exceptions.Timeout:
            raise RuntimeError("Request timed out. The model might be too slow for your hardware.")
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_json = response.json()
                error_detail = f"\nDetails: {json.dumps(error_json, indent=2)}"
            except:
                error_detail = f"\nResponse: {response.text[:300]}"
            raise RuntimeError(f"HTTP Error {response.status_code}: {str(e)}{error_detail}")
        except Exception as e:
            raise RuntimeError(f"Request failed: {e}")
        
        # Parse the response
        try:
            result = response.json()
            
            if 'message' in result:
                raw_text = result['message'].get('content', '')
            else:
                raw_text = result.get('response', '')
            
            if not raw_text:
                raise ValueError("Empty response from model")
            
            print("✅ Received response from model")
            
        except Exception as e:
            raise RuntimeError(f"Failed to parse Ollama response: {e}")
        
        # Try to parse as JSON first, then fall back to text parsing
        try:
            cleaned_text = self._clean_json_response(raw_text)
            parsed_json = json.loads(cleaned_text)
            print("✅ Successfully parsed JSON response")
            return parsed_json
            
        except json.JSONDecodeError as e:
            print("⚠️ Response is not in JSON format, attempting to parse text format...")
            
            try:
                # Try to parse the text format into JSON
                parsed_json = self._parse_text_to_json(raw_text)
                print("✅ Successfully converted text response to JSON")
                return parsed_json
            except Exception as parse_error:
                print(f"❌ Failed to parse text format: {parse_error}")
            
            # If both methods fail, save debug info
            with open("debug_response.txt", "w", encoding='utf-8') as f:
                f.write(raw_text)
            print("💾 Full response saved to: debug_response.txt")
            
            raise RuntimeError(
                f"Model did not return valid JSON and text parsing failed.\n"
                "Check debug_response.txt for the raw response."
            )


def check_ollama_status():
    """Check if Ollama is running and available."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return True, models
        return False, []
    except:
        return False, []


def main():
    """Main execution function."""
    
    print("\n" + "="*60)
    print("🏥 LOCAL HEALTH REPORT ANALYZER")
    print("="*60 + "\n")
    
    # Check if Ollama is running
    print("🔍 Checking Ollama status...")
    is_running, available_models = check_ollama_status()
    
    if not is_running:
        print("\n❌ ERROR: Ollama is not running!")
        print("Start Ollama from the Start Menu or check Task Manager\n")
        return
    
    print("✅ Ollama is running")
    
    # Check available models
    available_model_names = [m.get('name', '') for m in available_models]
    
    model_options = ["llava:7b", "llama3.2-vision:11b"]
    model_name = None
    
    for model in model_options:
        if any(model in name for name in available_model_names):
            model_name = model
            break
    
    if not model_name:
        model_name = "llama3.2-vision:11b"
    
    model_available = any(model_name in name for name in available_model_names)
    
    if not model_available:
        print(f"\n⚠️ Model '{model_name}' not found")
        print(f"Available models: {available_model_names}")
        print(f"\nInstall with: ollama pull {model_name}\n")
        return
    
    print(f"✅ Using model: {model_name}")
    
    # Configure file path
    report_path = "dummy-1.png"  # Change this to your file
    
    if not Path(report_path).exists():
        print(f"\n❌ ERROR: File not found: {report_path}\n")
        return
    
    # Run analysis
    try:
        analyzer = LocalHealthReportAnalyzer(model_name=model_name)
        
        print(f"\n📋 Analyzing: {report_path}")
        print("-" * 60)
        
        result = analyzer.analyze(report_path)
        
        print("\n" + "="*60)
        print("✅ ANALYSIS COMPLETE")
        print("="*60 + "\n")
        
        # Pretty print results
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Save to file
        output_file = "analysis_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Results saved to: {output_file}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()