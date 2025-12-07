import os
import sys
import asyncio
from uuid import uuid4
import pygame
import requests
import google.generativeai as genai
import edge_tts
import sounddevice as sd
import soundfile as sf
from google.api_core.exceptions import ResourceExhausted

BATCH_MODE = os.getenv("BATCH_MODE") == "1"

# ================== CONFIG ==================
API_KEY = "AIzaSyAKpTaEyiwC1lx3OeZskoUdyf3E7BSyQ1s"  # or read from .env
genai.configure(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash"          # text + files
model = genai.GenerativeModel(MODEL_NAME)

VOICE_MAP = {
    "hi": "hi-IN-SwaraNeural",
    "te": "te-IN-MohanNeural",
    "ta": "ta-IN-PallaviNeural",
    "kn": "kn-IN-GaganNeural",
    "bn": "bn-IN-TanishaaNeural",
    "ml": "ml-IN-SobhanaNeural",
    "en": "en-IN-NeerjaNeural",
}

# Check batch mode (backend-driven): if set, do NOT block for input() or try to play audio
BATCH_MODE = os.getenv("BATCH_MODE", "0") == "1"

# ================== AUDIO HELPERS ==================

def record_audio(filename, duration=10):
    """
    Records audio using the default input device.
    In BATCH_MODE we do not record from the server mic.
    """
    # if BATCH_MODE:
    #     print(f"[BATCH_MODE] Skipping server-side recording; expecting file '{filename}' to exist.")
    #     return

    if BATCH_MODE:
        print("[BATCH_MODE] Using provided ingredients.wav")
        return


    print(f"\nRecording for {duration} seconds... (Speak Now!)")

    fs = 44100
    device_id = None  # let sounddevice choose default mic

    try:
        recording = sd.rec(
            int(duration * fs),
            samplerate=fs,
            channels=1,
            device=device_id,
            blocking=True,
        )
        sf.write(filename, recording, fs)
        print(f"Recording saved to {filename}")

    except Exception as e:
        print(f"\nMicrophone Error: {e}")
        print("Check your audio input device (mic settings).")


# TTS counter and safe speak for batch mode
_tts_counter = 0
def _next_tts_filename():
    global _tts_counter
    _tts_counter += 1
    return f"ai_response_{_tts_counter}.mp3"

async def _save_tts_async(text, lang_code, filename):
    voice = VOICE_MAP.get(lang_code, "en-IN-NeerjaNeural")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filename)

def speak(text, lang_code):
    """
    In interactive desktop mode this played audio via pygame.
    In BATCH_MODE this saves TTS mp3 and prints a marker line so caller can fetch it.
    """
    if not text:
        return

    # Batch mode: save TTS to disk and print marker
    if BATCH_MODE:
        filename = f"tts_{uuid4().hex}.mp3"
        voice_name = VOICE_MAP.get(lang_code, "en-IN-NeerjaNeural")
        communicate = edge_tts.Communicate(text, voice_name)
        try:
            asyncio.run(communicate.save(filename))
            # Print a marker so the caller (routes.py) can find the file if needed
            print(f"TTS_FILE:{filename}")
        except Exception as e:
            print(f"[TTS ERROR] Could not save TTS file: {e}")
        return

    # Desktop / interactive mode: play via pygame
    print(f"\nAI Speaking ({lang_code}): {text}")

    voice = VOICE_MAP.get(lang_code, "en-IN-NeerjaNeural")
    output_file = "ai_response.mp3"

    communicate = edge_tts.Communicate(text, voice)
    asyncio.run(communicate.save(output_file))

    try:
        pygame.mixer.init()
        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.quit()
        os.remove(output_file)
    except Exception as e:
        print(f"Audio Playback Error: {e}")


def generate_image(prompt, filename="final_dish.jpg"):
    """
    Generate an image using Pollinations.ai and save locally.
    If BATCH_MODE, do not attempt to open the file.
    """
    print(f"\n[Pollinations] Generating image for: {prompt!r}")

    try:
        encoded_prompt = requests.utils.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

        r = requests.get(url, stream=True)
        if r.status_code != 200:
            print(f"[Pollinations] Failed with status {r.status_code}")
            return

        with open(filename, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)

        print(f"[Pollinations] Image saved to {filename}")

        if not BATCH_MODE:
            try:
                if sys.platform.startswith("win"):
                    os.startfile(filename)
                elif sys.platform.startswith("darwin"):
                    os.system(f'open "{filename}"')
                else:
                    os.system(f'xdg-open "{filename}"')
            except Exception as e:
                print("[Pollinations] Could not auto-open image:", e)

    except Exception as e:
        print("\n[Pollinations ERROR] Unexpected error while generating image.")
        print(type(e).__name__, ":", e)


# ================== GEMINI HELPERS ==================

def parse_lang_and_options(response_text):
    lang_code = "en"
    ai_question = response_text

    for line in response_text.split("\n"):
        if "LANG:" in line:
            lang_code = line.split(":", 1)[1].strip().lower()
        if "OPTIONS:" in line:
            ai_question = line.split(":", 1)[1].strip()

    return lang_code, ai_question


def parse_dish_block(final_text):
    dish_name = ""
    ingredients_text = ""
    question_text = ""
    base_recipe_text = ""
    image_prompt = "Indian food"

    for line in final_text.split("\n"):
        line = line.strip()
        if line.startswith("DISH:"):
            dish_name = line.split(":", 1)[1].strip()
        elif line.startswith("INGREDIENTS:"):
            ingredients_text = line.split(":", 1)[1].strip()
        elif line.startswith("QUESTION:"):
            question_text = line.split(":", 1)[1].strip()
        elif line.startswith("RECIPE:"):
            base_recipe_text = line.split(":", 1)[1].strip()
        elif line.startswith("IMG:"):
            image_prompt = line.split(":", 1)[1].strip()

    return dish_name, ingredients_text, question_text, base_recipe_text, image_prompt


def parse_steps(steps_text):
    """
    Parses lines like:
      STEP 1: ...
      STEP 2: ...
    into a Python list of step strings.
    """
    steps = []
    for line in steps_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("step"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                steps.append(parts[1].strip())
            else:
                # if it's like "STEP 1 - Do X"
                parts = line.split("-", 1)
                if len(parts) == 2:
                    steps.append(parts[1].strip())
    return steps


def get_user_step_command(lang_code, step_index):
    """
    Records the user's voice command for the current step,
    asks Gemini to interpret it as NEXT / REPEAT / STOP.

    In BATCH_MODE we expect a pre-existing step_command_{step_index}.wav file provided by the caller.
    """
    cmd_file = f"step_command_{step_index}.wav"

    if BATCH_MODE:
        print(f"[BATCH_MODE] Using pre-supplied step file: {cmd_file}")
    else:
        input("\nPress Enter and then SAY 'next', 'repeat', or 'stop' (in your language)...")
        record_audio(cmd_file, duration=5)

    # Upload audio to Gemini and ask for NEXT/REPEAT/STOP
    try:
        cmd_upload = genai.upload_file(cmd_file)
    except Exception as e:
        print(f"[ERROR] Could not upload step command file {cmd_file}: {e}")
        return "NEXT"

    prompt_cmd = f"""
    You are a controller for a cooking assistant.

    Language code: {lang_code}.
    Listen to this audio. The user will say something like "next", "repeat",
    "again", "once more", "stop", "finish", or similar, possibly in language {lang_code}.

    Your job: Map their intent to exactly one of these commands:
    NEXT, REPEAT, STOP

    Rules:
    - If they want to go to the next step, answer: NEXT
    - If they want you to repeat the current step, answer: REPEAT
    - If they want to finish or stop, answer: STOP

    Respond with ONLY ONE WORD in UPPERCASE: NEXT or REPEAT or STOP.
    Do NOT include any other text.
    """

    try:
        result_cmd = model.generate_content([prompt_cmd, cmd_upload])
    except Exception as e:
        print(f"[ERROR] Gemini step command failed: {e}")
        return "NEXT"

    command_raw = result_cmd.text.strip().upper()
    print(f"\n--- Gemini Step Command Raw ---\n{command_raw}\n")

    if "REPEAT" in command_raw:
        return "REPEAT"
    if "STOP" in command_raw:
        return "STOP"
    # default fallback
    return "NEXT"


# ================== MAIN FLOW ==================

def main():
    print("SMART CHEF AI: Starting... (Gemini brain + Pollinations images)")

    # --- STEP 1: USER SPEAKS INGREDIENTS ---
    ingredients_file = "ingredients.wav"
    if not BATCH_MODE:
        input("\nPress Enter to RECORD INGREDIENTS (5 seconds)...")
        record_audio(ingredients_file, duration=5)
    else:
        print(f"[BATCH_MODE] Expecting file '{ingredients_file}' to have been provided by caller.")

    print("Sending ingredients audio to Gemini...")
    try:
        myfile = genai.upload_file(ingredients_file)
    except Exception as e:
        print(f"[ERROR] Upload ingredients file failed: {e}")
        return

    prompt_1 = """
    Listen to this audio.
    1. Identify the Indian language spoken (return code: hi, te, ta, kn, bn, ml, en).
    2. In that SAME language, suggest 2 distinct dishes based on these ingredients.
    3. Return ONLY this format:
       LANG: [code]
       OPTIONS: [Your question with the two dish options, asking the user to choose one]
    """
    try:
        result_1 = model.generate_content([prompt_1, myfile])
    except ResourceExhausted as e:
        print("\n[ERROR] Gemini free-tier quota for this model is exhausted.")
        print("Details:", e)
        print("\nTo continue, you must either:")
        print("  • wait until your daily free quota resets, or")
        print("  • create a new API key (new project) or switch to a paid plan.")
        return

    response_text = result_1.text.strip()

    print("\n--- Gemini Response 1 ---")
    print(response_text)

    lang_code, ai_question = parse_lang_and_options(response_text)

    # Ask the user (voice) to choose a dish
    speak(ai_question, lang_code)

    # --- STEP 2: USER SPEAKS CHOICE OF DISH ---
    choice_file = "choice.wav"
    if not BATCH_MODE:
        input("\nPress Enter to RECORD YOUR CHOICE (up to 10 seconds)...")
        record_audio(choice_file, duration=10)
    else:
        print(f"[BATCH_MODE] Expecting file '{choice_file}' if required.")

    try:
        choice_upload = genai.upload_file(choice_file)
    except Exception as e:
        print(f"[ERROR] Upload choice file failed: {e}")
        choice_upload = None

    print("Understanding your chosen dish and preparing base recipe...")

    prompt_2 = f"""
    The user chose a dish in this audio file.
    Language Code: {lang_code}

    Your tasks:
    1. Listen to the audio to identify which dish (from your earlier two options) the user selected.
    2. In the SAME language ({lang_code}), respond in EXACTLY this format:
       DISH: [name of the chosen dish in {lang_code}]
       INGREDIENTS: [a clear comma-separated list of ingredients in {lang_code}]
       QUESTION: [politely ask the user if they have all these ingredients; tell them to say which are missing, or say 'yes' if everything is available]
       RECIPE: [2 short sentences describing how to cook it in {lang_code}]
       IMG: [English name of the dish]

    Important:
    - Do NOT add any extra lines or text outside this format.
    """

    try:
        if choice_upload:
            result_2 = model.generate_content([prompt_2, choice_upload])
        else:
            # If no choice audio was provided, ask Gemini to pick the first option from previous response_text
            fallback_prompt = f"""
            Based on these options (from user audio): {response_text}
            Choose the first dish and respond in the required DISH/INGREDIENTS/QUESTION/RECIPE/IMG format.
            """
            result_2 = model.generate_content(fallback_prompt)
    except Exception as e:
        print(f"[ERROR] Gemini generation for choice failed: {e}")
        return

    final_text = result_2.text.strip()
    print("\n--- Gemini Response 2 ---")
    print(final_text)

    dish_name, ingredients_text, question_text, base_recipe_text, image_prompt = parse_dish_block(
        final_text
    )

    # Generate image for the chosen dish (using English name from IMG) via Pollinations
    generate_image(f"delicious {image_prompt}, professional food photography, 4k")

    # --- STEP 3: ASK USER IF THEY HAVE ALL INGREDIENTS ---
    ingredients_prompt_for_user = f"{dish_name}. {ingredients_text}. {question_text}"
    speak(ingredients_prompt_for_user, lang_code)

    ingredients_reply_file = "ingredients_reply.wav"
    if not BATCH_MODE:
        input(
            "\nPress Enter to RECORD YOUR INGREDIENTS AVAILABILITY "
            "(say which items you don't have, or say you have all) (up to 10 seconds)..."
        )
        record_audio(ingredients_reply_file, duration=10)
    else:
        print(f"[BATCH_MODE] Expecting file '{ingredients_reply_file}' if available.")

    try:
        ingredients_reply_upload = genai.upload_file(ingredients_reply_file)
    except Exception as e:
        print(f"[ERROR] Upload ingredients reply file failed: {e}")
        ingredients_reply_upload = None

    print("Adjusting recipe based on your available ingredients...")

    # --- STEP 4: FINAL RECIPE ADJUSTMENT / ALTERNATIVE ---
    prompt_3 = f"""
    You are a helpful cooking assistant.

    Language Code: {lang_code}
    The chosen dish is: {dish_name}

    Here is the original ingredient list (in {lang_code}):
    {ingredients_text}

    Here is a short base recipe (in {lang_code}):
    {base_recipe_text}

    Now listen to this new audio from the user. They will either:
    - Say they have all the ingredients, or
    - Say they are missing some ingredients (they may name them).

    Your tasks:
    1. Listen to the audio and understand whether:
       - The user has all ingredients, OR
       - Some ingredients are missing and which ones.
    2. If the user has all ingredients:
       - Keep the same dish and provide a clear final recipe in {lang_code},
         3–5 sentences, step-by-step.
    3. If the user is missing some ingredients:
       - Decide if the same dish can still be made without those ingredients.
         If YES: adjust the recipe accordingly and clearly mention any substitutions or skips.
         If NO: suggest a simple alternative dish that can be made from the ingredients they likely have,
         and give a 3–5 sentence recipe for that alternative.
    4. IMPORTANT: Respond ONLY with the final recipe text in {lang_code}.
       Do NOT include labels like DISH:, INGREDIENTS:, IMG:, or any English explanations.
    """

    try:
        if ingredients_reply_upload:
            result_3 = model.generate_content([prompt_3, ingredients_reply_upload])
        else:
            # If no ingredients reply audio, ask the model to assume user has all ingredients
            fallback_prompt_3 = f"""
            Assume the user has all ingredients: {ingredients_text}
            Provide the final recipe in {lang_code}, 3-5 sentences.
            """
            result_3 = model.generate_content(fallback_prompt_3)
    except Exception as e:
        print(f"[ERROR] Gemini final recipe generation failed: {e}")
        return

    final_recipe_text = result_3.text.strip()
    print("\n--- Gemini Response 3 (Final Recipe) ---")
    print(final_recipe_text)

    # --- STEP 5: READ OUT SHORT FINAL RECIPE ---
    speak(final_recipe_text, lang_code)

    # --- STEP 6: ASK GEMINI TO BREAK RECIPE INTO STEP-BY-STEP FORMAT ---
    print("\nAsking Gemini to convert recipe into step-by-step instructions...")

    prompt_steps = f"""
    Language code: {lang_code}

    Here is the final recipe text in {lang_code}:
    \"\"\"{final_recipe_text}\"\"\"


    Convert this into a clear numbered sequence of short steps in {lang_code}.
    Respond in EXACTLY this format:
    STEP 1: ...
    STEP 2: ...
    STEP 3: ...
    (and so on)

    Do NOT add any introduction or conclusion.
    Do NOT add any text that does not start with 'STEP'.
    """

    try:
        result_steps = model.generate_content(prompt_steps)
    except Exception as e:
        print(f"[ERROR] Gemini step conversion failed: {e}")
        return

    steps_text = result_steps.text.strip()
    print("\n--- Gemini Step List ---")
    print(steps_text)

    steps = parse_steps(steps_text)

    if not steps:
        print("\nCould not parse steps. Using full recipe only.")
        return

    # Optional: brief intro to step-by-step mode
    intro_prompt = f"""
    Language code: {lang_code}.
    Write one short sentence in this language telling the user:
    'Now we will go through the recipe step by step. After each step, say NEXT to continue, REPEAT to hear it again, or STOP to finish.' 
    Respond only with that sentence, in {lang_code}.
    """
    intro_result = model.generate_content(intro_prompt)
    intro_text = intro_result.text.strip()
    speak(intro_text, lang_code)

    # --- STEP 7: INTERACTIVE STEP-BY-STEP COOKING MODE ---
    print("\nEntering interactive step-by-step mode...")

    step_index = 0
    while step_index < len(steps):
        current_step = steps[step_index]
        print(f"\nSTEP {step_index + 1}: {current_step}")
        speak(f"Step {step_index + 1}: {current_step}", lang_code)

        # get_user_step_command will, in BATCH_MODE, attempt to use pre-supplied step_command_{i}.wav files
        command = get_user_step_command(lang_code, step_index + 1)
        print(f"Interpreted command: {command}")

        if command == "NEXT":
            step_index += 1
        elif command == "REPEAT":
            # Just loop again with the same step_index
            continue
        elif command == "STOP":
            print("\nUser stopped the recipe.")
            break
        else:
            # Fallback: go to next
            step_index += 1

    print("\nCooking assistant finished. Bon Appétit!")


def process_ingredients_batch(ingredients_wav_path="ingredients.wav"):
    """
    Non-interactive helper for the web backend:
    - uploads `ingredients_wav_path` to Gemini
    - runs the first prompt (language detection + two dish options)
    - generates a TTS mp3 for the AI question and returns filenames
    Returns a dict:
      {
        "success": True|False,
        "error": "...",
        "response_text": "...",      # Gemini textual output
        "lang_code": "...",
        "ai_question": "...",
        "tts_files": ["tts_xxx.mp3", ...]
      }
    """
    result = {"success": False, "error": None, "response_text": "", "lang_code": "en", "ai_question": "", "tts_files": []}

    # Ensure the WAV file exists
    if not os.path.exists(ingredients_wav_path):
        result["error"] = f"Ingredients file not found: {ingredients_wav_path}"
        return result

    # Upload WAV to Gemini
    try:
        myfile = genai.upload_file(ingredients_wav_path)
    except Exception as e:
        result["error"] = f"Upload ingredients file failed: {e}"
        return result

    prompt_1 = """
    Listen to this audio.
    1. Identify the Indian language spoken (return code: hi, te, ta, kn, bn, ml, en).
    2. In that SAME language, suggest 2 distinct dishes based on these ingredients.
    3. Return ONLY this format:
       LANG: [code]
       OPTIONS: [Your question with the two dish options, asking the user to choose one]
    """

    # Call the model
    try:
        gen_result = model.generate_content([prompt_1, myfile])
    except ResourceExhausted as e:
        result["error"] = "Gemini quota exhausted: " + str(e)
        return result
    except Exception as e:
        result["error"] = "Gemini generation failed: " + str(e)
        return result

    response_text = (getattr(gen_result, "text", "") or "").strip()
    result["response_text"] = response_text

    # Parse language and the AI question/options
    lang_code, ai_question = parse_lang_and_options(response_text)
    result["lang_code"] = lang_code
    result["ai_question"] = ai_question

    # Generate TTS for the ai_question (batch mode)
    if ai_question:
        tts_filename = f"tts_{uuid4().hex}.mp3"
        voice_name = VOICE_MAP.get(lang_code, "en-IN-NeerjaNeural")
        try:
            communicate = edge_tts.Communicate(ai_question, voice_name)
            asyncio.run(communicate.save(tts_filename))
            result["tts_files"].append(tts_filename)
        except Exception as e:
            # Don't fail the whole request if TTS fails, but record the error
            result.setdefault("tts_error", str(e))

    result["success"] = True
    return result


if __name__ == "__main__":
    main()
