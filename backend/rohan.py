import os
import asyncio
import json
import re
import pygame
import requests
import google.generativeai as genai
import edge_tts
import sounddevice as sd
import soundfile as sf
import numpy as np

# --- CONFIGURATION ---
API_KEY = "AIzaSyBNgX2-36Vg_9mEMYHv-9kdqtPghlLVKQg"  # <--- PASTE YOUR KEY HERE
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-2.5-pro')

# --- HELPER: JSON PARSER ---
def extract_json(text):
    """Cleanly extracts JSON from AI response."""
    try:
        # Remove markdown code blocks if present
        text = re.sub(r"```json", "", text)
        text = re.sub(r"```", "", text)
        # Find the first { and last }
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != -1:
            json_str = text[start:end]
            return json.loads(json_str)
        return None
    except Exception as e:
        print(f"JSON Parse Error: {e}")
        return None

# --- AUDIO & TTS ---
def record_audio(filename, duration=10):
    print(f"\n🎤 Recording for {duration} seconds... (Speak Now!)")
    fs = 44100
    device_id = 1 # Using Device 1 (MME)
    try:
        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, device=device_id, blocking=True)
        sf.write(filename, recording, fs)
    except Exception as e:
        print(f"Mic Error: {e}")

async def speak(text, lang_code):
    """Speaks text using EdgeTTS."""
    print(f"\n🔊 AI Speaking ({lang_code})...")
    
    VOICE_MAP = {
        "hi": "hi-IN-SwaraNeural", "te": "te-IN-MohanNeural", 
        "ta": "ta-IN-PallaviNeural", "kn": "kn-IN-GaganNeural",
        "bn": "bn-IN-TanishaaNeural", "en": "en-IN-NeerjaNeural"
    }
    voice = VOICE_MAP.get(lang_code, "en-IN-NeerjaNeural")
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save("ai_resp.mp3")
        
        pygame.mixer.init()
        pygame.mixer.music.load("ai_resp.mp3")
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.quit()
        os.remove("ai_resp.mp3")
    except Exception as e:
        print(f"Audio Error: {e}")

def generate_image(prompt, filename="final_dish.jpg"):
    print(f"\n🎨 Generating Image...")
    safe_prompt = prompt.replace(" ", "%20")
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"Image saved to {filename}")
            try: os.startfile(filename)
            except: pass
    except Exception:
        pass

# --- MAIN LOGIC ---
def main():
    print("👨‍🍳 SMART CHEF AI: Starting...")
    
    # --- STEP 1: RECORD INGREDIENTS ---
    ingredients_file = "ingredients.wav"
    input("\n🔴 Press Enter to RECORD INGREDIENTS (5 seconds)...")
    record_audio(ingredients_file, duration=10)

    print(f"🚀 Sending to Gemini...")
    myfile = genai.upload_file(ingredients_file)

    # Prompt 1: Identify Lang & Suggest Options
    prompt_1 = """
    Listen to this audio.
    1. Identify the Indian language (return code: hi, te, ta, kn, etc).
    2. Suggest 2 distinct dishes based on ingredients in that language.
    3. Return JSON: {"lang": "code", "question": "Question text in native language"}
    """
    
    result_1 = model.generate_content([prompt_1, myfile])
    data_1 = extract_json(result_1.text)
    
    if not data_1:
        print("Error parsing Gemini response.")
        return

    lang_code = data_1.get("lang", "en")
    ai_question = data_1.get("question", "What would you like to make?")
    
    asyncio.run(speak(ai_question, lang_code))

    # --- STEP 2: RECORD CHOICE ---
    choice_file = "choice.wav"
    input(f"\n🔴 Press Enter to RECORD YOUR CHOICE (4 seconds)...")
    record_audio(choice_file, duration=10)
    choice_upload = genai.upload_file(choice_file)

    # --- STEP 3: GENERATE FULL RECIPE (WITH INGREDIENTS LIST) ---
    print("🍳 Cooking up your recipe...")
    
    prompt_2 = f"""
    The user chose a dish (listen to audio). Language: {lang_code}.
    Create a recipe. Return a JSON object with this EXACT structure:
    {{
        "dish_name_english": "Name in English",
        "ingredients_native": ["Item 1", "Item 2"],
        "ingredients_english": ["Item 1", "Item 2"],
        "steps_native": "Step 1... Step 2...",
        "steps_english": "Step 1... Step 2..."
    }}
    """
    
    result_2 = model.generate_content([prompt_2, choice_upload])
    recipe_data = extract_json(result_2.text)
    
    if not recipe_data:
        print("Error generating recipe.")
        return

    # Extract Data
    dish_name = recipe_data.get("dish_name_english", "Indian Dish")
    ing_native = recipe_data.get("ingredients_native", [])
    ing_english = recipe_data.get("ingredients_english", [])
    steps_native = recipe_data.get("steps_native", "")
    steps_english = recipe_data.get("steps_english", "")

    # Display Image
    generate_image(f"delicious {dish_name}, professional food photography, 4k")

    # DISPLAY RECIPE ON SCREEN
    print("\n" + "="*50)
    print(f"🍲 DISH: {dish_name.upper()}")
    print("-" * 20)
    print(f"🛒 INGREDIENTS ({lang_code.upper()}):")
    for item in ing_native: print(f" - {item}")
    print(f"\n🛒 INGREDIENTS (ENGLISH):")
    for item in ing_english: print(f" - {item}")
    print("-" * 20)
    print(f"📜 STEPS ({lang_code.upper()}):\n{steps_native}")
    print(f"\n📜 STEPS (ENGLISH):\n{steps_english}")
    print("="*50 + "\n")

    # SPEAK RECIPE
    asyncio.run(speak(f"Here is the recipe for {dish_name}. {steps_native}", lang_code))

    # --- STEP 4: CHECK MISSING INGREDIENTS ---
    print("\n❓ Do you have all these ingredients?")
    # Ask the user if they have everything
    check_question = "Do you have all these ingredients? Tell me if anything is missing."
    asyncio.run(speak(check_question, "en")) # Asking in English/Native context usually implies mixed mode

    missing_file = "missing.wav"
    input(f"\n🔴 Press Enter to REPLY (Yes/No/Missing items)...")
    record_audio(missing_file, duration=5)
    missing_upload = genai.upload_file(missing_file)

    # Robust Logic Prompt
    prompt_3 = f"""
    Context: User was shown a recipe for {dish_name}.
    Listen to user audio. Language: {lang_code}.
    Determine intent:
    - 'proceed': User has everything / says yes.
    - 'modify': User lacks optional items (e.g. coriander). Remove them.
    - 'pivot': User lacks main items (e.g. rice). Suggest NEW dish.
    
    Return JSON:
    {{
        "intent": "proceed" | "modify" | "pivot",
        "reason": "English explanation",
        "new_recipe_native": "Full new text or null",
        "new_recipe_english": "Full new text or null"
    }}
    """
    
    print("🧠 Checking logic...")
    result_3 = model.generate_content([prompt_3, missing_upload])
    check_data = extract_json(result_3.text)
    
    if check_data:
        intent = check_data.get("intent", "proceed")
        print(f"\n🔍 Status: {intent.upper()} ({check_data.get('reason')})")

        if intent == "proceed":
            print("\n✅ Perfect! Enjoy cooking.")
            asyncio.run(speak("Great! Enjoy your meal.", lang_code))
        else:
            # Handle Modify or Pivot
            new_native = check_data.get("new_recipe_native", "")
            new_english = check_data.get("new_recipe_english", "")
            
            print("\n" + "="*50)
            print(f"🔄 UPDATED RECIPE ({lang_code.upper()}):\n{new_native}")
            print(f"🔄 UPDATED RECIPE (ENGLISH):\n{new_english}")
            print("="*50 + "\n")
            
            asyncio.run(speak(new_native, lang_code))

if __name__ == "__main__":
    main()