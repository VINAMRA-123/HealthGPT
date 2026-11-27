import pytest

from app.ai.scope import (
    IN_SCOPE,
    OFF_TOPIC,
    UNCERTAIN,
    check_scope,
    classify_request,
)

OFF_TOPIC_QUESTIONS = [
    "tell me something about diljeet aura tour 2026",
    "who won the IPL final",
    "write a poem about the moon",
    "python code to reverse a string",
    "what is the bitcoin price today",
    "best movies on netflix",
    "who is the prime minister of India",
    "write a song about protein",
]

IN_SCOPE_QUESTIONS = [
    "how much protein have I eaten today",
    "suggest a high protein dinner",
    "what should I eat before a workout",
    "how many calories in masala oats",
    "am I within my budget this week",
    "hello",
    "tell me about vitamin d",
]


@pytest.mark.parametrize("question", OFF_TOPIC_QUESTIONS)
def test_off_topic_is_blocked(question):
    assert check_scope(question) == OFF_TOPIC
    assert classify_request(question) == "off_topic"


@pytest.mark.parametrize("question", IN_SCOPE_QUESTIONS)
def test_health_questions_are_not_blocked(question):
    assert check_scope(question) != OFF_TOPIC
    assert classify_request(question) != "off_topic"


def test_unknown_text_is_left_to_the_prompt_rule():
    assert check_scope("is that one fine") == UNCERTAIN


def test_empty_and_non_string_are_not_blocked():
    assert check_scope("") == UNCERTAIN
    assert check_scope(None) == UNCERTAIN


def test_greeting_is_in_scope():
    assert check_scope("hi") == IN_SCOPE
