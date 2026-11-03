from typing import List, Dict, Any

SYSTEM_INSTRUCTION = """You are RepoMind, an elite AI codebase intelligence and RAG agent powered by Gemini 3.8 Flash.
Your objective is to provide deep, accurate, and fully cited explanations of software repositories based strictly on the retrieved code context.

RULES & GUIDELINES:
1. Grounding & Truthfulness: Base your answers ONLY on the provided code evidence and architectural structure. If information is not in the retrieved evidence, clearly state what is missing rather than guessing or fabricating.
2. Source Citations: ALWAYS cite your claims with exact file paths and line ranges using the standard format: `[path/to/file.ext:start_line-end_line]`, for example: `[app/auth.py:25-48]`.
3. Architecture & Mechanics: Explain not just WHAT the code does, but HOW components interact (data structures, call flow, dependencies, error handling, invariants).
4. Code Snippets: When illustrating concepts, present concise code snippets with the language tag and highlight key lines.
5. Tone & Style: Authoritative, crisp, professional, and developer-focused.
"""

def build_rag_user_prompt(
    question: str,
    retrieved_chunks: List[Dict[str, Any]],
    conversation_history: List[Dict[str, str]] = None
) -> str:
    """Format user query and retrieved code context into structured prompt for Gemini."""
    evidence_blocks = []
    
    for i, chunk in enumerate(retrieved_chunks, start=1):
        fpath = chunk.get("file_path", "unknown")
        sline = chunk.get("start_line", 1)
        eline = chunk.get("end_line", 1)
        lang = chunk.get("language", "text")
        sym = chunk.get("symbol_name")
        sym_str = f" | Symbol: {sym}" if sym else ""
        content = chunk.get("content", "").strip()
        
        block = f"""--- EVIDENCE [{i}] ---
Source: [{fpath}:{sline}-{eline}]{sym_str} | Language: {lang}
```{lang}
{content}
```"""
        evidence_blocks.append(block)

    evidence_text = "\n\n".join(evidence_blocks) if evidence_blocks else "No relevant code chunks retrieved."

    history_text = ""
    if conversation_history:
        formatted_history = []
        for msg in conversation_history[-4:]:  # last 4 turns
            role = "User" if msg.get("role") == "user" else "Assistant"
            formatted_history.append(f"{role}: {msg.get('content', '')}")
        history_text = "CONVERSATION HISTORY:\n" + "\n".join(formatted_history) + "\n\n"

    prompt = f"""{history_text}RETRIEVED CODE EVIDENCE FROM REPOSITORY:
{evidence_text}

DEVELOPER QUESTION:
{question}

Provide an insightful, comprehensive, and well-structured answer. Cite all relevant files and line numbers with `[filepath:start-end]`."""

    return prompt
