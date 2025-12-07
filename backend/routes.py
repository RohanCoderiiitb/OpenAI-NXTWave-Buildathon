from fastapi import APIRouter, UploadFile, File
import os, base64
import ffmpeg

# Import the new helper
import recipe_generator as rg

router = APIRouter()

def convert_webm_to_wav(webm_path, wav_path):
    try:
        (
            ffmpeg
            .input(webm_path)
            .output(wav_path, acodec='pcm_s16le', ac=1, ar='44100')
            .overwrite_output()
            .run(quiet=True)
        )
        print("Converted to WAV:", wav_path)
    except Exception as e:
        print("FFmpeg error:", e)

@router.post("/run-recipe-generator")
async def run_recipe(ingredients: UploadFile = File(...)):

    # Save webm from frontend
    with open("ingredients.webm", "wb") as f:
        f.write(await ingredients.read())

    # Convert → WAV
    convert_webm_to_wav("ingredients.webm", "ingredients.wav")

    # Ensure WAV exists
    if not os.path.exists("ingredients.wav"):
        return {"success": False, "error": "Conversion failed: ingredients.wav not found", "stdout": "", "stderr": ""}

    # Call the recipe generator helper directly (non-blocking for interactive inputs)
    result = rg.process_ingredients_batch("ingredients.wav")

    stdout = result.get("response_text", "")
    stderr = result.get("error", "")

    # Collect TTS files and encode
    tts_files = []
    for fname in result.get("tts_files", []):
        if os.path.exists(fname):
            with open(fname, "rb") as f:
                tts_files.append({
                    "filename": fname,
                    "base64": base64.b64encode(f.read()).decode()
                })

    return {
        "success": result.get("success", False),
        "stdout": stdout,
        "stderr": stderr,
        "tts": tts_files
    }
