import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from werkzeug.utils import secure_filename


# ---------------------------------------------------
# 1. HealthReportAnalyzer CLASS
# ---------------------------------------------------
class HealthReportAnalyzer:
    def __init__(self, api_key, upload_folder="uploads"):
        self.client = OpenAI(api_key=api_key)
        self.upload_folder = upload_folder
        os.makedirs(upload_folder, exist_ok=True)
        self.allowed_extensions = {"png", "jpg", "jpeg", "pdf"}

    # ----------- File validation -----------
    def allowed_file(self, filename):
        return (
            "." in filename and
            filename.rsplit(".", 1)[1].lower() in self.allowed_extensions
        )

    # ----------- GPT-4o VISION ANALYSIS -----------
    def analyze(self, file_path):
        prompt = """
You are a medical report interpretation assistant (NOT a doctor).
Read the uploaded blood report and:

1. Extract important lab values.
2. Detect abnormalities (high/low).
3. Explain results in simple language.
4. Generate a 1-week personalized Indian diet plan.
5. Include a strong medical disclaimer.

Return ONLY JSON in this exact structure:

{
 "extracted_values": {},
 "abnormalities": {},
 "explanation": "",
 "diet_plan_1_week": {
     "day1": {"breakfast":"", "lunch":"", "dinner":"", "snacks":""},
     "day2": {},
     "day3": {},
     "day4": {},
     "day5": {},
     "day6": {},
     "day7": {}
 },
 "disclaimer": ""
}
"""

        input_file = self.client.files.create(
            file=open(file_path, "rb"),
            purpose="vision"
        )

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt},
                {
                    "role": "user",
                    "content": [{"type": "input_file", "input_file_id": input_file.id}]
                }
            ],
            response_format={"type": "json_object"}
        )

        return response.choices[0].message["content"]


# ---------------------------------------------------
# 2. FLASK APP SETUP
# ---------------------------------------------------
app = Flask(__name__)
CORS(app)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

analyzer = HealthReportAnalyzer(api_key=OPENAI_API_KEY)


# ---------------------------------------------------
# 3. ROUTE — UPLOAD + ANALYZE REPORT
# ---------------------------------------------------
@app.route("/analyze_health_report", methods=["POST"])
def analyze_report():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    if not analyzer.allowed_file(file.filename):
        return jsonify({"error": "Upload PNG/JPG/JPEG/PDF only"}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(analyzer.upload_folder, filename)
    file.save(file_path)

    try:
        result_json = analyzer.analyze(file_path)
        return jsonify({"success": True, "analysis": result_json})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------
# 4. RUN SERVER
# ---------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5001)
