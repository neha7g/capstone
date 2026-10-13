"""Translation Agent (LLM).

language detection (langdetect) -> English passthrough, or Bedrock Command R+ via LiteLLM
-> translated text + confidence score -> persisted to PostgreSQL.

Caching: every model call goes through services.llm.complete(), which caches responses in Redis under
llm:{sha256(prompt)} - identical content is never translated twice. Flushing Redis only costs time.
"""
import json
import logging
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml
from langdetect import DetectorFactory, LangDetectException, detect_langs

log = logging.getLogger(__name__)
DetectorFactory.seed = 0                      # deterministic detection

CONFIGS = Path(os.environ.get("CONFIGS_DIR", "/app/configs"))
CHUNK_CHARS = 3000                            # keep each model call small and cache-friendly
NUMBER_MISMATCH_CAP = 0.6                     # confidence ceiling if figures changed in translation
UNPARSEABLE_CONFIDENCE = 0.5                  # model answered but gave no usable confidence


@lru_cache(maxsize=1)
def _prompts() -> dict:
    return yaml.safe_load((CONFIGS / "prompts" / "prompts.yaml").read_text())


@lru_cache(maxsize=1)
def _persona() -> str:
    return yaml.safe_load((CONFIGS / "personas" / "agents.yaml").read_text())["translation"]["persona"]


# ----------------------------------------------------------------------------- language
def detect_language(text: str) -> tuple[str, float]:
    """(ISO code, probability). 'unknown' when the text has no detectable language."""
    try:
        best = detect_langs(text)[0]
        return best.lang.split("-")[0], float(best.prob)
    except LangDetectException:
        return "unknown", 0.0


# ----------------------------------------------------------------------------- helpers
def chunk(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on line boundaries so table rows are never cut in half."""
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        if cur and len(cur) + len(line) > size:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return out or [text]


def parse_model_json(raw: str) -> tuple[str, float | None]:
    """Extract {'translation','confidence'} from a model reply (tolerates code fences / chatter)."""
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            data = json.loads(m[0])
            tr = data.get("translation")
            conf = data.get("confidence")
            if isinstance(tr, str) and tr.strip():
                try:
                    conf = max(0.0, min(1.0, float(conf)))
                except (TypeError, ValueError):
                    conf = None
                return tr, conf
        except json.JSONDecodeError:
            pass
    return raw.strip(), None                  # model ignored the JSON format: keep text, confidence unknown


_DATE = re.compile(r"\d{1,2}[./]\d{1,2}[./]\d{4}")


def _figures(text: str) -> set[str]:
    """Amounts/years as separator-free digit runs of 3+ digits ('1.000,00' and '1,000.00' compare equal)."""
    t = _DATE.sub(" ", text)
    t = re.sub(r"(?<=\d)[.,\s](?=\d)", "", t)
    return set(re.findall(r"\d{3,}", t))


def figures_preserved(source: str, translated: str) -> bool:
    """Financial figures must survive translation unchanged."""
    return _figures(source) <= _figures(translated)


# ----------------------------------------------------------------------------- core
def translate_text(text: str, source_language: str) -> tuple[str, float]:
    from ..config import TRANSLATION_MODEL
    from ..services import llm

    parts, weighted, total_len = [], 0.0, 0
    for piece in chunk(text):
        prompt = _prompts()["translation"].format(source_language=source_language, text=piece)
        translated, conf = parse_model_json(llm.complete(TRANSLATION_MODEL, prompt, system=_persona()))
        conf = UNPARSEABLE_CONFIDENCE if conf is None else conf
        parts.append(translated)
        weighted += conf * len(piece)
        total_len += len(piece)
    result = "\n".join(parts)
    confidence = weighted / total_len if total_len else 0.0
    if not figures_preserved(text, result):
        log.warning("figures changed during translation; capping confidence at %.2f", NUMBER_MISMATCH_CAP)
        confidence = min(confidence, NUMBER_MISMATCH_CAP)
    return result, round(confidence, 3)


def translate(raw_text: str) -> dict:
    """Pure function: detect + translate. Returns the state fields this agent owns."""
    if not raw_text or not raw_text.strip():
        return {"source_language": "unknown", "translated_text": "", "translation_confidence": 0.0}
    lang, prob = detect_language(raw_text)
    if lang == "en":
        return {"source_language": "en", "translated_text": raw_text, "translation_confidence": 1.0}
    if lang == "unknown":
        # Cannot tell the language: translate anyway but never report high confidence.
        text, conf = translate_text(raw_text, "an unidentified language")
        return {"source_language": "unknown", "translated_text": text, "translation_confidence": min(conf, 0.5)}
    text, conf = translate_text(raw_text, lang)
    if prob < 0.9:                            # unsure about the source language -> less trust in the translation
        conf = round(conf * prob, 3)
    return {"source_language": lang, "translated_text": text, "translation_confidence": conf}


def translation_node(state: dict) -> dict:
    """LangGraph node: translate state['raw_text'] and persist the result."""
    from .. import db
    out = translate(state["raw_text"])
    db.save_translation(state["invoice_id"], out["translated_text"], out["source_language"],
                        out["translation_confidence"])
    log.info("translation %s -> en, confidence %.3f", out["source_language"], out["translation_confidence"])
    return out