from flask import Flask, request, jsonify
from flask_cors import CORS
from decimal import Decimal, InvalidOperation
from datetime import datetime

from decimal import Decimal, InvalidOperation, getcontext
import re

# Optional: set precision for Decimal math (tweak as you like)
getcontext().prec = 40

ALLOWED = set("0123456789.+-*/%() ")
TOKEN_RE = re.compile(r"""
    (?P<num>      \d+(?:\.\d+)? ) |
    (?P<op>       [+\-*/%]      ) |
    (?P<lpar>     \(            ) |
    (?P<rpar>     \)            ) |
    (?P<space>    \s+           )
""", re.X)

class ExprError(ValueError): pass

def tokenize(expr: str):
    if not expr or any(ch not in ALLOWED for ch in expr):
        raise ExprError("Invalid characters in expression")
    pos = 0
    tokens = []
    for m in TOKEN_RE.finditer(expr):
        if m.start() != pos:
            raise ExprError("Bad token sequence")
        pos = m.end()
        if m.lastgroup == "num":
            tokens.append(("num", m.group()))
        elif m.lastgroup == "op":
            tokens.append(("op", m.group()))
        elif m.lastgroup == "lpar":
            tokens.append(("lpar", "("))
        elif m.lastgroup == "rpar":
            tokens.append(("rpar", ")"))
        # ignore spaces
    if pos != len(expr):
        raise ExprError("Bad token sequence at end")
    return tokens

# Precedence & associativity
PRECEDENCE = {"+":1, "-":1, "*":2, "/":2, "%":2, "u-":3}
RIGHT_ASSOC = {"u-"}  # unary minus is right-assoc

def to_rpn(tokens):
    out = []
    opstack = []
    prev_kind = None
    for kind, val in tokens:
        if kind == "num":
            out.append(("num", val))
            prev_kind = "num"
        elif kind == "op":
            op = val
            # detect unary minus
            if op == "-" and (prev_kind in (None, "op", "lpar")):
                op = "u-"
            while opstack:
                top = opstack[-1]
                if top in ("(", ")"):
                    break
                if (top not in RIGHT_ASSOC and PRECEDENCE[top] >= PRECEDENCE[op]) or \
                   (top in RIGHT_ASSOC and PRECEDENCE[top] > PRECEDENCE[op]):
                    out.append(("op", opstack.pop()))
                else:
                    break
            opstack.append(op)
            prev_kind = "op"
        elif kind == "lpar":
            opstack.append("(")
            prev_kind = "lpar"
        elif kind == "rpar":
            while opstack and opstack[-1] != "(":
                out.append(("op", opstack.pop()))
            if not opstack:
                raise ExprError("Mismatched parentheses")
            opstack.pop()  # pop "("
            prev_kind = "rpar"
        else:
            raise ExprError("Unexpected token")
    while opstack:
        top = opstack.pop()
        if top == "(":
            raise ExprError("Mismatched parentheses")
        out.append(("op", top))
    return out

def eval_rpn(rpn):
    stack = []
    for kind, val in rpn:
        if kind == "num":
            try:
                stack.append(Decimal(val))
            except InvalidOperation:
                raise ExprError("Invalid number")
        else:  # op
            if val == "u-":
                if not stack: raise ExprError("Missing operand")
                stack.append(-stack.pop())
                continue
            if len(stack) < 2: raise ExprError("Missing operand")
            b = stack.pop()
            a = stack.pop()
            if val == "+": stack.append(a + b)
            elif val == "-": stack.append(a - b)
            elif val == "*": stack.append(a * b)
            elif val == "/":
                if b == 0: raise ExprError("Division by zero")
                stack.append(a / b)
            elif val == "%":
                if b == 0: raise ExprError("Division by zero")
                stack.append(a % b)
            else:
                raise ExprError("Unsupported operator")
    if len(stack) != 1:
        raise ExprError("Invalid expression")
    return stack[0]

def evaluate_expression(expr: str) -> str:
    if len(expr) > 1000:
        raise ExprError("Expression too long")
    tokens = tokenize(expr)
    rpn = to_rpn(tokens)
    result = eval_rpn(rpn)
    # normalize string output (avoid scientific if possible)
    s = format(result, 'f').rstrip('0').rstrip('.') if '.' in format(result, 'f') else str(result)
    return s

app = Flask(__name__)
# Allow your frontend origin in prod (replace "*" with actual URL later)
CORS(app, resources={r"/api/*": {"origins": [
    "https://hammer-hao.github.io",
                                 "http://localhost:5173" 
]
                                 }})

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

@app.post("/api/eval")
def eval_api():
    data = request.get_json(force=True, silent=True) or {}
    expr = (data.get("expr") or "").strip()
    if not expr:
        return jsonify({"ok": False, "error": "Empty expression"}), 400
    try:
        res = evaluate_expression(expr)
        entry = {"a": expr, "op": "=", "b": "", "result": res, "ts": datetime.utcnow().isoformat() + "Z"}
        HISTORY.append(entry)  # or persist to SQLite if you added it
        return jsonify({"ok": True, "result": res})
    except ExprError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
