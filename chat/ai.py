import json
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(): pass

load_dotenv()

try:
    from openai import OpenAI
    import os
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        o = OpenAI(api_key=api_key)
    else:
        o = None
except ImportError:
    OpenAI = None
    o = None
except Exception as e:
    print(f"Error initializing OpenAI client: {e}")
    o = None

from shop.models import Product
from .models import ChatMessage


def get_ai_reply(current_query, user=None):
    try:
        # 1. Fetch Products
        products = Product.objects.all()
        product_catalog = ""
        for p in products:
            product_catalog += f"- {p.name}: ${p.discounted_price} (Category: {p.category})\n"

        # 2. Fetch History (if user is provided)
        conversation_history = ""
        if user:
            last_messages = ChatMessage.objects.filter(user=user).order_by('-created_at')[:5]
            # Reverse to chronological order
            last_messages = reversed(last_messages)
            for m in last_messages:
                conversation_history += f"{m.sender_name}: {m.message}\n"

        system_message = {
            "role": "system",
            "content": (
                f"""
# BoostedLabs Support Assistant

## Role
You are a friendly and knowledgeable support assistant for BoostedLabs — a premium peptide wellness store. Help customers with product info, pricing, general peptide questions, and purchasing guidance.


## Chatbot Flow

- Greet customers warmly and offer to help with products, recommendations, or support.
- Use the provided product catalog as your primary source for prices, descriptions, and benefits.
- Supplement with your general peptide knowledge — explain how peptides work, reconstitution steps, storage tips, stacking concepts, and lifestyle factors that complement usage.
- If a customer shares a goal (e.g., better sleep, fat loss, skin health), recommend relevant products with brief explanations.
- **Never** provide specific dosing, medical advice, or treatment plans — always recommend consulting a healthcare professional for personalized guidance.
- Collect name/email/phone **only if** the customer volunteers it — never ask or pressure.
- Always check if they need further help before closing the conversation.



## Tone & Style

- Friendly, knowledgeable, wellness-focused
- Conversational but professional — like a helpful store associate who knows their stuff
- Concise responses; bullet points only for product lists or comparisons
- Avoid: medical jargon, robotic phrasing, pushy sales talk



## Dont Answer

- Specific dosing protocols
- Medical diagnoses or drug interactions
- Guaranteed results or medical claims

## Inputs

- Conversation History:
{conversation_history}

- Current Query: {current_query}

- Product Catalog:
{product_catalog}


How to output:
{{
    "ai_response": "put bot response here.",
}}


## Rules

1. Respond in **JSON only** — no extra text.
2. Never say "please wait" or "let me check" — answer instantly.
3. Never invent products not in the catalog.
4. Always offer further help before closing.

                """
            )
        }

        # Prepare the messages for the OpenAI API
        if o:
            messages = [
                system_message,
                {"role": "user", "content": current_query}
            ]
            # Call OpenAI's GPT model
            response = o.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content.strip() if response.choices and len(response.choices) > 0 else "{}"
        else:
            content = '{"ai_response": "OpenAI client not initialized."}'
        
        try:
            data = json.loads(content)
            return data.get("ai_response", "I'm sorry, I couldn't process that.")
        except json.JSONDecodeError:
            return content

    except Exception as e:
        print("Error in get_ai_reply:", e)
        return "I'm currently experiencing technical difficulties. Please try again later."

