import sys
import os
import base64
import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai
from google.genai import types
from models import InventoryItem, get_session
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
CORS(app)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

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
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                SYSTEM_PROMPT
            ]
        )
        raw = response.text.strip()
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

if __name__ == '__main__':
    app.run(debug=True)