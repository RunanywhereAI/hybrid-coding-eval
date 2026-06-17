"""Reference mini-templating engine.

Single-pass tokenizer + recursive-descent AST renderer.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field


class TemplateError(ValueError):
    pass


# ── tokens ──────────────────────────────────────────────────────────


@dataclass
class _Text:
    value: str


@dataclass
class _Var:
    path: str
    filter_name: str | None = None


@dataclass
class _Tag:
    kind: str  # "if" | "else" | "endif" | "for" | "endfor"
    payload: str


_TOKEN_RE = re.compile(
    r"""(?P<comment>\{\#.*?\#\})|
        (?P<var>\{\{\s*(?P<vbody>.*?)\s*\}\})|
        (?P<tag>\{%\s*(?P<tbody>.*?)\s*%\})
    """,
    re.DOTALL | re.VERBOSE,
)

_FOR_RE = re.compile(r"^for\s+(\w+)\s+in\s+([\w.]+)$")
_IF_RE = re.compile(r"^if\s+([\w.]+)$")


def _tokenize(source: str) -> list:
    out = []
    pos = 0
    for m in _TOKEN_RE.finditer(source):
        if m.start() > pos:
            out.append(_Text(source[pos:m.start()]))
        if m.group("comment"):
            pass  # drop comments
        elif m.group("var"):
            body = m.group("vbody").strip()
            if "|" in body:
                path_part, _, filt = body.rpartition("|")
                out.append(_Var(path_part.strip(), filt.strip()))
            else:
                out.append(_Var(body))
        else:
            body = m.group("tbody").strip()
            if body == "else":
                out.append(_Tag("else", ""))
            elif body == "endif":
                out.append(_Tag("endif", ""))
            elif body == "endfor":
                out.append(_Tag("endfor", ""))
            elif body.startswith("if "):
                m2 = _IF_RE.match(body)
                if not m2:
                    raise TemplateError(f"bad if tag: {body!r}")
                out.append(_Tag("if", m2.group(1)))
            elif body.startswith("for "):
                m2 = _FOR_RE.match(body)
                if not m2:
                    raise TemplateError(f"bad for tag: {body!r}")
                out.append(_Tag("for", f"{m2.group(1)}|{m2.group(2)}"))
            else:
                raise TemplateError(f"unknown tag: {body!r}")
        pos = m.end()
    if pos < len(source):
        out.append(_Text(source[pos:]))
    return out


# ── AST ─────────────────────────────────────────────────────────────


@dataclass
class _Block:
    body: list = field(default_factory=list)


@dataclass
class _IfNode:
    cond: str
    then_block: _Block
    else_block: _Block | None = None


@dataclass
class _ForNode:
    var_name: str
    iter_path: str
    body: _Block


def _parse(tokens: list, depth: int = 0) -> tuple[_Block, int]:
    block = _Block()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if isinstance(tok, _Tag):
            if tok.kind == "if":
                inner_tokens = tokens[i + 1:]
                then_block, consumed_then, has_else = _parse_until(
                    inner_tokens, {"else", "endif"}
                )
                else_block: _Block | None = None
                if has_else == "else":
                    rest = tokens[i + 1 + consumed_then + 1:]
                    else_block, consumed_else, ended = _parse_until(
                        rest, {"endif"}
                    )
                    if ended != "endif":
                        raise TemplateError("unterminated {% if %}")
                    block.body.append(
                        _IfNode(tok.payload, then_block, else_block)
                    )
                    i = i + 1 + consumed_then + 1 + consumed_else + 1
                elif has_else == "endif":
                    block.body.append(_IfNode(tok.payload, then_block))
                    i = i + 1 + consumed_then + 1
                else:
                    raise TemplateError("unterminated {% if %}")
            elif tok.kind == "for":
                var_name, iter_path = tok.payload.split("|", 1)
                body_tokens = tokens[i + 1:]
                body_block, consumed_body, ended = _parse_until(
                    body_tokens, {"endfor"}
                )
                if ended != "endfor":
                    raise TemplateError("unterminated {% for %}")
                block.body.append(_ForNode(var_name, iter_path, body_block))
                i = i + 1 + consumed_body + 1
            elif tok.kind in ("else", "endif", "endfor"):
                raise TemplateError(f"unexpected {tok.kind!r}")
            else:
                raise TemplateError(f"bad tag {tok.kind!r}")
        else:
            block.body.append(tok)
            i += 1
    return block, i


def _parse_until(tokens: list, terminators: set) -> tuple[_Block, int, str]:
    """Parse from the front of ``tokens`` until we see a tag in
    ``terminators``. Returns ``(block, consumed_count, terminator_kind)``.
    """
    block = _Block()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if isinstance(tok, _Tag) and tok.kind in terminators:
            return block, i, tok.kind
        if isinstance(tok, _Tag):
            if tok.kind == "if":
                inner_tokens = tokens[i + 1:]
                then_block, consumed_then, ended = _parse_until(
                    inner_tokens, {"else", "endif"}
                )
                else_block: _Block | None = None
                if ended == "else":
                    rest = tokens[i + 1 + consumed_then + 1:]
                    else_block, consumed_else, ended2 = _parse_until(
                        rest, {"endif"}
                    )
                    if ended2 != "endif":
                        raise TemplateError("unterminated {% if %}")
                    block.body.append(
                        _IfNode(tok.payload, then_block, else_block)
                    )
                    i = i + 1 + consumed_then + 1 + consumed_else + 1
                elif ended == "endif":
                    block.body.append(_IfNode(tok.payload, then_block))
                    i = i + 1 + consumed_then + 1
                else:
                    raise TemplateError("unterminated {% if %}")
            elif tok.kind == "for":
                var_name, iter_path = tok.payload.split("|", 1)
                body_tokens = tokens[i + 1:]
                body_block, consumed_body, ended = _parse_until(
                    body_tokens, {"endfor"}
                )
                if ended != "endfor":
                    raise TemplateError("unterminated {% for %}")
                block.body.append(_ForNode(var_name, iter_path, body_block))
                i = i + 1 + consumed_body + 1
            else:
                raise TemplateError(f"unexpected {tok.kind!r}")
        else:
            block.body.append(tok)
            i += 1
    return block, i, "EOF"


# ── eval ────────────────────────────────────────────────────────────


_MISSING = object()


def _resolve(path: str, ctx: dict, *, strict: bool) -> object:
    cur: object = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            if strict:
                raise TemplateError(f"unknown variable: {path!r}")
            return _MISSING
    return cur


def _apply_filter(value: object, name: str | None) -> str:
    if value is _MISSING:
        return ""
    s = "" if value is None else str(value)
    if name is None:
        return s
    if name == "escape":
        return html.escape(s, quote=True)
    raise TemplateError(f"unknown filter: {name!r}")


def _render_block(block: _Block, ctx: dict) -> str:
    out: list[str] = []
    for node in block.body:
        if isinstance(node, _Text):
            out.append(node.value)
        elif isinstance(node, _Var):
            val = _resolve(node.path, ctx, strict=False)
            out.append(_apply_filter(val, node.filter_name))
        elif isinstance(node, _IfNode):
            cond_val = _resolve(node.cond, ctx, strict=True)
            chosen = node.then_block if cond_val else node.else_block
            if chosen is not None:
                out.append(_render_block(chosen, ctx))
        elif isinstance(node, _ForNode):
            iterable = _resolve(node.iter_path, ctx, strict=True)
            try:
                items = list(iterable)  # type: ignore[arg-type]
            except TypeError as exc:
                raise TemplateError(
                    f"{node.iter_path!r} is not iterable"
                ) from exc
            for item in items:
                inner_ctx = dict(ctx)
                inner_ctx[node.var_name] = item
                out.append(_render_block(node.body, inner_ctx))
        else:
            raise TemplateError(f"unknown node: {node!r}")
    return "".join(out)


def render(source: str, context: dict) -> str:
    tokens = _tokenize(source)
    block, _ = _parse(tokens)
    return _render_block(block, context)
