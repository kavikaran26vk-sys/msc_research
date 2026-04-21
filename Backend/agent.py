import os
import json
import re
from typing import TypedDict, Annotated, Literal, Optional, Dict, Any, List

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver
from langchain.chat_models import init_chat_model

from database import SessionLocal, Product, Cluster

load_dotenv()


# ============================================================
# OUTPUT PARSER
# Keeps same final response format for frontend
# ============================================================

def looks_like_question(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if "?" in t:
        return True

    question_starters = (
        "what", "which", "would", "could", "can", "do", "does", "did",
        "is", "are", "should", "please tell", "tell me", "how much",
        "what's", "whats"
    )
    return t.lower().startswith(question_starters)


def extract_question_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    cleaned = str(text).strip()
    if not cleaned:
        return None

    # If whole response is already a question or prompt, keep it
    if looks_like_question(cleaned):
        return cleaned

    # Try to find the last sentence that looks like a question
    parts = re.split(r'(?<=[.!?])\s+', cleaned)
    for part in reversed(parts):
        part = part.strip()
        if looks_like_question(part):
            return part

    # Greeting-like assistant text can still be used as clarification
    # Example: "Hello! How can I assist you with your laptop search today?"
    if len(cleaned) <= 250:
        return cleaned

    return None


def _fallback_response(
    reason: str = "",
    clarification_question: Optional[str] = None
) -> dict:
    return {
        "reasoning": reason or "Could not process response.",
        "clarification_needed": True,
        "clarification_question": clarification_question or "What will you mainly use the laptop for?",
        "recommendations": [],
        "parse_error": True,
    }


def extract_and_validate_json(raw_text: str) -> dict:
    if not raw_text or not str(raw_text).strip():
        return _fallback_response("Empty response from agent")

    original_text = str(raw_text).strip()
    text = original_text
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = text.strip()

    try:
        return _validate_structure(json.loads(text))
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        question = extract_question_from_text(original_text)
        return _fallback_response(
            reason="Agent returned natural language instead of JSON",
            clarification_question=question or original_text
        )

    depth = 0
    end = -1
    in_str = False
    escape = False

    for i, ch in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth == 0:
            end = i
            break

    text = _attempt_close_json(text[start:]) if end == -1 else text[start:end + 1]
    text = _clean_json_string(text)

    try:
        return _validate_structure(json.loads(text))
    except json.JSONDecodeError:
        pass

    try:
        import ast
        result = ast.literal_eval(text)
        if isinstance(result, dict):
            return _validate_structure(result)
    except Exception:
        pass

    question = extract_question_from_text(original_text)
    return _fallback_response(
        reason=f"Could not parse agent output: {original_text[:200]}",
        clarification_question=question or original_text
    )


def _clean_json_string(text: str) -> str:
    result = []
    in_str = False
    prev = ""

    for ch in text:
        if ch == '"' and prev != "\\":
            in_str = not in_str
        if ch == "'" and not in_str:
            ch = '"'
        result.append(ch)
        prev = ch

    text = "".join(result)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = re.sub(r"\bNone\b", "null", text)
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r",\s*,", ",", text)
    return text


def _attempt_close_json(text: str) -> str:
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    if text.count('"') % 2 != 0:
        text += '"'
    text += "]" * max(0, open_brackets)
    text += "}" * max(0, open_braces)
    return text


def _safe_float(val) -> float:
    try:
        return float(val)
    except Exception:
        return 0.0


def _validate_structure(data: dict) -> dict:
    if not isinstance(data, dict):
        return _fallback_response("Response is not a JSON object")

    validated = {
        "reasoning": str(data.get("reasoning", "")),
        "clarification_needed": bool(data.get("clarification_needed", False)),
        "clarification_question": data.get("clarification_question", None),
        "recommendations": [],
    }

    for i, rec in enumerate((data.get("recommendations", []) or [])[:5]):
        if not isinstance(rec, dict):
            continue

        validated["recommendations"].append({
            "rank": rec.get("rank", i + 1),
            "name": str(rec.get("name", "Unknown")),
            "brand": str(rec.get("brand", "")),
            "retailer": str(rec.get("retailer", "")),
            "price": _safe_float(rec.get("price", 0)),
            "price_str": str(rec.get("price_str", "")),
            "ram": str(rec.get("ram", "N/A")),
            "storage": str(rec.get("storage", "N/A")),
            "screen_size": str(rec.get("screen_size", "N/A")),
            "processor": str(rec.get("processor", "N/A")),
            "gpu": str(rec.get("gpu", "Integrated")),
            "url": str(rec.get("url", "#")),
            "cluster_id": str(rec.get("cluster_id", "")),
            "is_multi_retailer": bool(rec.get("is_multi_retailer", False)),
            "why": str(rec.get("why", "")),
            "price_comparison": rec.get("price_comparison", None),
            "_all_prices": rec.get("_all_prices", []),
        })

    return validated


# ============================================================
# QUERY NORMALIZATION / VALIDATION
# ============================================================

ALLOWED_USE_CASES = {"gaming", "student", "business", "budget", "creative", "any"}

DEFAULTS_BY_USE_CASE = {
    "gaming": {
        "ram": "16GB",
        "storage": "512GB",
        "gpu_required": True,
    },
    "student": {
        "ram": "8GB",
        "storage": "256GB",
        "gpu_required": False,
    },
    "business": {
        "ram": "16GB",
        "storage": "512GB",
        "gpu_required": False,
    },
    "budget": {
        "ram": "8GB",
        "storage": "256GB",
        "gpu_required": False,
    },
    "creative": {
        "ram": "16GB",
        "storage": "512GB",
        "gpu_required": True,
    },
}

KNOWN_BRANDS = [
    "HP", "Lenovo", "Dell", "Asus", "Acer", "MSI", "Apple", "Samsung", "Razer", "LG"
]


def normalize_use_case(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().lower()

    mapping = {
        "uni": "student",
        "university": "student",
        "school": "student",
        "college": "student",
        "study": "student",
        "student": "student",
        "work": "business",
        "office": "business",
        "business": "business",
        "professional": "business",
        "gaming": "gaming",
        "gamer": "gaming",
        "games": "gaming",
        "creative": "creative",
        "editing": "creative",
        "video editing": "creative",
        "design": "creative",
        "budget": "budget",
        "cheap": "budget",
        "basic": "budget",
        "browsing": "budget",
        "any": "any",
    }

    return mapping.get(v, v if v in ALLOWED_USE_CASES else None)


def normalize_ram(value: Optional[str]) -> str:
    if not value:
        return "any"
    v = str(value).strip().upper().replace(" ", "")
    match = re.search(r"(4|8|12|16|24|32|64)GB", v)
    if match:
        return f"{match.group(1)}GB"
    return "any"


def normalize_storage(value: Optional[str]) -> str:
    if not value:
        return "any"

    v = str(value).strip().upper().replace(" ", "")
    gb_match = re.search(r"(64|128|256|512)GB", v)
    if gb_match:
        return f"{gb_match.group(1)}GB"

    tb_match = re.search(r"(1|2)TB", v)
    if tb_match:
        return f"{tb_match.group(1)}TB"

    return "any"


def normalize_brand(value: Optional[str]) -> str:
    if not value:
        return "any"

    v = str(value).strip().lower()
    for b in KNOWN_BRANDS:
        if b.lower() == v:
            return b

    for b in KNOWN_BRANDS:
        if v in b.lower() or b.lower() in v:
            return b

    return str(value).strip()


def normalize_budget(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        return float(value)

    v = str(value).strip().lower()

    if any(x in v for x in ["no limit", "no budget", "any budget", "unlimited"]):
        return 99999.0

    v = v.replace("£", "").replace("gbp", "").replace(",", "").strip()

    match = re.search(r"(\d+(?:\.\d+)?)", v)
    if match:
        try:
            return float(match.group(1))
        except Exception:
            return None

    return None


def apply_defaults(search_query: Dict[str, Any]) -> Dict[str, Any]:
    q = dict(search_query)

    use_case = normalize_use_case(q.get("use_case"))
    q["use_case"] = use_case

    q["budget"] = normalize_budget(q.get("budget"))
    q["ram"] = normalize_ram(q.get("ram"))
    q["storage"] = normalize_storage(q.get("storage"))
    q["brand"] = normalize_brand(q.get("brand"))

    gpu_required = q.get("gpu_required")
    if isinstance(gpu_required, str):
        gpu_required = gpu_required.strip().lower() in {"true", "yes", "1"}
    elif gpu_required is None:
        gpu_required = None
    else:
        gpu_required = bool(gpu_required)

    q["gpu_required"] = gpu_required

    if use_case in DEFAULTS_BY_USE_CASE:
        defaults = DEFAULTS_BY_USE_CASE[use_case]
        if q["ram"] == "any":
            q["ram"] = defaults["ram"]
        if q["storage"] == "any":
            q["storage"] = defaults["storage"]
        if q["gpu_required"] is None:
            q["gpu_required"] = defaults["gpu_required"]

    if q["brand"] == "":
        q["brand"] = "any"

    return q


def missing_required_fields(search_query: Dict[str, Any]) -> List[str]:
    missing = []
    if not search_query.get("use_case"):
        missing.append("use_case")
    if search_query.get("budget") is None:
        missing.append("budget")
    return missing


# ============================================================
# TOOLS
# ============================================================

@tool
def build_search_query_from_context(context_json: str) -> str:
    """
    Build a normalized search query object from LLM-extracted context.
    Input: JSON string with fields like use_case, budget, ram, storage, brand, gpu_required
    Output: normalized JSON object
    """
    try:
        data = json.loads(context_json)
    except Exception:
        data = {}

    normalized = apply_defaults({
        "use_case": data.get("use_case"),
        "budget": data.get("budget"),
        "ram": data.get("ram"),
        "storage": data.get("storage"),
        "brand": data.get("brand", "any"),
        "gpu_required": data.get("gpu_required"),
    })

    normalized["missing_fields"] = missing_required_fields(normalized)
    return json.dumps(normalized)


@tool
def validate_search_query(search_query_json: str) -> str:
    """
    Validate normalized search query before DB search.
    """
    try:
        q = json.loads(search_query_json)
    except Exception:
        return json.dumps({
            "valid": False,
            "errors": ["Invalid JSON query"],
            "normalized_query": None,
        })

    q = apply_defaults(q)
    errors = []

    if q.get("use_case") and q["use_case"] not in ALLOWED_USE_CASES:
        errors.append("Invalid use_case")

    budget = q.get("budget")
    if budget is not None:
        try:
            budget = float(budget)
            if budget <= 0:
                errors.append("Budget must be positive")
            q["budget"] = budget
        except Exception:
            errors.append("Budget must be a number")

    if q.get("ram") == "":
        q["ram"] = "any"
    if q.get("storage") == "":
        q["storage"] = "any"
    if q.get("brand") == "":
        q["brand"] = "any"

    q["missing_fields"] = missing_required_fields(q)

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "normalized_query": q,
    })


@tool
def search_laptops_db(search_query_json: str) -> str:
    """
    Search laptops from DB using a single validated query object.
    Only call this after validate_search_query says valid and missing_fields is empty.
    """
    try:
        qdata = json.loads(search_query_json)
    except Exception:
        return json.dumps({"error": "Invalid search query JSON"})

    use_case = qdata.get("use_case", "any")
    budget = qdata.get("budget")
    ram = qdata.get("ram", "any")
    storage = qdata.get("storage", "any")
    brand = qdata.get("brand", "any")
    gpu_required = bool(qdata.get("gpu_required", False))

    db: Session = SessionLocal()
    try:
        q = db.query(Product).filter(Product.price > 0)

        if budget is not None and budget < 99999:
            q = q.filter(Product.price <= budget)

        if ram and ram != "any":
            q = q.filter(Product.ram == ram)

        if storage and storage != "any":
            q = q.filter(Product.storage == storage)

        if brand and brand != "any":
            q = q.filter(Product.brand.ilike(f"%{brand}%"))

        if gpu_required:
            q = q.filter(
                (Product.name.ilike("%rtx%")) |
                (Product.name.ilike("%gtx%")) |
                (Product.gpu.ilike("%rtx%")) |
                (Product.gpu.ilike("%gtx%"))
            )

        if use_case == "gaming":
            q = q.filter(
                (Product.name.ilike("%gaming%")) |
                (Product.name.ilike("%rtx%")) |
                (Product.name.ilike("%legion%")) |
                (Product.name.ilike("%rog%")) |
                (Product.name.ilike("%nitro%")) |
                (Product.name.ilike("%predator%"))
            )

        products = q.order_by(Product.price.asc()).limit(20).all()

        if not products and budget is not None:
            relaxed = db.query(Product).filter(Product.price > 0)
            if budget < 99999:
                relaxed = relaxed.filter(Product.price <= budget)
            if brand and brand != "any":
                relaxed = relaxed.filter(Product.brand.ilike(f"%{brand}%"))
            products = relaxed.order_by(Product.price.asc()).limit(20).all()

        result = []
        for p in products:
            cluster = db.query(Cluster).filter(
                Cluster.cluster_id == p.cluster_id
            ).first()

            is_multi = cluster.retailer_count > 1 if cluster else False

            result.append({
                "global_id": p.global_id,
                "cluster_id": p.cluster_id,
                "is_multi_retailer": is_multi,
                "name": p.name,
                "brand": p.brand,
                "retailer": p.retailer,
                "price": p.price,
                "price_str": p.price_str,
                "ram": p.ram,
                "storage": p.storage,
                "screen_size": p.screen_size,
                "processor": p.processor,
                "gpu": p.gpu or "Integrated",
                "url": p.url,
                "stock_status": p.stock_status,
            })

        return json.dumps(result)
    finally:
        db.close()


@tool
def compare_cluster_prices(cluster_id: str) -> str:
    """
    Compare prices for same clustered product across retailers.
    """
    db: Session = SessionLocal()
    try:
        products = db.query(Product).filter(
            Product.cluster_id == cluster_id,
            Product.price > 0
        ).all()

        if not products:
            return json.dumps({"error": "Cluster not found"})

        prices = sorted([
            {
                "retailer": p.retailer,
                "name": p.name,
                "price": p.price,
                "price_str": p.price_str,
                "url": p.url,
            }
            for p in products
        ], key=lambda x: x["price"])

        best = prices[0]
        worst = prices[-1]
        saving = round(worst["price"] - best["price"], 2)

        return json.dumps({
            "cluster_id": cluster_id,
            "all_prices": prices,
            "cheapest_retailer": best["retailer"],
            "cheapest_price": best["price"],
            "cheapest_url": best["url"],
            "most_expensive": worst["price"],
            "saving": saving,
            "summary": (
                f"Cheapest at {best['retailer']} for £{best['price']}. "
                f"Also at {worst['retailer']} for £{worst['price']}. "
                f"Save £{saving} by choosing {best['retailer']}."
            )
        })
    finally:
        db.close()


# ============================================================
# AGENT STATE
# ============================================================

class LaptopAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    thread_id: str


# ============================================================
# SYSTEM PROMPT
# Final assistant response must still be SAME frontend JSON shape
# ============================================================

SYSTEM_PROMPT = """
You are a UK laptop shopping assistant helping users find the best laptop deals.

You must behave naturally and use tools when needed.

IMPORTANT INTERNAL FLOW:
1. Understand the user's need from current message + conversation history.
2. If required details are missing, ask exactly ONE clarification question.
3. If enough details exist, create a structured search query.
4. Validate the query before database search.
5. Search the database only after validation succeeds and required fields are complete.
6. If products are multi-retailer, compare prices and choose the cheapest retailer.
7. Return ONLY final JSON in the exact output format below.

REQUIRED INFO BEFORE SEARCH:
- use_case
- budget

CUSTOM USER REQUIREMENTS:
If user mentions custom RAM, storage, brand, or GPU preference, keep them.
Defaults should only fill missing fields after use_case is known.

DEFAULTS:
- gaming: RAM 16GB, storage 512GB, GPU required true
- student: RAM 8GB, storage 256GB, GPU required false
- business: RAM 16GB, storage 512GB, GPU required false
- budget: RAM 8GB, storage 256GB, GPU required false
- creative: RAM 16GB, storage 512GB, GPU required true

DO NOT directly invent DB results.
Use tools.

WHEN ASKING CLARIFICATION:
- Ask one question only
- Ask use case first if missing
- Ask budget second if use case known but budget missing

WHEN BUILDING STRUCTURED CONTEXT FOR TOOL:
Use build_search_query_from_context with a compact JSON object such as:
{
  "use_case": "...",
  "budget": "...",
  "ram": "...",
  "storage": "...",
  "brand": "...",
  "gpu_required": true
}

IMPORTANT OUTPUT RULE:
Prefer final JSON always.
But if you are in a clarification step and naturally ask a plain-language question,
the backend may convert that question into the frontend JSON format.

FINAL OUTPUT:
Return ONLY valid JSON with exactly this structure:

{
  "reasoning": "What was understood, what defaults/custom filters were used, and whether clarification/search was done",
  "clarification_needed": false,
  "clarification_question": null,
  "recommendations": [
    {
      "rank": 1,
      "name": "Full product name",
      "brand": "Brand",
      "retailer": "Best retailer",
      "price": 499.99,
      "price_str": "£499.99",
      "ram": "8GB",
      "storage": "256GB",
      "screen_size": "15.6\\"",
      "processor": "Intel Core i5",
      "gpu": "Integrated",
      "url": "https://...",
      "cluster_id": "CLU_00001",
      "is_multi_retailer": false,
      "why": "Why it matches the user",
      "price_comparison": null,
      "_all_prices": []
    }
  ]
}

If clarification is needed:
{
  "reasoning": "What is known and what is missing",
  "clarification_needed": true,
  "clarification_question": "Ask exactly one question",
  "recommendations": []
}

STRICT:
- final response should be valid JSON when possible
- no markdown
- no code fences
- max 5 recommendations
- if multi-retailer, include _all_prices and choose cheapest retailer
"""


# ============================================================
# BUILD AGENT
# ============================================================

class LaptopShoppingAgent:
    def __init__(self):
        self.model = init_chat_model(
            "gpt-4o-mini",
            model_provider="openai",
            temperature=0,
            max_tokens=2000,
        )

        self.tools = [
            build_search_query_from_context,
            validate_search_query,
            search_laptops_db,
            compare_cluster_prices,
        ]

        self.llm_with_tools = self.model.bind_tools(self.tools)
        self.tool_node = ToolNode(tools=self.tools)
        self.graph = self._build_graph()

    def assistant_node(self, state: LaptopAgentState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = self.llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def route_after_assistant(self, state: LaptopAgentState) -> Literal["tools", END]: # type: ignore
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    def _build_graph(self):
        checkpointer = InMemorySaver()
        builder = StateGraph(LaptopAgentState)

        builder.add_node("assistant", self.assistant_node)
        builder.add_node("tools", self.tool_node)

        builder.add_edge(START, "assistant")

        builder.add_conditional_edges(
            "assistant",
            self.route_after_assistant,
            {
                "tools": "tools",
                END: END,
            },
        )

        builder.add_edge("tools", "assistant")
        return builder.compile(checkpointer=checkpointer)


agent = LaptopShoppingAgent()


# ============================================================
# MESSAGE EXTRACTION
# ============================================================

def _content_to_text(content: Any) -> str:
    if content is None:
        return ""

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" and item.get("text"):
                    parts.append(str(item["text"]))
                elif "text" in item:
                    parts.append(str(item["text"]))
        return "\n".join([p for p in parts if p]).strip()

    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"]).strip()

    return str(content).strip()


def get_latest_assistant_text(messages: List[Any]) -> str:
    for msg in reversed(messages):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)

        if isinstance(msg, dict):
            role = msg.get("role", role)
            content = msg.get("content", "")
        else:
            content = getattr(msg, "content", "")

        text = _content_to_text(content)
        role_str = str(role).lower() if role else ""

        if text and any(r in role_str for r in ["assistant", "ai"]):
            return text

    for msg in reversed(messages):
        if isinstance(msg, dict):
            text = _content_to_text(msg.get("content", ""))
        else:
            text = _content_to_text(getattr(msg, "content", ""))
        if text:
            return text

    return ""


# ============================================================
# PUBLIC API
# Same output shape as your current frontend expects
# ============================================================

def run_agent(query: str, session_id: str = "default") -> dict:
    config = {"configurable": {"thread_id": session_id}}

    try:
        result = agent.graph.invoke(
            {
                "messages": [{"role": "user", "content": query}],
                "thread_id": session_id
            },
            config=config,
        )

        messages = result.get("messages", [])
        raw_output = get_latest_assistant_text(messages)
        print(f"Agent raw output: {raw_output}")

        parsed = extract_and_validate_json(raw_output)
        print(f"Agent parsed output: {parsed}")

        return parsed

    except Exception as e:
        error_response = _fallback_response(f"Agent error: {str(e)}")
        print(f"Agent parsed output: {error_response}")
        return error_response


def clear_session(session_id: str):
    # InMemorySaver doesn't expose simple per-thread delete here.
    # Recreate agent/checkpointer if you need a hard reset.
    pass