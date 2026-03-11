import sys
import os
import base64
import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
from models import InventoryItem, get_session
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
CORS(app)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = (
    "You are SnapChef, an AI kitchen assistant. "
    "Analyze the fridge image and respond ONLY with a valid JSON object. "
    "The JSON must have two keys: ingredients (list of objects with name and days_until_spoil) "
    "and recipe (object with recipe_name, prep_time, cook_time, ingredients list, and steps list). "
    "Only use visible ingredients plus basic staples. "
    "Total time must be 15 minutes or less. "
    "Return ONLY the JSON, no extra text."
)

@app.route('/health')
def health():
    return jsonify({"status": "SnapChef backend is running!"})

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    try:
        image_file = request.files['image']
        image_bytes = image_file.read()
        mime_type = image_file.content_type
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}
                        },
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT
                        }
                    ]
                }
            ]
        )

        raw = response.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group())

            # Save ingredients to database
            session = get_session()
            for ingredient in result.get("ingredients", []):
                item = InventoryItem(
                    name=ingredient["name"],
                    days_until_spoil=ingredient["days_until_spoil"],
                    expires_on=datetime.utcnow() + timedelta(days=ingredient["days_until_spoil"])
                )
                session.add(item)
            session.commit()
            session.close()

            return jsonify(result)
        else:
            return jsonify({"error": "Could not parse AI response", "raw": raw}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/inventory', methods=['GET'])
def get_inventory():
    session = get_session()
    items = session.query(InventoryItem).order_by(InventoryItem.expires_on).all()
    result = []
    for item in items:
        days_left = (item.expires_on - datetime.utcnow()).days
        result.append({
            "id": item.id,
            "name": item.name,
            "days_left": max(0, days_left),
            "expires_on": item.expires_on.strftime("%Y-%m-%d"),
            "status": "urgent" if days_left <= 2 else "soon" if days_left <= 5 else "ok"
        })
    session.close()
    return jsonify(result)

@app.route('/inventory/<int:item_id>', methods=['DELETE'])
def delete_inventory_item(item_id):
    session = get_session()
    item = session.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if item:
        session.delete(item)
        session.commit()
        session.close()
        return jsonify({"message": "Item deleted"})
    session.close()
    return jsonify({"error": "Item not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)