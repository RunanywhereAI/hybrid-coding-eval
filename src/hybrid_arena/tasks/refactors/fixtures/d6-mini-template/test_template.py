"""Acceptance tests for the mini templating engine."""

from __future__ import annotations

import pytest

from template import TemplateError, render


# ── literal pass-through ────────────────────────────────────────────


def test_literal_text():
    assert render("hello, world", {}) == "hello, world"


def test_empty_template():
    assert render("", {}) == ""


# ── variable substitution ───────────────────────────────────────────


def test_simple_var():
    assert render("hi {{ name }}", {"name": "alice"}) == "hi alice"


def test_var_with_no_spaces():
    assert render("{{name}}", {"name": "bob"}) == "bob"


def test_int_var_stringified():
    assert render("count={{ n }}", {"n": 42}) == "count=42"


def test_dotted_path():
    ctx = {"user": {"name": "carol", "age": 30}}
    assert render("{{ user.name }}", ctx) == "carol"


def test_missing_var_in_substitution_is_empty():
    # {{ missing }} → empty string (NOT an error in substitutions).
    assert render("[{{ missing }}]", {}) == "[]"


def test_missing_dotted_path_is_empty():
    assert render("[{{ a.b.c }}]", {"a": {}}) == "[]"


# ── escape filter ───────────────────────────────────────────────────


def test_escape_filter_html():
    out = render("{{ s | escape }}", {"s": "<script>"})
    assert "&lt;script&gt;" in out


def test_escape_filter_quote_chars():
    out = render("{{ s | escape }}", {"s": "a & b \"c\""})
    assert "&amp;" in out
    assert "&quot;" in out


def test_unknown_filter_raises():
    with pytest.raises(TemplateError):
        render("{{ s | bogus }}", {"s": "x"})


# ── if / else ───────────────────────────────────────────────────────


def test_if_truthy():
    src = "{% if flag %}YES{% endif %}"
    assert render(src, {"flag": True}) == "YES"
    assert render(src, {"flag": "yes"}) == "YES"
    assert render(src, {"flag": 1}) == "YES"


def test_if_falsy():
    src = "{% if flag %}YES{% endif %}"
    assert render(src, {"flag": False}) == ""
    assert render(src, {"flag": ""}) == ""
    assert render(src, {"flag": 0}) == ""


def test_if_else():
    src = "{% if flag %}YES{% else %}NO{% endif %}"
    assert render(src, {"flag": True}) == "YES"
    assert render(src, {"flag": False}) == "NO"


def test_if_unknown_variable_raises():
    # Unlike substitutions, unknown vars in {% if %} raise.
    with pytest.raises(TemplateError):
        render("{% if missing %}x{% endif %}", {})


def test_unterminated_if_raises():
    with pytest.raises(TemplateError):
        render("{% if x %}YES", {"x": True})


def test_dotted_if_condition():
    src = "{% if user.active %}LIVE{% else %}OFF{% endif %}"
    assert render(src, {"user": {"active": True}}) == "LIVE"
    assert render(src, {"user": {"active": False}}) == "OFF"


# ── for loop ────────────────────────────────────────────────────────


def test_for_iterates_list():
    src = "{% for x in items %}[{{ x }}]{% endfor %}"
    assert render(src, {"items": [1, 2, 3]}) == "[1][2][3]"


def test_for_empty_iterable_emits_nothing():
    src = "before{% for x in items %}[{{ x }}]{% endfor %}after"
    assert render(src, {"items": []}) == "beforeafter"


def test_for_unknown_iterable_raises():
    with pytest.raises(TemplateError):
        render("{% for x in items %}{% endfor %}", {})


def test_for_non_iterable_raises():
    with pytest.raises(TemplateError):
        render("{% for x in n %}{% endfor %}", {"n": 5})


def test_for_dotted_iter_path():
    src = "{% for u in data.users %}{{ u.name }}|{% endfor %}"
    ctx = {"data": {"users": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}}
    assert render(src, ctx) == "a|b|c|"


def test_unterminated_for_raises():
    with pytest.raises(TemplateError):
        render("{% for x in items %}x", {"items": [1]})


# ── comments ────────────────────────────────────────────────────────


def test_comment_stripped():
    assert render("a{# this is a comment #}b", {}) == "ab"


def test_comment_multi_line():
    src = "a{# line\nspans\nlines #}b"
    assert render(src, {}) == "ab"


# ── combinations ────────────────────────────────────────────────────


def test_nested_if_inside_for():
    src = (
        "{% for u in users %}"
        "{% if u.admin %}ADMIN:{{ u.name }}{% else %}USER:{{ u.name }}{% endif %};"
        "{% endfor %}"
    )
    ctx = {
        "users": [
            {"name": "a", "admin": True},
            {"name": "b", "admin": False},
        ]
    }
    assert render(src, ctx) == "ADMIN:a;USER:b;"


def test_real_world_template():
    src = (
        "<h1>{{ title | escape }}</h1>\n"
        "{% if items %}"
        "<ul>"
        "{% for it in items %}<li>{{ it.label | escape }}</li>{% endfor %}"
        "</ul>"
        "{% else %}<p>none</p>{% endif %}"
    )
    ctx = {
        "title": "<X>",
        "items": [{"label": "a&b"}, {"label": "c<d"}],
    }
    out = render(src, ctx)
    assert "&lt;X&gt;" in out
    assert "<li>a&amp;b</li>" in out
    assert "<li>c&lt;d</li>" in out
