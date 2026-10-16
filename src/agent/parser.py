import json
import re
from typing import Any, Dict, Optional
from src.agent.models import Action
from src.models import DeclaredScope
from src.agent.aci import SUPPORTED_ACTIONS


class ActionParseError(Exception):
    """Raised when model output cannot be parsed into a valid Action."""
    pass


def extract_json_block(text: str) -> str:
    """
    Extract JSON substring from model output.
    Supports ```json ... ``` fences, <action>...</action> tags, or outer braces.
    """
    text = text.strip()

    # 1. Try markdown code block ```json ... ``` or ``` ... ```
    fence_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(fence_pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 2. Try XML tag <action> ... </action>
    xml_pattern = r"<action>\s*(\{.*?\})\s*</action>"
    match = re.search(xml_pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 3. Try finding first '{' and matching outermost '}'
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1].strip()

    return text


def parse_action(raw_output: str) -> Action:
    """
    Parse and validate raw model text output into a structured Action instance.
    
    Raises:
        ActionParseError: If text does not contain valid JSON or missing required fields.
    """
    if not raw_output or not raw_output.strip():
        raise ActionParseError("Empty response received from model; expected JSON action.")

    json_str = extract_json_block(raw_output)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        snippet = raw_output[:200] + ("..." if len(raw_output) > 200 else "")
        raise ActionParseError(
            f"Failed to decode action JSON: {e}. Output was: '{snippet}'. "
            "Please format your action strictly as a valid JSON object."
        )

    if not isinstance(data, dict):
        raise ActionParseError(f"Action JSON must be an object (dict), got {type(data).__name__}.")

    # Identify action type (supporting 'action', 'action_type', or 'tool')
    action_type = data.get("action") or data.get("action_type") or data.get("tool")
    if not action_type or not isinstance(action_type, str):
        raise ActionParseError("Action object must contain a non-empty string field 'action'.")

    action_type = action_type.strip().lower()

    # Normalize known aliases
    aliases = {
        "view_file": "read_file",
        "read": "read_file",
        "write_file": "edit_file",
        "edit": "edit_file",
        "shell": "run_shell",
        "bash": "run_shell",
    }
    action_type = aliases.get(action_type, action_type)

    if action_type not in SUPPORTED_ACTIONS:
        raise ActionParseError(
            f"Unsupported action '{action_type}'. Supported actions are: {sorted(list(SUPPORTED_ACTIONS))}."
        )

    # Validate args
    args = data.get("args")
    if args is None:
        args = data.get("arguments", {})
    if not isinstance(args, dict):
        raise ActionParseError(f"'args' field must be a dictionary, got {type(args).__name__}.")

    # Validate or extract declared_scope
    raw_scope = data.get("declared_scope")
    if raw_scope is not None:
        if not isinstance(raw_scope, dict):
            raise ActionParseError(f"'declared_scope' must be a dictionary, got {type(raw_scope).__name__}.")
        try:
            declared_scope = DeclaredScope(**raw_scope)
        except Exception as e:
            raise ActionParseError(f"Invalid declared_scope format: {e}")
    else:
        # Default empty declared scope if omitted
        declared_scope = DeclaredScope()

    return Action(
        action_type=action_type,
        args=args,
        declared_scope=declared_scope
    )
