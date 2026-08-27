import json
import re
import ast
import os
import base64
from typing import Dict, Any, Tuple, Optional

# Load environment variables from .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


VISION_SYSTEM_PROMPT = """You are an expert mathematics grader. Your task is to evaluate a student's step-by-step mathematical working against a given marking rubric.

You will be provided with:
1. An image of the MARKING RUBRIC containing steps, equations, and marks allocated per step.
2. An image of the STUDENT'S ANSWER containing written/typed mathematical equations.

GRADING RULES:
1. Read the rubric image carefully to identify each step, the expected equation/solution, and its allocated marks.
2. Read the student answer image carefully to identify all written steps.
3. Accept mathematically equivalent equations where valid (e.g., "2*x = 6" is equivalent to "6 = 2*x" or "x*2 = 6"; "x = 3/2" is equivalent to "x = 1.5"; algebraic rearrangements representing the same valid state).
4. If a student step is correct and satisfies the corresponding rubric step, award the marks allocated for that step.
5. If a student step is incorrect, missing, or mathematically invalid for that step, award 0 marks for that step.
6. NEVER award more marks for a step than specified in the rubric.
7. NEVER award negative marks.
8. Keep each reason short, objective, and clear (1-2 sentences).
9. Keep any thinking/reasoning brief and ALWAYS finish with the complete JSON object.

OUTPUT FORMAT:
You MUST respond with STRICT JSON ONLY. Do not include markdown code block backticks, commentary, or text before or after the JSON.

Expected JSON format:
{
  "results": [
    {
      "rubric_step": "Step description or equation identified from rubric image",
      "student_step": "Matched student equation from answer image or 'None / Missing'",
      "correct": true,
      "marks_awarded": 1,
      "max_marks": 1,
      "reason": "Short reason for marks awarded."
    }
  ],
  "total_marks": 1,
  "maximum_marks": 3
}
"""

TEXT_SYSTEM_PROMPT = """You are an expert mathematics grader. Your task is to evaluate a student's step-by-step mathematical working against a given marking rubric.

GRADING RULES:
1. Compare each step in the marking rubric with the student's submitted steps.
2. Accept mathematically equivalent equations where valid (e.g., "2*x = 6" is equivalent to "6 = 2*x" or "x*2 = 6"; "x = 3/2" is equivalent to "x = 1.5"; algebraic rearrangements representing the same valid state).
3. If a student step is correct and satisfies the corresponding rubric step, award the marks allocated for that step.
4. If a student step is incorrect, missing, or mathematically invalid for that step, award 0 marks for that step.
5. NEVER award more marks for a step than specified in the rubric.
6. NEVER award negative marks.
7. Keep each reason short, objective, and clear (1-2 sentences).

OUTPUT FORMAT:
You MUST respond with STRICT JSON ONLY. Do not include markdown code block backticks, thinking tags, commentary, or text before or after the JSON.

Expected JSON format:
{
  "results": [
    {
      "rubric_step": "Step description or equation",
      "student_step": "Matched student equation or 'None / Missing'",
      "correct": true,
      "marks_awarded": 1,
      "max_marks": 1,
      "reason": "Short reason for marks awarded."
    }
  ],
  "total_marks": 1,
  "maximum_marks": 3
}
"""


def extract_json(raw_text: str) -> Dict[str, Any]:
    """
    Robustly extracts and parses JSON from the LLM response.
    Handles:
    - <think>...</think> reasoning tags
    - Markdown code fences (```json ... ```)
    - Python dict format with single quotes (ast.literal_eval)
    - Substring bounding between first { and last }
    - Trailing commas
    """
    if not raw_text or not isinstance(raw_text, str):
        raise ValueError("Empty or invalid response received from model.")

    cleaned = raw_text.strip()

    # 1. Remove <think>...</think> reasoning blocks from thinking models (like Qwen)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    
    # If <think> was unclosed (e.g. truncated during thought), strip out the thinking prefix if JSON exists
    if "<think>" in cleaned:
        cleaned = re.sub(r"<think>.*?(?=\{)", "", cleaned, flags=re.DOTALL).strip()


    # 2. Extract code block content if present
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if code_block_match:
        cleaned = code_block_match.group(1).strip()

    # 3. Direct JSON parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 4. Extract between first '{' and last '}'
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = cleaned[first_brace:last_brace + 1].strip()
        
        # Try direct json parse on extracted candidate
        try:
            return json.loads(json_candidate)
        except Exception:
            pass

        # Try ast.literal_eval (handles single quotes: {'results': ...}, True, False, None)
        try:
            eval_res = ast.literal_eval(json_candidate)
            if isinstance(eval_res, dict):
                return eval_res
        except Exception:
            pass

        # Try fixing common JSON issues:
        # - replace single quotes around keys/values with double quotes
        # - remove trailing commas before closing braces/brackets
        fixed = json_candidate
        # Replace Python boolean strings if needed
        fixed = re.sub(r"\bTrue\b", "true", fixed)
        fixed = re.sub(r"\bFalse\b", "false", fixed)
        fixed = re.sub(r"\bNone\b", "null", fixed)
        # Fix single quoted keys: 'key': -> "key":
        fixed = re.sub(r"(?<=[{\s,])'([^']+)'\s*:", r'"\1":', fixed)
        # Fix single quoted values: : 'value' -> : "value"
        fixed = re.sub(r":\s*'([^']*)'", r': "\1"', fixed)
        # Remove trailing commas
        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)

        try:
            return json.loads(fixed)
        except Exception:
            pass

    raise ValueError(f"Could not parse valid JSON from model response:\n{raw_text[:300]}")


def validate_evaluation_results(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and enforces grading constraints on the parsed JSON data:
    - Non-negative marks
    - marks_awarded <= max_marks per step
    - Recalculates total_marks = sum(marks_awarded) to ensure arithmetic integrity
    - total_marks <= maximum_marks
    """
    if "results" not in data or not isinstance(data["results"], list):
        raise ValueError("Response missing 'results' list.")

    calculated_total = 0.0
    calculated_max = 0.0

    for idx, item in enumerate(data["results"]):
        # Ensure default fields exist
        item.setdefault("rubric_step", f"Step {idx + 1}")
        item.setdefault("student_step", "N/A")
        item.setdefault("correct", False)
        item.setdefault("reason", "")

        # Validate step marks
        try:
            marks_awarded = float(item.get("marks_awarded", 0))
        except (ValueError, TypeError):
            marks_awarded = 0.0

        try:
            max_marks = float(item.get("max_marks", 1))
        except (ValueError, TypeError):
            max_marks = 1.0

        # Enforce non-negative marks
        if marks_awarded < 0:
            marks_awarded = 0.0
        
        # Enforce step upper bound
        if max_marks < 0:
            max_marks = 0.0
            
        if marks_awarded > max_marks:
            marks_awarded = max_marks

        # Set clean numeric representations
        item["marks_awarded"] = int(marks_awarded) if marks_awarded.is_integer() else marks_awarded
        item["max_marks"] = int(max_marks) if max_marks.is_integer() else max_marks

        calculated_total += item["marks_awarded"]
        calculated_max += item["max_marks"]

    # Provide safe total and max marks
    data["total_marks"] = int(calculated_total) if calculated_total.is_integer() else calculated_total
    
    # If maximum_marks was provided by LLM and valid, use it; otherwise fallback to sum of max_marks
    llm_max = data.get("maximum_marks")
    if llm_max is not None:
        try:
            llm_max = float(llm_max)
            data["maximum_marks"] = int(llm_max) if llm_max.is_integer() else llm_max
        except (ValueError, TypeError):
            data["maximum_marks"] = int(calculated_max) if calculated_max.is_integer() else calculated_max
    else:
        data["maximum_marks"] = int(calculated_max) if calculated_max.is_integer() else calculated_max

    # Enforce total <= maximum
    if data["total_marks"] > data["maximum_marks"]:
        data["total_marks"] = data["maximum_marks"]

    return data


def encode_image_bytes_to_base64(image_bytes: bytes) -> str:
    """Converts image bytes into a base64 encoded string."""
    return base64.b64encode(image_bytes).decode("utf-8")


def evaluate_equations_images(
    rubric_image_bytes: bytes,
    student_image_bytes: bytes,
    rubric_mime: str = "image/png",
    student_mime: str = "image/png",
    api_key: Optional[str] = None,
    model_name: str = "qwen/qwen3.6-27b"
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Sends rubric image and student answer image to Groq Vision LLM
    and returns structured evaluation.
    
    Returns:
        (success: bool, data: dict, error_message: str)
    """
    effective_api_key = api_key or os.getenv("GROQ_API_KEY")
    if not effective_api_key or not effective_api_key.strip():
        return False, {}, "Groq API Key is required. Please set GROQ_API_KEY in .env or enter it in the sidebar."

    if not rubric_image_bytes:
        return False, {}, "Rubric image cannot be empty."

    if not student_image_bytes:
        return False, {}, "Student answer image cannot be empty."

    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage
    except ImportError:
        return False, {}, "Missing required packages. Please run: pip install -r requirements.txt"

    try:
        rubric_b64 = encode_image_bytes_to_base64(rubric_image_bytes)
        student_b64 = encode_image_bytes_to_base64(student_image_bytes)

        user_content = [
            {
                "type": "text",
                "text": "Image 1 is the MARKING RUBRIC (with steps and allocated marks). Image 2 is the STUDENT ANSWER (written equations/working). Evaluate the student answer against the rubric step-by-step and return strict JSON."
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{rubric_mime};base64,{rubric_b64}"
                }
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{student_mime};base64,{student_b64}"
                }
            }
        ]

        raw_content = ""
        # Try direct Groq client first for vision & JSON mode
        try:
            from groq import Groq
            client = Groq(api_key=effective_api_key)
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": VISION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                max_tokens=4096,
                temperature=0.0
            )
            raw_content = completion.choices[0].message.content
        except Exception:
            # Fallback to LangChain ChatGroq
            llm = ChatGroq(
                groq_api_key=effective_api_key,
                model_name=model_name,
                max_tokens=4096,
                temperature=0.0
            )
            messages = [
                SystemMessage(content=VISION_SYSTEM_PROMPT),
                HumanMessage(content=user_content)
            ]
            response = llm.invoke(messages)
            raw_content = response.content

        parsed_data = extract_json(raw_content)
        validated_data = validate_evaluation_results(parsed_data)

        return True, validated_data, ""


    except Exception as e:
        return False, {}, f"Vision evaluation failed: {str(e)}"


def evaluate_equations_text(
    rubric: str,
    student_answer: str,
    api_key: Optional[str] = None,
    model_name: str = "llama-3.3-70b-versatile"
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Sends text-based rubric and student equations to Groq LLM and returns structured evaluation.
    
    Returns:
        (success: bool, data: dict, error_message: str)
    """
    effective_api_key = api_key or os.getenv("GROQ_API_KEY")
    if not effective_api_key or not effective_api_key.strip():
        return False, {}, "Groq API Key is required. Please set GROQ_API_KEY in .env or enter it in the sidebar."

    if not rubric.strip():
        return False, {}, "Marking rubric cannot be empty."

    if not student_answer.strip():
        return False, {}, "Student answer cannot be empty."

    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage
    except ImportError:
        return False, {}, "Missing required packages. Please run: pip install -r requirements.txt"

    user_prompt = f"""Please evaluate the following student response against the marking rubric.

### MARKING RUBRIC:
{rubric}

### STUDENT ANSWER:
{student_answer}

Respond with the strict JSON format specified in the system prompt."""

    try:
        llm = ChatGroq(
            groq_api_key=effective_api_key,
            model_name=model_name,
            model_kwargs={"response_format": {"type": "json_object"}},
            temperature=0.0
        )

        messages = [
            SystemMessage(content=TEXT_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]

        response = llm.invoke(messages)
        parsed_data = extract_json(response.content)
        validated_data = validate_evaluation_results(parsed_data)

        return True, validated_data, ""

    except Exception as e:
        return False, {}, f"Evaluation failed: {str(e)}"


# Alias for backward compatibility
evaluate_equations = evaluate_equations_text
