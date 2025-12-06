import os
import asyncio
import pygame
import requests
import google.generativeai as genai
import edge_tts
import sounddevice as sd
import soundfile as sf
import numpy as np

# --- 1. CONFIGURATION ---
# IMPORTANT: Paste your Google AI Studio Key below
API_KEY = "AIzaSyBNgX2-36Vg_9mEMYHv-9kdqtPghlLVKQg"  

# Configure Gemini
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-2.5-pro')


# Voice mapping for Indian languages (EdgeTTS)
VOICE_MAP = {
    "hi": "hi-IN-SwaraNeural",       # Hindi
    "te": "te-IN-MohanNeural",       # Telugu
    "ta": "ta-IN-PallaviNeural",     # Tamil
    "kn": "kn-IN-GaganNeural",       # Kannada
    "bn": "bn-IN-TanishaaNeural",    # Bengali
    "ml": "ml-IN-SobhanaNeural",     # Malayalam
    "en": "en-IN-NeerjaNeural"       # English (Indian Accent)
}

# --- 2. AUDIO RECORDING FUNCTION ---
def record_audio(filename, duration=5):
    """
    Records audio using Device 1 (MME) which you confirmed works.
    """
    print(f"\nRecording for {duration} seconds... (Speak Now!)")
    
    # Settings for Device 1
    fs = 44100  # Standard sample rate
    device_id = 1 
    
    try:
        # blocking=True ensures the script waits for you to finish speaking
        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, device=device_id, blocking=True)
        
        # Save to WAV file
        sf.write(filename, recording, fs)
        print(f"Recording saved to {filename}")
        
    except Exception as e:
        print(f"\nMicrophone Error: {e}")
        print("Check if Device 1 is still available.")

# --- 3. TEXT-TO-SPEECH FUNCTION ---
async def speak(text, lang_code):
    """
    Uses EdgeTTS to speak the text in the correct language.
    """
    print(f"\nAI Speaking ({lang_code}): {text}")
    
    # Pick the right voice, default to English if unknown
    voice = VOICE_MAP.get(lang_code, "en-IN-NeerjaNeural")
    output_file = "ai_response.mp3"
    
    # Generate Audio
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
    
    # Play Audio using Pygame
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.quit()
        
        # Delete file after playing to keep folder clean
        os.remove(output_file)
    except Exception as e:
        print(f"Audio Playback Error: {e}")

# --- 4. IMAGE GENERATION FUNCTION ---
def generate_image(prompt, filename="final_dish.jpg"):
    """
    Generates an image using Pollinations.ai (Free, Fast, No GPU needed).
    """
    print(f"\nGenerating Image...")
    # Clean prompt for URL
    safe_prompt = prompt.replace(" ", "%20")
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"Image saved to {filename}")
            # Open image automatically on Windows
            os.startfile(filename) 
        else:
            print("Image generation failed.")
    except Exception as e:
        print(f"Error generating image: {e}")

# --- 5. MAIN APPLICATION LOGIC ---
def main():
    print("SMART CHEF AI: Starting...")
    
    # --- STEP 1: RECORD INGREDIENTS ---
    ingredients_file = "ingredients.wav"
    input("\nPress Enter to RECORD INGREDIENTS (5 seconds)...")
    record_audio(ingredients_file, duration=5)

    print(f"Sending to Gemini Brain...")
    
    # Upload audio to Gemini
    myfile = genai.upload_file(ingredients_file)

    # Ask Gemini to identify language and suggest options
    prompt_1 = """
    Listen to this audio.
    1. Identify the Indian language spoken (return code: hi, te, ta, kn, etc).
    2. In that SAME language, suggest 2 distinct dishes based on these ingredients.
    3. Return ONLY this format:
       LANG: [code]
       OPTIONS: [Your question with options]
    """
    
    result_1 = model.generate_content([prompt_1, myfile])
    response_text = result_1.text.strip()
    
    # Parse the response
    lang_code = "en"
    ai_question = response_text
    
    # simple parsing
    for line in response_text.split("\n"):
        if "LANG:" in line:
            lang_code = line.split(":")[1].strip().lower()
        if "OPTIONS:" in line:
            ai_question = line.split(":")[1].strip()

    # AI Speaks the question
    asyncio.run(speak(ai_question, lang_code))

    # --- STEP 2: RECORD CHOICE ---
    choice_file = "choice.wav"
    input(f"\nPress Enter to RECORD YOUR CHOICE (3 seconds)...")
    record_audio(choice_file, duration=3)
    
    # Upload choice audio
    choice_upload = genai.upload_file(choice_file)

    # --- STEP 3: GENERATE RECIPE & IMAGE ---
    print("Cooking up your recipe...")
    
    prompt_2 = f"""
    The user chose a dish in this audio file.
    Language Code: {lang_code}
    1. Listen to the audio to identify the chosen dish.
    2. Provide a short 2-sentence recipe in {lang_code}.
    3. On a new line, write "IMG:" followed by the English name of the dish.
    """
    
    # We send the choice audio to Gemini
    result_2 = model.generate_content([prompt_2, choice_upload])
    final_text = result_2.text.strip()
    
    recipe_text = ""
    image_prompt = "Indian Food"

    # Separate recipe text from image prompt
    for line in final_text.split("\n"):
        if "IMG:" in line:
            image_prompt = line.replace("IMG:", "").strip()
        else:
            recipe_text += line + " "

    # 1. Generate Image
    generate_image(f"delicious {image_prompt}, professional food photography, 4k")
    
    # 2. Speak Recipe
    asyncio.run(speak(recipe_text, lang_code))
    
    print("\nBon Appétit!")

if __name__ == "__main__":
    main()