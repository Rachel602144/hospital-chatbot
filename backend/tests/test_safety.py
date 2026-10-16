"""Unit tests for the deterministic safety layer (app/safety.py).
These test exact, repeatable behaviour. The 'known gap' tests document
what the keyword layer MISSES, on purpose, so we can talk about it honestly."""
import pytest

from app.safety import Level, classify

EMERGENCIES = [
    "my father has chest pain",
    "he's been breathless since morning and his lips look a bit blue, is that normal?",
    "she can't breathe properly",
    "My mom collapsed in the bathroom",
    "his face is drooping and speech is slurred",
    "I think he's having a heart attack",
    "my son swallowed bleach",
    "she is not responding",
    "Hi, I wanted to ask about parking and visiting hours, also my dad has chest pain right now and I'm not sure what to do",
    "CHEST PAIN",
    "he can’t breathe",  # curly apostrophe from phone keyboards
]

SELF_HARM = [
    "I want to kill myself",
    "i don't want to live anymore",
    "I've been thinking about suicide",
    "sometimes I feel like I'd be better off dead",
]

POSSIBLE = [
    "my dad had chest pain last year, that's why I want a cardiology checkup",
    "he has a history of heart attack, need a follow-up",
    "follow up after his stroke",
]

NORMAL = [
    "what time does cardiology OPD open?",
    "book an appointment for my dad on Friday",
    "where do I park?",
    "does that time fit your schedule",  # 'fit' must not match seizure 'fits'
    "my breathing test report, when will it be ready",
]


@pytest.mark.parametrize("msg", EMERGENCIES)
def test_emergency_detected(msg):
    assert classify(msg) == Level.EMERGENCY


@pytest.mark.parametrize("msg", SELF_HARM)
def test_self_harm_detected(msg):
    assert classify(msg) == Level.SELF_HARM


@pytest.mark.parametrize("msg", POSSIBLE)
def test_past_history_is_possible_not_emergency(msg):
    assert classify(msg) == Level.POSSIBLE


@pytest.mark.parametrize("msg", NORMAL)
def test_normal_messages_not_flagged(msg):
    assert classify(msg) == Level.NONE


def test_past_symptom_happening_again_is_emergency():
    assert classify("he had chest pain last year and it's happening again right now") == Level.EMERGENCY


# ---- Known gaps: documented, not hidden ------------------------------------------------
# These are things the keyword layer does NOT catch. The model-side flag
# (flag_urgent_symptoms) may catch some of them; nothing guarantees it.

KNOWN_MISSES = [
    "it feels like an elephant is sitting on his chest",   # paraphrase
    "seene mein dard ho raha hai",                           # Hindi (romanised): chest pain
    "his left arm feels heavy and he's sweating a lot",      # indirect heart-attack signs
]


@pytest.mark.parametrize("msg", KNOWN_MISSES)
def test_known_gaps_are_missed_by_keywords(msg):
    assert classify(msg) == Level.NONE
