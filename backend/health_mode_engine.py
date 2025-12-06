
import os
from dataclasses import dataclass
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI



load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SUPPORTED_CONDITIONS = [
    "Diabetes",
    "Thyroid",
    "Cholesterol",
    "PCOS",
    "Weight loss"
]

INDIAN_CONTEXT_HINT = (
    "Assume user is from India. Prefer Indian foods, ingredients, and cooking methods "
    "(idlis, dosas, upma, dal, sabzi, roti, poha, etc.). "
)

SYSTEM_PROMPT = f"""
You are a careful, practical Indian nutrition assistant and diet coach.

{INDIAN_CONTEXT_HINT}

You *must* adapt advice to the user's selected health condition:
- Diabetes
- Thyroid
- Cholesterol
- PCOS
- Weight loss

For **each response**, always return a **structured JSON** with these keys:

- "condition": string  // one of the 5 modes
- "summary": string    // 2-4 line overview tailored to the condition
- "recipe": {{
    "title": string,
    "servings": int,
    "ingredients": [string],
    "instructions": [string]
  }}
- "ingredient_swaps": {{
    "explanation": string,
    "swaps": [string]   // bullet-style text like "Replace white rice → brown rice"
  }}
- "diet_plan": {{
    "day": "Sample Day 1",
    "meals": {{
        "breakfast": [string],
        "mid_morning": [string],
        "lunch": [string],
        "evening_snack": [string],
        "dinner": [string]
    }}
  }}
- "warnings": {{
    "red_flags": [string],
    "notes": [string]
  }}

Rules:
- Use **simple, non-technical language** a normal person can understand.
- Mention **portion control** and **balanced plate** where relevant.
- For Diabetes: stress low GI, fibre, avoiding sugar spikes.
- For Thyroid: mention iodine, selenium, soy and goitrogenic foods carefully.
- For Cholesterol: focus on healthy fats, fibre, low fried foods and trans fats.
- For PCOS: focus on insulin sensitivity, high protein, low refined carbs.
- For Weight loss: focus on calorie deficit, high protein, high fibre, sustainable habits.
- Never give extreme, risky or crash-diet advice.
- If user gives obviously unsafe behaviour, gently warn and suggest consulting a doctor.

Return **only JSON**, no extra text, no markdown.
"""

@dataclass
class HealthModeRequest:
    condition: str
    user_input: str


# =============================
# Core OpenAI call
# =============================

def generate_health_plan(req: HealthModeRequest) -> Dict[str, Any]:
    """
    Calls the OpenAI API with the selected condition + user input.
    Returns a parsed Python dict (from JSON).
    """
    user_prompt = f"""
User health condition (mode): {req.condition}

User text (ingredients / craving / dish / notes):
\"\"\"{req.user_input}\"\"\".

Task:
Using the JSON format described in the system prompt, generate:
- A condition-safe recipe (Indian style if possible),
- Ingredient swaps,
- A 1-day sample diet plan,
- Food warnings / red flags.
"""
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        response_format={"type": "json_object"},
    )

    # The Responses API returns content in 'output[0].content[0].text' style;
    # but we use the higher-level field:
    content_text = response.output[0].content[0].text
    import json
    data = json.loads(content_text)
    return data


# =============================
# Pretty printing helpers
# =============================

def print_section(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70 + "\n")


def print_health_response(data: Dict[str, Any]):
    print_section(f"Mode: {data.get('condition', 'Unknown')}")

    # Summary
    print("🔍 Overview:")
    print(data.get("summary", "").strip())
    print()

    # Recipe
    recipe = data.get("recipe", {})
    print_section("🍲 Condition-Friendly Recipe")
    print(f"Title: {recipe.get('title', 'N/A')}")
    print(f"Servings: {recipe.get('servings', 'N/A')}\n")

    print("Ingredients:")
    for ing in recipe.get("ingredients", []):
        print(f"  - {ing}")
    print("\nInstructions:")
    for step_no, step in enumerate(recipe.get("instructions", []), start=1):
        print(f"  {step_no}. {step}")

    # Ingredient swaps
    swaps = data.get("ingredient_swaps", {})
    print_section("♻ Ingredient Swaps")
    print(swaps.get("explanation", "").strip())
    print()
    for s in swaps.get("swaps", []):
        print(f"  - {s}")

    # Diet plan
    diet = data.get("diet_plan", {})
    print_section(f"🗓 {diet.get('day', 'Sample Day')}: Diet Plan")
    meals = diet.get("meals", {})
    for meal_name in ["breakfast", "mid_morning", "lunch", "evening_snack", "dinner"]:
        items = meals.get(meal_name, [])
        if not items:
            continue
        pretty_name = meal_name.replace("_", " ").title()
        print(f"{pretty_name}:")
        for item in items:
            print(f"  - {item}")
        print()

    # Warnings
    warnings = data.get("warnings", {})
    print_section("⚠ Warnings & Notes")

    if warnings.get("red_flags"):
        print("Red Flags:")
        for rf in warnings["red_flags"]:
            print(f"  - {rf}")
        print()

    if warnings.get("notes"):
        print("Notes:")
        for n in warnings["notes"]:
            print(f"  - {n}")
        print()


# =============================
# Simple CLI
# =============================

def choose_condition() -> str:
    print("Select a health mode:\n")
    for idx, cond in enumerate(SUPPORTED_CONDITIONS, start=1):
        print(f"{idx}. {cond}")
    print()

    while True:
        choice = input("Enter choice (1-5): ").strip()
        if not choice.isdigit():
            print("Please enter a number from 1 to 5.")
            continue
        idx = int(choice)
        if 1 <= idx <= len(SUPPORTED_CONDITIONS):
            return SUPPORTED_CONDITIONS[idx - 1]
        else:
            print("Invalid choice. Try again.")


def main():
    print("=== Health-Aware Recipe & Diet Engine (India-Focused) ===\n")

    condition = choose_condition()
    print(f"\nYou selected: {condition}\n")

    print("Now describe what you want help with.")
    print("Examples:")
    print("  - \"I have white rice, potatoes and paneer\"")
    print("  - \"I crave samosa and gulab jamun\"")
    print("  - \"Give me a South Indian style breakfast idea\"")
    user_input = input("\nType your ingredients / craving / dish: ").strip()

    req = HealthModeRequest(condition=condition, user_input=user_input)
    print("\nThinking with AI... (this may take a few seconds)\n")

    try:
        data = generate_health_plan(req)
        print_health_response(data)
    except Exception as e:
        print("❌ Error while contacting AI or parsing response:")
        print(e)


if __name__ == "__main__":
    main()
