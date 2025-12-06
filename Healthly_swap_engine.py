
import os
from openai import OpenAI

# Initialize client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are a Health & Nutrition Assistant specialized in INDIAN food and diet.

User will give you a CRAVING (e.g., "pizza", "chocolate cake", "burger", "butter chicken with naan").

Your job is to respond in clean, structured JSON with four fields:
1. why_unhealthy  – short, clear explanation of why the original craving is unhealthy (for frequent / large consumption).
2. healthy_indian_swap – a practical Indian alternative that:
   - is healthier
   - still feels satisfying and tasty
   - uses ingredients that are commonly available in Indian households.
3. nutritional_comparison – bullet-style comparison between original and swap:
   - calories
   - fats
   - sugar
   - protein
   (Approximate values with clear language like "roughly", "about".)
4. why_it_wins – persuasive explanation in simple language why this swap is a win
   (health + taste + practicality).

Important:
- Keep the answer SHORT and ACTIONABLE.
- Focus on realistic, homemade or easy-to-find Indian options.
- Return ONLY valid JSON. No backticks, no extra text.
- JSON KEYS must be: why_unhealthy, healthy_indian_swap, nutritional_comparison, why_it_wins.
"""

def generate_healthy_swap(craving: str) -> dict:
    """
    Given a craving (string), call GPT and return a dict with:
      - why_unhealthy
      - healthy_indian_swap
      - nutritional_comparison
      - why_it_wins
    """
    response = client.responses.create(
        model="gpt-5.1-mini",  # or "gpt-5.1" depending on your plan
        input=f"Craving: {craving}\nGenerate the four fields as described.",
        # We ask for JSON mode to make parsing easy:
        response_format={"type": "json_object"}
    )

    # The model’s main text output is in response.output[0].content[0].text
    output_text = response.output[0].content[0].text

    import json
    try:
        data = json.loads(output_text)
    except json.JSONDecodeError:
        # Fallback: wrap in a safe structure
        data = {
            "why_unhealthy": "Sorry, could not parse model output.",
            "healthy_indian_swap": "",
            "nutritional_comparison": "",
            "why_it_wins": ""
        }

    return data


if __name__ == "__main__":
    # Example usage
    user_craving = input("What are you craving? ")
    result = generate_healthy_swap(user_craving)

    print("\n=== Healthy Swaps Engine Result ===")
    print(f"Craving: {user_craving}")
    print("\nWhy it’s unhealthy:")
    print(result.get("why_unhealthy", ""))

    print("\nHealthy Indian swap:")
    print(result.get("healthy_indian_swap", ""))

    print("\nNutritional comparison:")
    print(result.get("nutritional_comparison", ""))

    print("\nWhy it wins:")
    print(result.get("why_it_wins", ""))
