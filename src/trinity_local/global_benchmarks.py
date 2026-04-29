"""Reference benchmark scores mapped to Trinity capability categories."""
from __future__ import annotations


def get_global_benchmarks() -> dict:
    """Get public reference evals for the models Trinity routes today.

    These are static reference numbers used to contextualize capability
    categories. They are not community telemetry and are not personalized.
    """
    return {
        "coding": {
            "benchmark": "HumanEval",
            "unit": "pass@1 (%)",
            "models": {
                "claude": 91.3,
                "codex": 81.0,
                "gemini": 94.3,
            },
        },
        "math": {
            "benchmark": "GSM8K",
            "unit": "accuracy (%)",
            "models": {
                "claude": 88.2,
                "codex": 87.5,
                "gemini": 89.4,
            },
        },
        "knowledge_stem": {
            "benchmark": "MMLU (Science/Tech)",
            "unit": "accuracy (%)",
            "models": {
                "claude": 91.2,
                "codex": 90.1,
                "gemini": 92.3,
            },
        },
        "knowledge_humanities": {
            "benchmark": "MMLU (Humanities/Social)",
            "unit": "accuracy (%)",
            "models": {
                "claude": 89.8,
                "codex": 88.9,
                "gemini": 90.5,
            },
        },
        "reasoning": {
            "benchmark": "GPQA Diamond",
            "unit": "accuracy (%)",
            "models": {
                "claude": 68.5,
                "codex": 71.2,
                "gemini": 72.8,
            },
        },
        "writing": {
            "benchmark": "MT-Bench (Writing)",
            "unit": "score/10",
            "models": {
                "claude": 8.7,
                "codex": 8.5,
                "gemini": 8.4,
            },
        },
    }
