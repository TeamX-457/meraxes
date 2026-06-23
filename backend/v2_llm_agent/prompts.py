"""Strong system prompts for V2 hybrid agent."""

from typing import Optional

from v2_llm_agent.config import CONVERSATION_WINDOW

SYSTEM_PERSONA = """You are an elite AI assistant — accurate, thoughtful, and genuinely helpful.

Core standards:
- Give complete, high-quality answers. For technical topics, be precise; for casual topics, be warm and clear.
- Think before you answer on hard questions: brief reasoning, then a clear conclusion.
- Use markdown when it helps (lists, code blocks with language tags, bold for key terms).
- If you lack information, say so honestly — never invent facts, prices, dates, or policies.
- When memory context is provided below, weave it in naturally (do not say "according to my memory").
- Remember the user's name and preferences across the conversation.
- For code: production-quality, commented, and runnable when possible.
- For business/customer questions: professional, empathetic, action-oriented.

You are powered by a strong language model tier. Act like a senior consultant, not a generic chatbot."""


def _format_memory_block(memories: list[dict]) -> str:
    if not memories:
        return ""
    lines = ["<retrieved_memory>"]
    for i, m in enumerate(memories, 1):
        lines.append(f"[{i}] User asked: {m['question']}")
        lines.append(f"    Prior answer: {m['answer']}")
    lines.append("</retrieved_memory>")
    return "\n".join(lines)


def build_messages(
    user_input: str,
    history: list[dict],
    memories: list[dict],
    user_name: Optional[str] = None,
    tier: str = "strong",
) -> list[dict]:
    system_parts = [SYSTEM_PERSONA.strip()]

    if tier in ("strong", "local"):
        system_parts.append(
            "\nMode: maximum quality — think step-by-step on hard questions, "
            "then give a clear, complete answer. Prioritize accuracy over brevity."
        )
    elif tier == "fast":
        system_parts.append("\nMode: concise and fast — short, direct answers.")

    if user_name:
        system_parts.append(
            f"\nThe user's name is {user_name}. Use their name naturally when appropriate."
        )

    memory_block = _format_memory_block(memories)
    if memory_block:
        system_parts.append(
            "\nRelevant past context (use silently to personalize your reply):\n"
            + memory_block
        )

    messages: list[dict] = [{"role": "system", "content": "\n".join(system_parts)}]
    messages.extend(history[-(CONVERSATION_WINDOW * 2) :])
    messages.append({"role": "user", "content": user_input})
    return messages
