from __future__ import annotations


ROLE_INSTRUCTIONS = {
    "thinker": (
        "You are the Thinker. Decompose the task, identify strategy, risks, and the best next step. "
        "Do not over-execute. Produce a concise plan the Worker can act on."
    ),
    "worker": (
        "You are the Worker. Execute the task directly using the available context. "
        "Be concrete, complete, and practical."
    ),
    "verifier": (
        "You are the Verifier. Check correctness, edge cases, contradictions, and missing details. "
        "If the current answer is acceptable, say ACCEPT and provide the polished final answer. "
        "If not, say REVISE and state what is wrong."
    ),
}


def build_prompt(
    *,
    role: str,
    task: str,
    task_kind: str,
    transcript: list[dict[str, str]],
) -> str:
    history = []
    for turn in transcript:
        history.append(
            f"[turn {turn['turn']}] role={turn['role']} provider={turn['provider']}\n{turn['content']}"
        )

    transcript_block = "\n\n".join(history) if history else "(no prior turns)"
    role_instruction = ROLE_INSTRUCTIONS[role]

    return (
        f"{role_instruction}\n\n"
        f"Task kind: {task_kind}\n"
        f"Original user task:\n{task}\n\n"
        f"Prior transcript:\n{transcript_block}\n\n"
        "Return only your role output."
    )
