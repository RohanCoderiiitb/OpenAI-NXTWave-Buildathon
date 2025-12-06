# =============================================================================
# ONE-FILE RECIPE APP: Voice → Ingredients → Recipe → AI Image (Gemini Edition)
# pip install gradio google-generativeai pillow && python recipe_app_gemini.py
# =============================================================================
# =============================================================================
# ONE-FILE RECIPE APP: Voice → Ingredients → Recipe → AI Image (Gemini 3 + Nano Banana)
# Now loads API key from .env automatically
# =============================================================================

import os
from dotenv import load_dotenv  # ← ADD THIS

# Load .env from the current directory (where your .env file is)
load_dotenv()  # ← ADD THIS LINE

# Better error message if still missing
if not os.getenv("GEMINI_API_KEY"):
    raise ValueError(
        "\nGEMINI_API_KEY not found!\n"
        "Make sure you have a file named '.env' in the same folder as this script with:\n"
        "GEMINI_API_KEY=your_key_here  (no spaces, no quotes)\n"
    )

import gradio as gr
import json
import os
import google.generativeai as genai
from PIL import Image
import requests
from io import BytesIO

# ====================== CONFIGURATION ======================
if not os.getenv("GEMINI_API_KEY"):
    raise ValueError("Please set GEMINI_API_KEY environment variable")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Models
TRANSCRIPTION_MODEL = "gemini-3-pro-preview"
TEXT_MODEL = "gemini-3-pro-preview"           # Fast & great for text tasks
RECIPE_MODEL = "gemini-3-pro-preview"           # Better creativity for recipes
IMAGE_MODEL = "gemini-3-pro-image"            # Supports image generation

# Safety settings (allow food-related content)
safety_settings = [
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
]

# ====================== FUNCTIONS ======================
def transcribe_and_extract(audio, session):
    if session is None:
        session = {}
    if audio is None:
        return "No audio provided", gr.update(visible=False), session

    try:
        # Upload audio file to Gemini
        audio_file = genai.upload_file(path=audio, mime_type="audio/wav")
        model = genai.GenerativeModel(TRANSCRIPTION_MODEL)

        # Transcribe + extract ingredients in one shot
        prompt = """
        You are an expert chef assistant. Listen to the user's voice and:

        1. Transcribe exactly what they said.
        2. Detect the language (return 2-letter code).
        3. Extract ingredients they HAVE and DON'T HAVE.
        4. Return ONLY valid JSON in this format:

        {
          "language": "en|es|fr|de|...",
          "has": ["tomato", "rice", "chicken", ...],
          "not_has": ["cheese", "wine", ...],
          "clean_sentence": "Clean version of what user said"
        }

        Do not add any explanations.
        """

        response = model.generate_content(
            [audio_file, prompt],
            generation_config={"response_mime_type": "application/json"},
            safety_settings=safety_settings
        )

        data = json.loads(response.text)
        lang = data.get("language", "en")
        has = data.get("has", [])
        not_has = data.get("not_has", [])

        session["has"] = has
        session["not_has"] = not_has
        session["language"] = lang
        session["original_text"] = data.get("clean_sentence", "")

        result = f"*You said:* {data.get('clean_sentence', 'Could not parse')}\n\n"
        result += f"*Language:* {lang.upper()}\n\n"
        result += "✅ You HAVE:\n" + (", ".join(has) if has else "Nothing detected")
        result += "\n\n❌ You DON'T HAVE:\n" + (", ".join(not_has) if not_has else "None mentioned")

        return result, gr.update(choices=has, value=has, visible=True), session

    except Exception as e:
        return f"Error: {str(e)}", gr.update(visible=False), session
    finally:
        # Clean up uploaded file
        try:
            genai.delete_file(audio_file.name)
        except:
            pass


def suggest_dishes(session):
    if session is None:
        session = {}
    has = session.get("has", [])
    not_has = session.get("not_has", [])
    lang = session.get("language", "en")

    if not has:
        return gr.update(choices=[], value=None, label="Record ingredients first!"), session

    try:
        model = genai.GenerativeModel(TEXT_MODEL)
        prompt = f"""
        You are a creative chef. Suggest 5 appetizing dish names in {lang} language.
        Use ONLY ingredients from: {', '.join(has)}
        Avoid completely: {', '.join(not_has)}
        Number them 1–5. Make them sound delicious and realistic.
        """

        response = model.generate_content(prompt, safety_settings=safety_settings)
        lines = [line.strip() for line in response.text.split("\n") if line.strip() and any(c.isdigit() for c in line)]
        dishes = []
        for line in lines:
            # Remove numbering
            clean = line.split(".", 1)[-1].split(")", 1)[-1].strip(" -:")
            if clean:
                dishes.append(clean.strip())
        dishes = dishes[:5]

        return gr.update(choices=dishes, value=dishes[0] if dishes else None), session

    except Exception as e:
        return gr.update(choices=[], label=f"Error: {str(e)}"), session


def generate_recipe(selected_dish, session):
    if session is None:
        session = {}
    if not selected_dish:
        return "Please select a dish", session

    has = session.get("has", [])
    not_has = session.get("not_has", [])
    lang = session.get("language", "en")

    try:
        model = genai.GenerativeModel(RECIPE_MODEL)
        prompt = f"""
        Write a warm, encouraging, step-by-step recipe for "{selected_dish}" in {lang}.
        Use ONLY these ingredients: {', '.join(has)}
        NEVER use: {', '.join(not_has)}
        If impossible, say it's not possible and suggest alternatives.
        Include portions for 2 people.
        """

        response = model.generate_content(prompt, safety_settings=safety_settings)
        recipe = response.text
        session["current_dish"] = selected_dish
        return recipe, session

    except Exception as e:
        return f"Recipe error: {str(e)}", session


def generate_image(session):
    if session is None:
        session = {}
    current_dish = session.get("current_dish")

    if not current_dish:
        return None, "No dish selected. Generate recipe first!", session

    try:
        model = genai.GenerativeModel(IMAGE_MODEL)
        prompt = f"""
        A stunning, professional food photograph of {current_dish}.
        Gourmet restaurant style, perfect appetizing lighting, sharp 4K details,
        delicious presentation, depth of field, food magazine cover quality.
        """

        response = model.generate_content(
            [prompt],
            generation_config={"response_mime_type": "image/png"},
            safety_settings=safety_settings
        )

        # Gemini returns image in response.parts
        image_data = None
        for part in response.parts:
            if hasattr(part, 'inline_data'):
                image_data = part.inline_data.data
                break

        if not image_data:
            return None, "No image generated", session

        image = Image.open(BytesIO(image_data))
        return image, "", session

    except Exception as e:
        return None, f"Image error: {str(e)}", session


# ====================== GRADIO UI ======================
with gr.Blocks(title="What's in My Fridge? Gemini Chef") as demo:
    gr.Markdown("#  What's in My Fridge? Gemini Chef")
    gr.Markdown("Speak what you have in your fridge → Get recipes & stunning AI photos!")

    session_state = gr.State({})

    with gr.Row():
        audio_input = gr.Audio(
            label="Record or Upload Voice",
            type="filepath",
            sources=["microphone", "upload"]
        )

    transcribe_btn = gr.Button("Analyze Ingredients", variant="primary")
    output_text = gr.Markdown()

    with gr.Row():
        ingredients_list = gr.CheckboxGroup(label="You Have These", visible=False)

    gr.Markdown("###  Suggested Dishes")
    suggest_btn = gr.Button("Suggest Dishes")
    dish_dropdown = gr.Dropdown(label="Choose a dish", choices=[], interactive=True)

    recipe_btn = gr.Button("Get Full Recipe", variant="primary")
    recipe_output = gr.Markdown()

    with gr.Row():
        image_btn = gr.Button("Generate Photo of My Dish", variant="secondary")

    with gr.Row():
        image_output = gr.Image(label="Your Masterpiece")
        image_error = gr.Textbox(label="Status", interactive=False)

    # Connect buttons
    transcribe_btn.click(
        transcribe_and_extract,
        inputs=[audio_input, session_state],
        outputs=[output_text, ingredients_list, session_state]
    )

    suggest_btn.click(
        suggest_dishes,
        inputs=[session_state],
        outputs=[dish_dropdown, session_state]
    )

    recipe_btn.click(
        generate_recipe,
        inputs=[dish_dropdown, session_state],
        outputs=[recipe_output, session_state]
    )

    image_btn.click(
        generate_image,
        inputs=[session_state],
        outputs=[image_output, image_error, session_state]
    )

# ====================== LAUNCH ======================
if __name__ == "__main__":
    demo.launch(
        share=True,
        server_name="0.0.0.0",
        server_port=7860
    )