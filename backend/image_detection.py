import os
import uuid
import json
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Google GenAI SDK
# pip install google-genai
import google.generativeai as genai

# ----------------------------
# Configuration
# ----------------------------
# Set your Google API key in environment before running:
# export GOOGLE_API_KEY="your_key_here"
API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("WARNING: GOOGLE_API_KEY / GEMINI_API_KEY not found in environment. Set it before running.")
# Initialize client
genai.configure(api_key=API_KEY)
client = genai  # alias to match naming below

# Limits and allowed types
MAX_IMAGES = 6
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
UPLOAD_FOLDER = "fridge_uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Flask app
app = Flask(__name__)
CORS(app)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ----------------------------
# Prompt (same carefully-designed JSON schema prompt)
# ----------------------------
INGREDIENT_EXTRACTION_PROMPT = """
You are a reliable kitchen assistant and visual recognizer. You will be shown MULTIPLE IMAGES of a refrigerator interior.
Task (do all of the following):

1) VISUAL EXTRACTION:
   - Identify all food ingredients and edible items visible across ALL images.
   - Include fresh produce (e.g., tomato, spinach), packaged goods (e.g., butter, milk carton, pasta packet), condiments (e.g., soy sauce, ketchup), dairy, eggs, leftovers in containers, and beverage items that could be used as ingredients.
   - Ignore purely non-food objects (shelves, containers without visible food, magnets, labels that are not ingredient names).
   - Try to detect duplicates across images and consolidate them.

2) NORMALIZATION:
   - Normalize common names to simple tokens (e.g., "bell pepper" -> "capsicum" or "bell pepper", "cilantro" -> "coriander", "chilled shredded mozzarella" -> "cheese (mozzarella)").
   - Provide a short canonical name field and an array of raw labels you might have seen.

3) QUANTITY ESTIMATION (if visibly clear):
   - If you can visually estimate count (e.g., "3 tomatoes", "1 loaf of bread"), return an estimated `quantity` with a string. Otherwise set `quantity` to null.
   - Do not guess weight — only count or clear container indicators (e.g., "milk carton (1)", "eggs (6-pack)").

4) CONFIDENCE:
   - Provide a `confidence` score between 0.0 and 1.0 for each detected ingredient describing how sure you are.

5) NOTES:
   - If an ingredient is partially obscured or ambiguous, add a short `note` describing the ambiguity (e.g., "partially obscured — could be 'jalapeno' or 'green chili'").

6) SUGGESTIONS FOR THE USER (single short string):
   - If any ingredient is badly pictured (blurry, too dark, reflection), include one short suggestion message to the user explaining how to take better photos next time.

7) JSON OUTPUT:
   - **Return ONLY valid JSON** following this schema exactly (no surrounding text):

{
  "ingredients": [
    {
      "canonical_name": "tomato",
      "raw_labels": ["tomato", "red tomato", "tomatoes"],
      "confidence": 0.92,
      "quantity": "3",            # or null
      "note": ""                  # or short string
    },
    ...
  ],
  "suggestion_for_better_photos": "Short single sentence or empty string if none."
}

Important formatting rules:
- The JSON must be parseable by a standard JSON parser.
- Use arrays and simple types only (strings, numbers, booleans).
- If you are not sure about a quantity, use null.
- Remove duplicates by canonical_name and merge raw_labels and choose the maximum confidence.
"""

# ----------------------------
# Helper: upload images to Gemini and call model
# ----------------------------
def detect_ingredients_from_images(image_filepaths):
    """
    Uploads each image to Gemini using client.files.upload, then calls models.generate_content
    with the prompt and the uploaded file references. Returns parsed JSON.
    """
    uploaded_objects = []
    try:
        for path in image_filepaths:
            # The google-genai SDK exposes client.files.upload(file=...)
            # It accepts either a path or file-like object; we'll pass the path.
            uploaded = client.files.upload(file=path)
            uploaded_objects.append(uploaded)
    except Exception as e:
        print("Error uploading files to Gemini:", e)
        traceback.print_exc()
        raise RuntimeError(f"Failed to upload files to Gemini: {e}") from e

    # Build contents: the prompt string followed by each uploaded file object
    contents = [INGREDIENT_EXTRACTION_PROMPT]
    contents.extend(uploaded_objects)

    try:
        # Call the model — choose a vision-capable Gemini model
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            temperature=0.0,
            max_output_tokens=1500
        )
    except Exception as e:
        print("Error calling Gemini generate_content:", e)
        traceback.print_exc()
        raise RuntimeError(f"Gemini model call failed: {e}") from e

    # Extract text from response (robust handling)
    raw_text = None
    # genai SDK responses usually have .text
    if getattr(response, "text", None):
        raw_text = response.text
    else:
        # Try to stringify 'output' or 'candidates' if present
        if getattr(response, "output", None):
            try:
                raw_text = json.dumps(response.output)
            except Exception:
                raw_text = str(response.output)
        elif getattr(response, "candidates", None):
            try:
                # candidates often hold generated text pieces
                raw_text = " ".join([c.text for c in response.candidates if getattr(c, "text", None)])
            except Exception:
                raw_text = str(response.candidates)

    if not raw_text:
        raise RuntimeError("No textual response from Gemini to parse as JSON.")

    # Model should return only JSON — try direct parse first, then robust extraction
    try:
        parsed = json.loads(raw_text)
        return parsed
    except Exception:
        # Try to locate the first JSON object in the text (from first '{' to last '}')
        try:
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = raw_text[start:end+1]
                parsed = json.loads(candidate)
                return parsed
        except Exception as ex:
            print("Failed robust JSON extraction:", ex)
            traceback.print_exc()

    # If still not parsed, raise helpful error with the raw response attached
    raise RuntimeError(f"Failed to parse JSON from model response. Raw response:\n{raw_text}")


# ----------------------------
# Flask route: accept multiple images and return JSON
# ----------------------------
@app.route("/fridge_scan", methods=["POST"])
def fridge_scan():
    try:
        if "images" not in request.files:
            return jsonify({"error": "No images part in form-data. Use the key 'images' for multiple files."}), 400

        files = request.files.getlist("images")
        if not files:
            return jsonify({"error": "No files uploaded under key 'images'."}), 400

        if len(files) > MAX_IMAGES:
            return jsonify({"error": f"Too many images. Max allowed is {MAX_IMAGES}."}), 400

        saved_paths = []
        for file in files:
            if file.filename == "":
                return jsonify({"error": "One of the uploaded files has an empty filename."}), 400
            if not allowed_file(file.filename):
                return jsonify({"error": f"File type not allowed: {file.filename}. Allowed: {ALLOWED_EXTENSIONS}"}), 400

            # save with a unique name to avoid collisions
            filename = secure_filename(file.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            filepath = os.path.join(UPLOAD_FOLDER, unique_name)
            file.save(filepath)
            saved_paths.append(filepath)

        # Call Gemini vision + LLM pipeline
        parsed_output = detect_ingredients_from_images(saved_paths)

        # Return parsed JSON to frontend
        return jsonify({"success": True, "result": parsed_output})

    except Exception as e:
        print("Server error at /fridge_scan:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ----------------------------
# Run server
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5003)
