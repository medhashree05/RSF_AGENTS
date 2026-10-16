import os

def load_system_prompt() -> str:
    """Load the default agent system prompt from system.md."""
    prompt_path = os.path.join(os.path.dirname(__file__), "system.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()
