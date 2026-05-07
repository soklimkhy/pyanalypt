import json
import logging
import re

import ollama
import pandas as pd
from django.conf import settings

logger = logging.getLogger(__name__)

_SSE_DONE  = "data: [DONE]\n\n"
_SSE_ERROR = "data: [ERROR] {}\n\n"


class OllamaError(Exception):
    """Custom exception for Ollama client errors."""
    pass


class OllamaClient:
    """Client for interacting with a local Ollama instance."""

    def __init__(self, model=None):
        self.model = model or getattr(settings, "OLLAMA_MODEL", "qwen2.5:7b")

    def generate_response(self, prompt, system_prompt=None):
        try:
            kwargs = {"model": self.model, "prompt": prompt, "stream": False}
            if system_prompt:
                kwargs["system"] = system_prompt
            response = ollama.generate(**kwargs)
            return response.response
        except Exception as exc:
            raise OllamaError(f"Failed to connect to Ollama: {exc}") from exc

    def stream_response(self, prompt, system_prompt=None):
        try:
            kwargs = {"model": self.model, "prompt": prompt, "stream": True}
            if system_prompt:
                kwargs["system"] = system_prompt
            for chunk in ollama.generate(**kwargs):
                token = chunk.response
                if token:
                    yield token
        except Exception as exc:
            raise OllamaError(f"Failed to connect to Ollama: {exc}") from exc


# ── SSE helpers ────────────────────────────────────────────────────────────────

def _sse_stream(client: OllamaClient, prompt: str, system_prompt: str):
    """Shared SSE generator: yields token chunks then DONE or ERROR."""
    try:
        for token in client.stream_response(prompt, system_prompt=system_prompt):
            yield f"data: {token.replace(chr(10), chr(92) + 'n')}\n\n"
        yield _SSE_DONE
    except OllamaError as exc:
        yield _SSE_ERROR.format(exc)


# ── Problem Framing ────────────────────────────────────────────────────────────

def frame_problem(columns, sample_stats=None):
    client = OllamaClient()
    system_prompt, prompt = _build_prompt(columns, sample_stats)
    return client.generate_response(prompt, system_prompt=system_prompt)


def stream_frame_problem(columns, sample_stats=None):
    """Yields SSE chunks for problem framing."""
    client = OllamaClient()
    system_prompt, prompt = _build_prompt(columns, sample_stats)
    yield from _sse_stream(client, prompt, system_prompt)


def stream_suggest_questions(columns, problem_statement=""):
    """Streams Q1, Q2, Q3… analytical questions as SSE chunks."""
    client = OllamaClient()
    system_prompt, prompt = _build_suggest_prompt(columns, problem_statement)
    yield from _sse_stream(client, prompt, system_prompt)


def generate_questions(columns, n=10, sample_stats=None):
    """Generate n analytical questions synchronously. Returns a list of question strings."""
    client = OllamaClient()
    system_prompt, prompt = _build_generate_questions_prompt(columns, n, sample_stats)
    raw = client.generate_response(prompt, system_prompt=system_prompt)
    return _parse_questions(raw)


def stream_interpret_eda(eda_type, data, columns=None):
    """Interpret EDA results (correlation, distribution, etc.) using AI."""
    client = OllamaClient()
    system_prompt = (
        "You are an expert data scientist. Interpret the following statistical results "
        "and explain them in simple, actionable terms for a business user. "
        "Focus on key insights, surprising patterns, and potential next steps."
    )
    prompt = f"EDA Type: {eda_type}\n"
    if columns:
        prompt += f"Columns: {', '.join(columns)}\n"
    prompt += f"Results Data: {json.dumps(data, indent=2)}\n\n"
    prompt += "Provide a clear interpretation of these results."
    yield from _sse_stream(client, prompt, system_prompt)


def stream_suggest_cleaning(columns, stats_summary):
    """Suggest data cleaning operations based on dataset statistics."""
    client = OllamaClient()
    system_prompt = (
        "You are an expert data engineer. Analyze the dataset statistics and suggest "
        "specific cleaning steps (e.g., imputing nulls, handling outliers, casting types). "
        "Be specific about which columns need what action and why."
    )
    prompt = f"Columns: {', '.join(columns)}\n"
    prompt += f"Statistics Summary: {json.dumps(stats_summary, indent=2)}\n\n"
    prompt += "Provide a list of recommended cleaning operations."
    yield from _sse_stream(client, prompt, system_prompt)


# ── AI Chat on Data ────────────────────────────────────────────────────────────

def build_dataset_context(df: pd.DataFrame, dataset_name: str = "", max_rows: int = 5) -> str:
    """
    Build a compact dataset context string to inject into chat system prompts.
    Includes column dtypes, descriptive stats for numeric columns, and sample rows.
    """
    lines = []
    if dataset_name:
        lines.append(f"Dataset: {dataset_name}")
    lines.append(f"Shape: {len(df)} rows × {len(df.columns)} columns\n")

    lines.append("Columns:")
    for col in df.columns:
        null_pct = round(df[col].isna().mean() * 100, 1)
        lines.append(f"  - {col} ({df[col].dtype}) — {null_pct}% null")

    num_df = df.select_dtypes(include="number")
    if not num_df.empty:
        lines.append("\nNumeric summary (mean | std | min | max):")
        for col in num_df.columns:
            s = num_df[col].describe()
            lines.append(
                f"  {col}: mean={s['mean']:.3g} std={s['std']:.3g} "
                f"min={s['min']:.3g} max={s['max']:.3g}"
            )

    sample = df.head(max_rows).fillna("").astype(str)
    lines.append(f"\nSample rows (first {min(max_rows, len(df))}):")
    lines.append(sample.to_string(index=False))

    return "\n".join(lines)


def chat_about_data(dataset_context: str, conversation_history: list[dict], user_message: str) -> str:
    """Single-shot chat turn. Returns the full assistant reply."""
    client = OllamaClient()
    prompt = f"{_format_history(conversation_history)}User: {user_message}\nAssistant:"
    return client.generate_response(prompt, system_prompt=_build_chat_system_prompt(dataset_context))


def stream_chat_about_data(dataset_context: str, conversation_history: list[dict], user_message: str):
    """Streaming chat turn. Yields SSE-formatted chunks."""
    client = OllamaClient()
    prompt = f"{_format_history(conversation_history)}User: {user_message}\nAssistant:"
    yield from _sse_stream(client, prompt, _build_chat_system_prompt(dataset_context))


def _build_chat_system_prompt(dataset_context: str) -> str:
    return (
        "You are PyAnalypt, an expert AI data analyst assistant. "
        "You help users understand and analyze their data through conversation.\n\n"
        "Dataset context:\n"
        f"{dataset_context}\n\n"
        "Answer questions clearly and concisely. Reference actual column names. "
        "Suggest EDA operations, transformations, or visualizations when relevant."
    )


def _format_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines = [
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in history[-10:]  # cap at 10 turns to stay within context window
    ]
    return "\n".join(lines) + "\n"


# ── Internal prompt builders ───────────────────────────────────────────────────

def _build_suggest_prompt(columns, problem_statement=""):
    system_prompt = (
        "You are an expert data analyst. Generate analytical questions for a dataset. "
        "Output ONLY the questions, one per line, in this exact format:\n"
        "Q1: [question]\nQ2: [question]\nQ3: [question]\n"
        "Generate between 3 and 5 questions. No other text, no explanations."
    )
    prompt = f"Dataset columns: {', '.join(columns)}\n"
    if problem_statement:
        prompt += f"Problem context: {problem_statement}\n"
    prompt += "\nGenerate analytical questions for this dataset."
    return system_prompt, prompt


def _build_generate_questions_prompt(columns, n=10, sample_stats=None):
    example = "\n".join(f"Q{i}: [question]" for i in range(1, 4))
    system_prompt = (
        f"You are an expert data analyst. Generate exactly {n} analytical questions for a dataset.\n"
        f"Output ONLY the questions, one per line, in this exact format:\n"
        f"{example}\n"
        f"...\n"
        f"Q{n}: [question]\n"
        "No introductions, no explanations, no extra text — just the numbered questions."
    )
    prompt = f"Dataset columns: {', '.join(columns)}\n"
    if sample_stats:
        prompt += f"Numeric summary (mean | std):\n{json.dumps(sample_stats, indent=2)}\n"
    prompt += f"\nGenerate {n} insightful analytical questions about this dataset."
    return system_prompt, prompt


def _parse_questions(text):
    """Extract question strings from a Qn: formatted Ollama response."""
    questions = []
    for line in text.splitlines():
        m = re.match(r"^Q\d+[\.:]\s*(.+)", line.strip())
        if m:
            questions.append(m.group(1).strip())
    return questions


def _build_prompt(columns, sample_stats):
    system_prompt = (
        "You are an expert data analyst. Your task is to look at the column headers "
        "and summary statistics of a dataset and suggest 3-5 'problem statements' "
        "or analysis goals. Be concise and professional."
    )
    prompt = f"Dataset Columns: {', '.join(columns)}\n"
    if sample_stats:
        prompt += f"Summary Statistics: {json.dumps(sample_stats, indent=2)}\n"
    prompt += "\nPlease provide a list of 3-5 problem statements for this dataset."
    return system_prompt, prompt
