"""LLM extraction with a forced tool call, so every answer comes back in the schema."""
from __future__ import annotations

import os
import time
from typing import Any

from .schema import TOOL_SCHEMA, Eligibility

PROMPT_VERSION = "v1"  # bump this whenever SYSTEM_PROMPT changes, so results stay comparable
DEFAULT_MODEL = os.environ.get("TRIALPARSE_MODEL", "claude-haiku-5-5")

SYSTEM_PROMPT = """You read the eligibility criteria of one clinical trial and record them in a fixed schema.

Rules:
- Record only what the text states. Do not guess and do not use outside knowledge.
- Ages are in years. Convert months to years (6 months = 0.5). Use null when the text gives no age limit.
- sex is ALL unless the text limits enrollment to one sex.
- excludes_pregnancy is true only if pregnant people are excluded.
- required_conditions: diseases or conditions a participant must have to join.
- excluded_conditions: diseases or conditions that keep a participant out.
- For both condition lists use short plain names (for example "type 2 diabetes", "chronic kidney disease").
  Do not include drugs, treatments, procedures, lab values, or administrative items like consent.
- lab_thresholds: numeric limits on lab tests or body measures (HbA1c, BMI, eGFR, blood pressure and so on).
  Keep the operator exactly as written in its section. A range becomes two entries: >= low and <= high.
  section is "inclusion" or "exclusion", matching where the limit appears.
"""

TOOL = {
    "name": "record_eligibility",
    "description": "Record the structured eligibility criteria for this trial.",
    "input_schema": TOOL_SCHEMA,
}


def make_client():
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise SystemExit("pip install anthropic  (needed only for --method llm)") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY to run LLM extraction.")
    return anthropic.Anthropic()


def extract(client, model: str, title: str, criteria_text: str, retries: int = 3) -> dict[str, Any]:
    """Returns {'result': Eligibility, 'input_tokens', 'output_tokens', 'latency_ms'}."""
    user = f"Trial title: {title}\n\n<criteria>\n{criteria_text}\n</criteria>"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            t0 = time.perf_counter()
            msg = client.messages.create(
                model=model,
                max_tokens=2000,
                temperature=0,
                system=SYSTEM_PROMPT,
                tools=[TOOL],
                tool_choice={"type": "tool", "name": TOOL["name"]},
                messages=[{"role": "user", "content": user}],
            )
            latency = (time.perf_counter() - t0) * 1000
            block = next((b for b in msg.content if b.type == "tool_use"), None)
            if block is None:
                raise ValueError("model returned no tool call")
            return {
                "result": Eligibility.from_dict(block.input),
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "latency_ms": latency,
            }
        except Exception as e:  # network errors, rate limits, schema errors
            last_err = e
            time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"failed after {retries} tries: {last_err}")
