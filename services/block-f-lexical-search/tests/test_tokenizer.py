"""Unit checks for code-aware tokenizer."""

from app.services.tokenizer import tokenize


def test_camel_case_split():
    assert tokenize("getUserInfo") == ["get", "user", "info"]


def test_snake_case_split():
    assert tokenize("user_info") == ["user", "info"]


def test_pascal_and_kebab():
    assert tokenize("UserInfo") == ["user", "info"]
    assert tokenize("get-user-info") == ["get", "user", "info"]
