from flask import Flask, request, jsonify
from flask_cors import CORS
from decimal import Decimal, InvalidOperation
from datetime import datetime

app = Flask(__name__)
# Allow your frontend origin in prod (replace "*" with actual URL later)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# In-memory history (simple; resets on redeploy)
HISTORY = []

def safe_calc(a, op, b):
    # Use Decimal for accuracy and predictable rounding.
    try:
        A = Decimal(str(a))
        B = Decimal(str(b))
    except InvalidOperation:
        raise ValueError("Invalid number")

    if op == "+": return A + B
    if op == "-": return A - B
    if op == "*": return A * B
    if op == "/":
        if B == 0: raise ValueError("Division by zero")
        return A / B
    if op == "%":
        if B == 0: raise ValueError("Division by zero")
        return A % B
    raise ValueError("Unsupported operator")

@app.post("/api/calc")
def calc():
    """
    Expect JSON: { "a": number|string, "op": "+|-|*|/|%", "b": number|string }
    """
    data = request.get_json(force=True, silent=True) or {}
    print("DEBUG received:", data)
    a, op, b = data.get("a"), data.get("op"), data.get("b")
    try:
        result = safe_calc(a, op, b)
        entry = {
            "a": str(a), "op": op, "b": str(b),
            "result": str(result.normalize() if result == result.normalize() else result),
            "ts": datetime.utcnow().isoformat() + "Z"
        }
        HISTORY.append(entry)
        return jsonify({"ok": True, "result": entry["result"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.get("/api/history")
def history():
    # Optional enhancement
    return jsonify({"ok": True, "items": HISTORY[-50:]})
