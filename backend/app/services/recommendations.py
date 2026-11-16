"""Evidence-grounded recommendations.

The rule is that no agronomic instruction reaches a farmer unless it came from a curated
source and a technician approved it. Two mechanisms enforce that, and they are different:

  1. The PROMPT tells a language model what it may not say.
  2. The VALIDATOR checks what it actually said, and rejects the output otherwise.

Only the second is enforcement. A prompt instruction is a request; models comply most of
the time, and "most of the time" is not a safety property when the failure mode is a
wrong pesticide rate given to a farmer.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from app.config import Config

log = logging.getLogger(__name__)

FALLBACK = "Consult an agricultural technician."

SEVERITY_BANDS = (
    (0.5, "none"),
    (10.0, "mild"),
    (30.0, "moderate"),
    (float("inf"), "severe"),
)

# Patterns that may only appear if they are present verbatim in a retrieved record.
_DOSAGE_PATTERNS = [
    re.compile(r"\b\d+(\.\d+)?\s?(ml|l|litre|liter|g|kg|mg|oz)\b", re.I),
    re.compile(r"\b\d+(\.\d+)?\s?(ml|l|g|kg)\s?/\s?(ha|hectare|L|liter|litre)\b", re.I),
    re.compile(r"\b\d+(\.\d+)?\s?%\s?(solution|concentration|a\.?i\.?)\b", re.I),
    re.compile(r"\bre-?entry interval\b", re.I),
    re.compile(r"\b\d+\s?(days?|hours?)\s+(before|after)\s+(harvest|application|spray)", re.I),
    re.compile(r"\bapply\s+\d", re.I),
    re.compile(r"\bevery\s+\d+\s?(days?|weeks?)\b", re.I),
]

# Common active ingredients and product-name endings. Not exhaustive by design: the
# validator's job is to catch the obvious cases, and the technician gate catches the rest.
_CHEMICAL_PATTERNS = [
    re.compile(r"\b\w+(conazole|thrin|phos|carb|mycin|amide|prid|strobin|zeb)\b", re.I),
    re.compile(r"\b(mancozeb|carbendazim|chlorpyrifos|imidacloprid|glyphosate|urea|"
               r"copper oxychloride|validamycin|tricyclazole|buprofezin)\b", re.I),
]


def severity_band(value: float | None) -> str:
    if value is None:
        return "not_measured"
    for threshold, name in SEVERITY_BANDS:
        if value <= threshold:
            return name
    return "severe"


def cache_key(condition_code: str, band: str, growth_stage: str) -> str:
    return f"{condition_code}|{band}|{growth_stage}"


# ------------------------------------------------------------------------ validator


def validate_output(text_out: str, retrieved_text: str) -> tuple[bool, list[str]]:
    """Reject anything the retrieved records do not actually contain.

    Comparison is on normalised text: a dosage or product name is allowed only if the
    exact string appears in what was retrieved.
    """
    if not text_out:
        return False, ["empty output"]

    haystack = " ".join(retrieved_text.split()).lower()
    problems: list[str] = []

    for pattern in _DOSAGE_PATTERNS + _CHEMICAL_PATTERNS:
        for match in pattern.finditer(text_out):
            phrase = " ".join(match.group(0).split()).lower()
            if phrase not in haystack:
                problems.append(match.group(0).strip())

    return (not problems), sorted(set(problems))


# ------------------------------------------------------------------------- phrasing


class Phraser(ABC):
    """Turns retrieved records into farmer-readable text. Adds no agronomy."""

    name = "abstract"

    @abstractmethod
    def phrase(self, facts: dict, records: list[dict]) -> str:
        ...


class TemplatePhraser(Phraser):
    """Deterministic assembly of the retrieved records. The default.

    No model call, no internet, and no possibility of invention: every sentence is
    either a fixed frame or text copied from the knowledge base.
    """

    name = "TemplatePhraser"

    def phrase(self, facts: dict, records: list[dict]) -> str:
        if not records:
            return FALLBACK
        record = records[0]
        band = facts.get("severity_band", "not_measured")
        stage = facts.get("growth_stage", "DATA_REQUIRED")

        parts = [
            f"Condition: {facts.get('condition_name', 'Unknown')}.",
            f"Severity estimate: {band}. Crop stage: {stage}.",
        ]
        if record.get("identification_cues"):
            parts.append(f"What to look for: {record['identification_cues']}")
        if record.get("cultural_measures"):
            parts.append(f"What you can do: {record['cultural_measures']}")
        if record.get("preventive_measures"):
            parts.append(f"Preventing it next season: {record['preventive_measures']}")
        if record.get("monitoring_guidance"):
            parts.append(f"What to watch: {record['monitoring_guidance']}")
        parts.append(
            record.get("when_to_call")
            or "Contact an agricultural technician if the affected area grows."
        )
        return "\n\n".join(parts)


class LLMPhraser(Phraser):
    """Slot for a language model. Not enabled without an API key.

    The system prompt is written here so it can be read and reviewed. It is a request,
    not a guarantee: validate_output() is what actually holds the line.
    """

    name = "LLMPhraser"

    SYSTEM_PROMPT = (
        "You rewrite agricultural guidance for rice farmers in Surallah, South Cotabato, "
        "Philippines. You will be given (a) facts about one detection and (b) curated "
        "records from Philippine agricultural authorities.\n\n"
        "RULES:\n"
        "1. Use ONLY the supplied records. Add no agronomic content from your own "
        "knowledge.\n"
        "2. Never name a pesticide, fungicide, herbicide, fertiliser product, active "
        "ingredient, application rate, dosage, spray interval or re-entry interval "
        "unless that exact text appears in the supplied records.\n"
        "3. If the records do not cover the condition, reply with exactly: "
        f"{FALLBACK}\n"
        "4. Write plainly, in short sentences, for a reader who is not a scientist.\n"
        "5. Do not state or imply certainty about the diagnosis."
    )

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def phrase(self, facts: dict, records: list[dict]) -> str:
        if not self.cfg.LLM_API_KEY:
            raise RuntimeError(
                "LLM_NOT_AVAILABLE: no API key configured. "
                "Set AGRISCAN_PHRASER_IMPL=template to generate without a model."
            )
        raise NotImplementedError(
            "LLMPhraser is a wired interface. Implement the call in one place, then "
            "pass its output through validate_output() before storing."
        )


def build_phraser(cfg: Config) -> Phraser:
    if cfg.PHRASER_IMPL == "llm":
        return LLMPhraser(cfg)
    return TemplatePhraser()


# ------------------------------------------------------------------------ retrieval


def records_to_text(records: list[dict]) -> str:
    fields = (
        "identification_cues", "cultural_measures", "preventive_measures",
        "monitoring_guidance", "when_to_call",
    )
    return "\n".join(
        str(record.get(field) or "") for record in records for field in fields
    )


# What the text generator is allowed to see. PROMISE (pp. xviii, xxvii) gives its AI
# assistant "minimized participant context" and nothing that could identify a person.
# The generator needs the condition, how severe it looks and the growth stage, and
# nothing else. Field ids, condition ids, owners, coordinates and photographs stay out.
PHRASER_FACT_KEYS = ("condition_code", "condition_name", "severity_band", "growth_stage")


def minimised_facts(facts: dict) -> dict:
    return {key: facts.get(key) for key in PHRASER_FACT_KEYS}


def generate(facts: dict, records: list[dict], cfg: Config) -> dict:
    """Produce candidate text. Always returns a dict; never raises on model failure.

    Takes no database session by design: the generator can read what it is handed and
    return text, and cannot write to a detection. A test pins that signature.
    """
    facts = minimised_facts(facts)
    if not records:
        return {
            "text": FALLBACK,
            "generated_by": "fallback",
            "validated": True,
            "problems": [],
            "note": "No knowledge base record matched this condition.",
        }

    phraser = build_phraser(cfg)
    try:
        text_out = phraser.phrase(facts, records)
    except (RuntimeError, NotImplementedError) as exc:
        log.warning("Phraser unavailable (%s); falling back to template.", exc)
        text_out = TemplatePhraser().phrase(facts, records)
        phraser = TemplatePhraser()

    ok, problems = validate_output(text_out, records_to_text(records))
    if not ok:
        log.error(
            "Generated recommendation contained ungrounded specifics %s; suppressed.",
            problems,
        )
        return {
            "text": FALLBACK,
            "generated_by": f"{phraser.name}+validator_rejected",
            "validated": False,
            "problems": problems,
            "note": (
                "Output named dosages or products absent from the sources, so it was "
                "discarded and replaced with the fallback."
            ),
        }

    return {
        "text": text_out,
        "generated_by": phraser.name,
        "validated": True,
        "problems": [],
        "note": None,
    }
