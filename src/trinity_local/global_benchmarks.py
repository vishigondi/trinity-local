"""Global benchmark scores for model comparison."""
from __future__ import annotations


def get_global_benchmarks() -> dict:
    """Get global benchmark scores for all models across categories.

    Data sourced from:
    - HumanEval: code generation
    - GSM8K: math reasoning
    - MMLU: general knowledge
    - GPQA Diamond: advanced reasoning
    - MT-Bench: writing quality
    """
    return {
        "coding": {
            "benchmark": "HumanEval",
            "unit": "pass@1 (%)",
            "models": {
                "claude": 91.3,
                "gpt": 81.0,
                "gemini": 94.3,
                "mistral": 78.5,
            },
        },
        "math": {
            "benchmark": "GSM8K",
            "unit": "accuracy (%)",
            "models": {
                "claude": 88.2,
                "gpt": 87.5,
                "gemini": 89.4,
                "mistral": 85.1,
            },
        },
        "knowledge_stem": {
            "benchmark": "MMLU (Science/Tech)",
            "unit": "accuracy (%)",
            "models": {
                "claude": 91.2,
                "gpt": 90.1,
                "gemini": 92.3,
                "mistral": 88.5,
            },
        },
        "knowledge_humanities": {
            "benchmark": "MMLU (Humanities/Social)",
            "unit": "accuracy (%)",
            "models": {
                "claude": 89.8,
                "gpt": 88.9,
                "gemini": 90.5,
                "mistral": 87.2,
            },
        },
        "reasoning": {
            "benchmark": "GPQA Diamond",
            "unit": "accuracy (%)",
            "models": {
                "claude": 68.5,
                "gpt": 71.2,
                "gemini": 72.8,
                "mistral": 61.3,
            },
        },
        "writing": {
            "benchmark": "MT-Bench (Writing)",
            "unit": "score/10",
            "models": {
                "claude": 8.7,
                "gpt": 8.5,
                "gemini": 8.4,
                "mistral": 8.1,
            },
        },
    }


def format_benchmark_display(name: str, unit: str, scores: dict) -> dict:
    """Format benchmark for display in UI."""
    return {
        "name": name.replace("_", " ").title(),
        "unit": unit,
        "scores": scores,
    }
