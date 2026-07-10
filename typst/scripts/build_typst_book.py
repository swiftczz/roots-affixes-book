#!/usr/bin/env python3
"""Build the Typst edition from the multi-file Markdown manuscript."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict, namedtuple
from pathlib import Path


SCRIPT = Path(__file__).resolve()
TYPST_DIR = SCRIPT.parents[1]
BOOK_DIR = SCRIPT.parents[2]

TITLE = "词根词缀的故事"
SUBTITLE = "一部英语词汇的起源史"
AUTHOR = "郑成中"

VOLUMES = {
    "01-阅读准备": ("第一卷", "阅读准备", "英语词汇的历史坐标"),
    "02-拉丁之根": ("第二卷", "拉丁之根", "古罗马留给英语的制度、法律与学术词汇"),
    "03-希腊之光": ("第三卷", "希腊之光", "科学、哲学与学科命名的古典源头"),
    "04-日耳曼之骨": ("第四卷", "日耳曼之骨", "英语日常核心词的底层结构"),
    "05-法语之饰": ("第五卷", "法语之饰", "诺曼征服后的语体分层与双词汇系统"),
    "06-词缀的故事": ("第六卷", "词缀的故事", "前缀、后缀与英语造词机制"),
    "07-附录": ("附录", "索引与辨正", "思考题答案、词根与词缀索引、民间词源辨正、变形规律速查"),
}

NAV_LINE = re.compile(r"^\*?下一(?:章|卷|篇)\s*→\s*\[[^\]]+\]\([^)]+\.md\)\*?\s*$")
MERMAID_BLOCK = re.compile(r"```mermaid\n(.*?)\n```", re.S)
BR = re.compile(r"<br\s*/?>", re.I)
HTML_TAG = re.compile(r"</?b>|<[^>]+>", re.I)
NODE_REF = re.compile(
    r"""^\s*
    (?P<id>[A-Za-z][A-Za-z0-9_]*)
    \s*
    (?:
      \[\s*"(?P<bracket>(?:\\.|[^"])*)"\s*\]
      |
      \{\{\s*"(?P<brace>(?:\\.|[^"])*)"\s*\}\}
    )?
    \s*$
    """,
    re.X,
)
ARROW = re.compile(r"(<-\.->|<--->|<-->|-->|-\.->|---|~~~)(?:\|([^|]*)\|)?")


Node = namedtuple("Node", "id label")
Edge = namedtuple("Edge", "source target token label", defaults=(None,))

# CJK-context punctuation normalization: half-width marks typed inside Chinese
# prose become full-width so Typst justification and glyph choice stay CJK.
CJKISH = re.compile(
    "["
    "\u2e80-\u2eff"  # CJK radicals
    "\u3000-\u303f"  # CJK symbols and punctuation
    "\u3400-\u4dbf"  # CJK extension A
    "\u4e00-\u9fff"  # CJK unified ideographs
    "\uf900-\ufaff"  # CJK compatibility ideographs
    "\uff00-\uffef"  # full-width and half-width forms
    "\u2018\u2019\u201c\u201d"  # curly quotes
    "\u2014\u2026"  # em dash, ellipsis
    "]"
)
HALF_TO_FULL = {",": "，", ":": "：", ";": "；", "!": "！", "?": "？"}
EMPHASIS_MARKS = "*_~"
PAREN_PAIR = re.compile(r"\(([^()\n]*)\)")
DQUOTE_PAIR = re.compile(r"\"([^\"]*)\"")
SQUOTE_PAIR = re.compile(r"'([^']*)'")
INLINE_CODE = re.compile(r"`[^`\n]*`")
CODE_SENTINEL = "\x00"
CJK_SPACE = re.compile(f"({CJKISH.pattern}) +({CJKISH.pattern})")
TYPST_CJK_MARKUP_SPACE = re.compile(f"({CJKISH.pattern})\\] +({CJKISH.pattern})")
TYPST_CJK_BEFORE_MARKUP_SPACE = re.compile(f"({CJKISH.pattern}) +#(strong|emph)\\[")
MARKDOWN_QUOTE_STARTS = "\"“‘"


def is_cjkish(char: str) -> bool:
    return bool(char) and CJKISH.match(char) is not None


def fullwidth_parens(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        inner = match.group(1)
        if CJKISH.search(inner):
            return f"（{inner}）"
        return match.group(0)

    # Two passes: the first converts innermost pairs, the second the pairs
    # that contained them.
    return PAREN_PAIR.sub(repl, PAREN_PAIR.sub(repl, value))


def fullwidth_quotes(
    value: str,
    pattern: re.Pattern[str],
    open_char: str,
    close_char: str,
    require_cjk: bool,
) -> str:
    parts: list[str] = []
    pos = 0
    for match in pattern.finditer(value):
        if require_cjk and not CJKISH.search(match.group(1)):
            continue
        parts.append(value[pos : match.start()])
        parts.append(f"{open_char}{match.group(1)}{close_char}")
        pos = match.end()
    parts.append(value[pos:])
    return "".join(parts)


def fullwidth_marks(value: str) -> str:
    chars = list(value)
    for index, char in enumerate(chars):
        full = HALF_TO_FULL.get(char)
        if full is None:
            continue
        # Colons also look back through digits so "词 1:xxx" converts; commas
        # must not, or "1,000" would break.
        left_transparent = EMPHASIS_MARKS + "0123456789 " if char == ":" else EMPHASIS_MARKS
        left = index - 1
        while left >= 0 and chars[left] in left_transparent:
            left -= 1
        right = index + 1
        while right < len(chars) and chars[right] in EMPHASIS_MARKS:
            right += 1
        prev = chars[left] if left >= 0 else ""
        nxt = chars[right] if right < len(chars) else ""
        if is_cjkish(prev) or is_cjkish(nxt):
            chars[index] = full
    return "".join(chars)


def remove_cjk_spaces(value: str) -> str:
    previous = None
    while previous != value:
        previous = value
        value = CJK_SPACE.sub(r"\1\2", value)
    return value


def protect_markdown_strong_boundaries(value: str) -> str:
    for marker in ("**", "__"):
        result: list[str] = []
        pos = 0
        opening = True
        while True:
            index = value.find(marker, pos)
            if index == -1:
                result.append(value[pos:])
                break
            segment = value[pos:index]
            nxt = value[index + len(marker)] if index + len(marker) < len(value) else ""
            if opening and segment and is_cjkish(segment[-1]) and nxt in MARKDOWN_QUOTE_STARTS:
                result.append(segment)
                result.append(" ")
                result.append(marker)
            else:
                result.append(segment)
                result.append(marker)
            pos = index + len(marker)
            if not opening:
                nxt = value[pos] if pos < len(value) else ""
                if nxt and not nxt.isspace() and is_cjkish(nxt):
                    result.append(" ")
            opening = not opening
        value = "".join(result)
    return value


def remove_typst_cjk_markup_spaces(value: str) -> str:
    value = TYPST_CJK_BEFORE_MARKUP_SPACE.sub(r"\1#\2[", value)
    return TYPST_CJK_MARKUP_SPACE.sub(r"\1]\2", value)


def normalize_segment(value: str) -> str:
    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        spans.append(match.group(0))
        return CODE_SENTINEL

    masked = INLINE_CODE.sub(stash, value)
    masked = fullwidth_parens(masked)
    masked = fullwidth_marks(masked)
    masked = fullwidth_quotes(masked, DQUOTE_PAIR, "“", "”", False)
    masked = remove_cjk_spaces(masked)
    masked = protect_markdown_strong_boundaries(masked)
    for span in spans:
        masked = masked.replace(CODE_SENTINEL, span, 1)
    return masked


def normalize_cjk_punctuation(value: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in value.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            lines.append(line)
            continue
        lines.append(line if in_fence else normalize_segment(line))
    return "\n".join(lines)


def run(cmd: list[str], cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def require_tools() -> dict[str, str]:
    missing = [tool for tool in ("pandoc", "typst") if not shutil.which(tool)]
    if missing:
        raise SystemExit(f"Missing required tools: {', '.join(missing)}")
    versions = {}
    for tool in ("pandoc", "typst"):
        proc = run([tool, "--version"])
        if proc.returncode != 0:
            raise SystemExit(proc.stderr.strip() or f"Could not run {tool} --version")
        versions[tool] = proc.stdout.splitlines()[0]
    return versions


def q(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def clean_label(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = value.replace(r"\"", '"')
    value = BR.sub("\n", value)
    value = HTML_TAG.sub("", value)
    value = value.replace("\\n", "\n")
    lines = [" ".join(line.split()) for line in value.splitlines()]
    value = "\n".join(line for line in lines if line).strip()
    value = fullwidth_parens(value)
    value = fullwidth_marks(value)
    value = fullwidth_quotes(value, DQUOTE_PAIR, "“", "”", False)
    return fullwidth_quotes(value, SQUOTE_PAIR, "‘", "’", True)


def clean_markdown_text(value: str) -> str:
    lines = [line for line in value.splitlines() if not NAV_LINE.match(line.strip())]
    value = "\n".join(lines)
    value = BR.sub("；", value)
    value = value.replace("Mermaid 图", "图示")
    return normalize_cjk_punctuation(value)


def normalize_edge_labels(line: str) -> str:
    def repl(match: re.Match[str]) -> str:
        label = match.group(1).strip().strip('"')
        return f" -->|{label}| "

    return re.sub(r"\s+--\s+(?![>.|])(.*?)\s+-->", repl, line)


def parse_node(token: str, nodes: dict[str, Node]) -> str | None:
    token = token.strip()
    if not token:
        return None
    match = NODE_REF.match(token)
    if not match:
        fallback = re.match(r"([A-Za-z][A-Za-z0-9_]*)", token)
        if not fallback:
            return None
        node_id = fallback.group(1)
        nodes.setdefault(node_id, Node(node_id, node_id))
        return node_id
    node_id = match.group("id")
    raw_label = match.group("bracket") if match.group("bracket") is not None else match.group("brace")
    label = clean_label(raw_label) or node_id
    if node_id not in nodes or nodes[node_id].label == node_id:
        nodes[node_id] = Node(node_id, label)
    return node_id


def parse_flowchart(block: str) -> tuple[str, dict[str, Node], list[Edge]]:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    direction = "TD"
    if lines:
        first = lines[0].split()
        if len(first) >= 2 and first[0] == "flowchart":
            direction = first[1]
            lines = lines[1:]

    nodes = {}
    edges = []

    for raw in lines:
        line = normalize_edge_labels(raw)
        if line.startswith(("style ", "classDef ", "class ")):
            continue
        matches = list(ARROW.finditer(line))
        if not matches:
            parse_node(line, nodes)
            continue

        parts = []
        arrows = []
        pos = 0
        for match in matches:
            parts.append(line[pos : match.start()])
            raw_label = (match.group(2) or "").strip().strip('"')
            arrows.append((match.group(1), clean_label(raw_label) or None))
            pos = match.end()
        parts.append(line[pos:])

        node_ids = [parse_node(part, nodes) for part in parts]
        for index, (token, label) in enumerate(arrows):
            source = node_ids[index]
            target = node_ids[index + 1] if index + 1 < len(node_ids) else None
            if source and target:
                edges.append(Edge(source, target, token, label))

    return direction, nodes, edges


def arrow_mark(token: str) -> str:
    if token in {"<-->", "<--->"}:
        return "↔"
    if token == "<-.->":
        return "⇄"
    if token == "-.->":
        return "⇢"
    if token == "---":
        return "—"
    if token == "~~~":
        return "⋯"
    return "→"


# ---------------------------------------------------------------------------
# Fletcher graph rendering: trees, forests and DAGs become real node-and-edge
# diagrams. Layout is computed here (rank -> column, DFS order -> row) and
# emitted as explicit fletcher coordinates.

# Tokens that express a layering constraint (source is an ancestor of target).
# "---" and "~~~" are used in the manuscript as merge/association links that
# still read left-to-right, so they participate in layering too.
LAYER_TOKENS = {"-->", "-.->", "---", "~~~"}

EDGE_KIND = {
    "-->": "solid",
    "-.->": "dashed",
    "---": "plain",
    "~~~": "faint",
    "<-->": "bidir",
    "<--->": "bidir",
    "<-.->": "bidir-dashed",
}

DIAGRAM_MAX_WIDTH = 124.0  # mm available inside a diagram panel
DIAGRAM_MAX_HEIGHT = 172.0  # mm before a graph is split into parts
COL_SEP = 7.0
ROW_SEP = 4.0
LINE_H = 4.0  # mm per wrapped label line at 8pt
NODE_PAD_H = 3.4  # vertical inset + stroke allowance per node
NODE_PAD_W = 5.6  # horizontal inset + stroke allowance per node
MIN_COL_W = 16.0
MAX_COL_W = 44.0


def label_line_width(line: str) -> float:
    """Rough rendered width of one label line in mm at 8pt."""
    width = 0.0
    for char in line:
        if CJKISH.match(char):
            width += 2.95
        elif char == " ":
            width += 0.9
        elif char.isupper():
            width += 1.95
        else:
            width += 1.55
    return width


def wrap_label(label: str, width_mm: float, scale: float = 0.94) -> str:
    """Wrap an edge label so it fits the free space between node columns."""
    lines: list[str] = []
    for raw in label.split("\n"):
        current = ""
        current_w = 0.0
        for char in raw:
            char_w = label_line_width(char) * scale
            if current and current_w + char_w > width_mm:
                lines.append(current)
                current = char
                current_w = char_w
            else:
                current += char
                current_w += char_w
        if current:
            lines.append(current)
    return "\n".join(lines)


def compute_ranks(nodes: dict[str, Node], edges: list[Edge]) -> dict[str, int]:
    preds = defaultdict(list)
    for edge in edges:
        if edge.token in LAYER_TOKENS and edge.source != edge.target:
            preds[edge.target].append(edge.source)

    rank: dict[str, int] = {}
    visiting: set[str] = set()

    def rk(node_id: str) -> int:
        if node_id in rank:
            return rank[node_id]
        if node_id in visiting:
            return -1  # cycle guard: ignore back edge
        visiting.add(node_id)
        value = 0
        for pred in preds.get(node_id, ()):
            if pred in visiting:
                continue
            value = max(value, rk(pred) + 1)
        visiting.discard(node_id)
        rank[node_id] = value
        return value

    for node_id in nodes:
        rk(node_id)

    # Nodes attached only through undirected edges sit next to their partner.
    layered = set()
    for edge in edges:
        if edge.token in LAYER_TOKENS:
            layered.add(edge.source)
            layered.add(edge.target)
    for edge in edges:
        if edge.token in LAYER_TOKENS:
            continue
        for a, b in ((edge.source, edge.target), (edge.target, edge.source)):
            if a not in layered and b in layered:
                rank[a] = rank[b]
    return rank


def assign_rows(nodes: dict[str, Node], edges: list[Edge], rank: dict[str, int]) -> dict[str, int]:
    children: dict[str, list[str]] = defaultdict(list)
    incoming: set[str] = set()
    for edge in edges:
        if edge.token in LAYER_TOKENS and rank.get(edge.target, 0) > rank.get(edge.source, 0):
            if edge.target not in children[edge.source]:
                children[edge.source].append(edge.target)
                incoming.add(edge.target)

    row: dict[str, int] = {}
    used: dict[int, set[int]] = defaultdict(set)
    visiting: set[str] = set()
    counter = [0]

    def place(node_id: str, wanted: int) -> int:
        column = used[rank[node_id]]
        value = wanted
        step = 0
        while value in column:
            step += 1
            value = wanted + (step + 1) // 2 * (1 if step % 2 else -1)
        column.add(value)
        row[node_id] = value
        return value

    def dfs(node_id: str) -> int:
        if node_id in row:
            return row[node_id]
        visiting.add(node_id)
        kid_rows = []
        for kid in children.get(node_id, ()):
            if kid in visiting:
                continue
            kid_rows.append(row[kid] if kid in row else dfs(kid))
        visiting.discard(node_id)
        if kid_rows:
            value = place(node_id, round(sum(kid_rows) / len(kid_rows)))
        else:
            value = place(node_id, counter[0])
            counter[0] = max(counter[0], value) + 1
        return value

    for node_id in nodes:
        if node_id not in incoming:
            dfs(node_id)
    for node_id in nodes:
        if node_id not in row:
            dfs(node_id)

    minimum = min(row.values(), default=0)
    return {node_id: value - minimum for node_id, value in row.items()}


def column_widths(
    nodes: dict[str, Node],
    rank: dict[str, int],
    col_sep: float = COL_SEP,
) -> dict[int, float]:
    need: dict[int, float] = {}
    for node_id, node in nodes.items():
        widest = max((label_line_width(line) for line in node.label.split("\n")), default=10.0)
        wanted = min(max(widest + NODE_PAD_W, MIN_COL_W), MAX_COL_W)
        column = rank[node_id]
        need[column] = max(need.get(column, 0.0), wanted)

    ncols = max(rank.values(), default=0) + 1
    for column in range(ncols):
        need.setdefault(column, MIN_COL_W)
    total = sum(need.values()) + col_sep * (ncols - 1)
    if total > DIAGRAM_MAX_WIDTH:
        scale = (DIAGRAM_MAX_WIDTH - col_sep * (ncols - 1)) / sum(need.values())
        need = {column: max(value * scale, 14.0) for column, value in need.items()}
    return need


def node_height(node: Node, col_w: float) -> float:
    usable = max(col_w - NODE_PAD_W, 8.0)
    lines = 0
    for line in node.label.split("\n"):
        lines += max(1, -(-int(label_line_width(line) * 10) // int(usable * 10)))
    return lines * LINE_H + NODE_PAD_H


def graph_height(
    nodes: dict[str, Node],
    rank: dict[str, int],
    row: dict[str, int],
    widths: dict[int, float],
) -> float:
    row_h: dict[int, float] = {}
    for node_id, node in nodes.items():
        height = node_height(node, widths[rank[node_id]])
        row_h[row[node_id]] = max(row_h.get(row[node_id], 0.0), height)
    if not row_h:
        return 0.0
    return sum(row_h.values()) + ROW_SEP * (len(row_h) - 1)


def graph_node_kinds(nodes: dict[str, Node], edges: list[Edge]) -> dict[str, str]:
    incoming_tokens: dict[str, set[str]] = defaultdict(set)
    outgoing: set[str] = set()
    for edge in edges:
        if edge.token in LAYER_TOKENS:
            incoming_tokens[edge.target].add(edge.token)
            outgoing.add(edge.source)
    kinds = {}
    for node_id in nodes:
        tokens = incoming_tokens.get(node_id, set())
        if not tokens:
            kinds[node_id] = "root"
        elif tokens <= {"-.->", "~~~"} and node_id not in outgoing:
            kinds[node_id] = "note"
        else:
            kinds[node_id] = "node"
    return kinds


def subgraph(nodes: dict[str, Node], edges: list[Edge], keep: set[str]) -> tuple[dict[str, Node], list[Edge]]:
    kept_nodes = {node_id: node for node_id, node in nodes.items() if node_id in keep}
    kept_edges = [edge for edge in edges if edge.source in keep and edge.target in keep]
    return kept_nodes, kept_edges


def reachable(start: str, edges: list[Edge]) -> set[str]:
    seen = {start}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        for edge in edges:
            if edge.token in LAYER_TOKENS and edge.source == current and edge.target not in seen:
                seen.add(edge.target)
                frontier.append(edge.target)
    return seen


def split_units(nodes: dict[str, Node], edges: list[Edge], rank: dict[str, int]) -> tuple[list[str], list[set[str]]]:
    """Break an oversized graph into root-preserving units of top-level subtrees."""
    incoming = {edge.target for edge in edges if edge.token in LAYER_TOKENS}
    roots = [node_id for node_id in nodes if node_id not in incoming]
    if len(roots) == 1:
        root = roots[0]
        kids = []
        for edge in edges:
            if edge.token in LAYER_TOKENS and edge.source == root and edge.target not in kids:
                kids.append(edge.target)
        return [root], [reachable(kid, edges) | {kid} for kid in kids]
    return [], [reachable(root, edges) for root in roots]


def layout_or_split(
    nodes: dict[str, Node],
    edges: list[Edge],
    depth: int = 0,
) -> list[tuple[dict[str, Node], list[Edge]]]:
    rank = compute_ranks(nodes, edges)
    row = assign_rows(nodes, edges, rank)
    widths = column_widths(nodes, rank)
    if graph_height(nodes, rank, row, widths) <= DIAGRAM_MAX_HEIGHT or depth >= 2:
        return [(nodes, edges)]

    anchors, units = split_units(nodes, edges, rank)
    if not units or len(units) == 1:
        return [(nodes, edges)]

    parts: list[tuple[dict[str, Node], list[Edge]]] = []
    current: set[str] = set()

    def flush() -> None:
        if not current:
            return
        part_nodes, part_edges = subgraph(nodes, edges, current | set(anchors))
        parts.extend(layout_or_split(part_nodes, part_edges, depth + 1))

    for unit in units:
        candidate = current | unit | set(anchors)
        cand_nodes, cand_edges = subgraph(nodes, edges, candidate)
        cand_rank = compute_ranks(cand_nodes, cand_edges)
        cand_row = assign_rows(cand_nodes, cand_edges, cand_rank)
        cand_widths = column_widths(cand_nodes, cand_rank)
        if current and graph_height(cand_nodes, cand_rank, cand_row, cand_widths) > DIAGRAM_MAX_HEIGHT:
            flush()
            current = set(unit)
        else:
            current |= unit
    flush()
    return parts


def render_fletcher_graph(title: str, nodes: dict[str, Node], edges: list[Edge]) -> str:
    parts = layout_or_split(nodes, edges)
    panels = []
    for index, (part_nodes, part_edges) in enumerate(parts, start=1):
        suffix = f" · {index}/{len(parts)}" if len(parts) > 1 else ""
        rank = compute_ranks(part_nodes, part_edges)
        row = assign_rows(part_nodes, part_edges, rank)
        kinds = graph_node_kinds(part_nodes, part_edges)

        # Nodes hide whatever they overlap, so a label only survives in open
        # space: widen the column gutter for labels on straight horizontal
        # edges, and the row gap for labels on same-column links.
        col_sep = COL_SEP
        row_sep = ROW_SEP
        for edge in part_edges:
            if not edge.label:
                continue
            dcol = abs(rank[edge.target] - rank[edge.source])
            drow = abs(row[edge.target] - row[edge.source])
            if dcol == 1 and drow == 0:
                col_sep = 13.0
            if dcol == 0:
                row_sep = 9.0
        widths = column_widths(part_nodes, rank, col_sep)

        lines = [
            f"#diagram-panel(title: {q(title + suffix)}, breakable: false)[",
            "  #align(center)[",
            f"    #f-diagram(spacing: ({col_sep:.0f}mm, {row_sep:.0f}mm),",
        ]
        for node_id, node in part_nodes.items():
            position = f"({rank[node_id]}, {row[node_id]})"
            width = widths[rank[node_id]]
            lines.append(
                f"      fnode({position}, {q(node.label)}, kind: {q(kinds[node_id])}, w: {width:.1f}mm),"
            )
        for edge in part_edges:
            kind = EDGE_KIND.get(edge.token, "solid")
            source = f"({rank[edge.source]}, {row[edge.source]})"
            target = f"({rank[edge.target]}, {row[edge.target]})"
            dcol = abs(rank[edge.target] - rank[edge.source])
            drow = abs(row[edge.target] - row[edge.source])
            extra = ""
            if edge.label:
                if dcol == 1 and drow == 0:
                    fit = col_sep - 1.0
                elif dcol == 0:
                    fit = 16.0
                else:
                    fit = 16.0 if dcol == 1 else 26.0
                extra += f", label: {q(wrap_label(edge.label, fit))}"
            if dcol == 0:
                extra += ", bend: 30deg"
            elif dcol >= 2:
                extra += ", bend: 16deg"
            lines.append(f"      fedge({source}, {target}, kind: {q(kind)}{extra}),")
        lines.extend(["    )", "  ]", "]"])
        panels.append("\n".join(lines))
    return "\n\n".join(panels)


def chain_edges(nodes: dict[str, Node], edges: list[Edge]) -> list[Edge] | None:
    if not nodes or len(edges) != len(nodes) - 1:
        return None
    outgoing = defaultdict(list)
    incoming = defaultdict(int)
    for edge in edges:
        if edge.token in {"<-->", "<--->", "<-.->", "---", "~~~"}:
            return None
        outgoing[edge.source].append(edge)
        incoming[edge.target] += 1
    if any(len(value) > 1 for value in outgoing.values()):
        return None
    starts = [node_id for node_id in nodes if incoming[node_id] == 0]
    if len(starts) != 1:
        return None
    ordered = []
    seen = {starts[0]}
    current = starts[0]
    while current in outgoing:
        edge = outgoing[current][0]
        if edge.target in seen:
            return None
        ordered.append(edge)
        seen.add(edge.target)
        current = edge.target
    if len(seen) != len(nodes):
        return None
    return ordered


def render_chain(title: str, nodes: dict[str, Node], edges: list[Edge]) -> str:
    ordered_nodes = [edges[0].source] + [edge.target for edge in edges]
    if len(ordered_nodes) >= 4:
        cells = []
        for index, node_id in enumerate(ordered_nodes):
            kind = "root" if index == 0 else "node"
            cells.append(f"      #d-node({q(nodes[node_id].label)}, kind: {q(kind)})")
            if index < len(edges):
                edge = edges[index]
                label_arg = f", label: {q(edge.label)}" if edge.label else ""
                cells.append(f"      #d-down(mark: \"↓\"{label_arg})")
        return (
            f"#diagram-panel(title: {q(title)}, breakable: false)[\n"
            "  #align(center)[\n"
            "    #block(width: 82%)[\n"
            + "\n".join(cells)
            + "\n    ]\n"
            "  ]\n"
            "]"
        )

    columns = []
    cells = []
    for index, node_id in enumerate(ordered_nodes):
        columns.append("1fr")
        kind = "root" if index == 0 else "node"
        cells.append(f"    d-node({q(nodes[node_id].label)}, kind: {q(kind)}),")
        if index < len(edges):
            edge = edges[index]
            columns.append("23pt")
            label_arg = f", label: {q(edge.label)}" if edge.label else ""
            cells.append(f"    d-flow(mark: {q(arrow_mark(edge.token))}{label_arg}),")
    return (
        f"#diagram-panel(title: {q(title)}, breakable: false)[\n"
        "  #table(\n"
        f"    columns: ({', '.join(columns)}),\n"
        "    stroke: none,\n"
        "    column-gutter: 5pt,\n"
        "    align: horizon,\n"
        + "\n".join(cells)
        + "\n  )\n"
        "]"
    )


def render_flowchart(block: str, diagram_no: int) -> tuple[str, dict[str, object]]:
    direction, nodes, edges = parse_flowchart(block)
    title = f"图示 {diagram_no} · 关系图"

    chain = chain_edges(nodes, edges)
    mode = "relation"
    if chain:
        typst = render_chain(f"图示 {diagram_no} · 词源路径", nodes, chain)
        mode = "chain"
    elif edges:
        typst = render_fletcher_graph(title, nodes, edges)
        mode = "fletcher"
    else:
        cells = "\n".join(f"    d-node({q(node.label)})," for node in nodes.values())
        typst = (
            f"#diagram-panel(title: {q(title)}, breakable: false)[\n"
            "  #table(columns: (1fr,), stroke: none, row-gutter: 5pt,\n"
            f"{cells}\n"
            "  )\n"
            "]"
        )
        mode = "nodes"

    info = {
        "type": "flowchart",
        "direction": direction,
        "nodes": len(nodes),
        "edges": len(edges),
        "render_mode": mode,
    }
    return typst, info


def parse_timeline(block: str) -> tuple[str, list[tuple[str, str, str | None]]]:
    lines = [line.rstrip() for line in block.splitlines() if line.strip()]
    title = "时间轴"
    entries = []
    section = None
    for raw in lines[1:]:
        line = raw.strip()
        if line.startswith("title "):
            title = clean_label(line.removeprefix("title "))
            continue
        if line.startswith("section "):
            section = clean_label(line.removeprefix("section "))
            entries.append(("section", section, None))
            continue
        parts = [clean_label(part) for part in re.split(r"\s+:\s+", line)]
        if len(parts) >= 2:
            date = parts[0]
            body = "\n".join(parts[1:])
            entries.append((date, body, section))
    return title, entries


def render_timeline(block: str, diagram_no: int) -> tuple[str, dict[str, object]]:
    title, entries = parse_timeline(block)
    rows = []
    for date, body, _section in entries:
        if date == "section":
            rows.append(f"    table.cell(colspan: 2)[#timeline-section({q(body)})],")
        else:
            rows.append(f"    timeline-date({q(date)}), timeline-entry({q(body)}),")
    typst = (
        f"#diagram-panel(title: {q('图示 ' + str(diagram_no) + ' · 时间轴 · ' + title)}, breakable: false)[\n"
        "  #table(\n"
        "    columns: (30mm, 1fr),\n"
        "    stroke: none,\n"
        "    row-gutter: 6pt,\n"
        "    column-gutter: 7pt,\n"
        + "\n".join(rows)
        + "\n  )\n"
        "]"
    )
    info = {
        "type": "timeline",
        "title": title,
        "entries": sum(1 for row in entries if row[0] != "section"),
    }
    return typst, info


def render_mermaid(block: str, diagram_no: int) -> tuple[str, dict[str, object]]:
    if block.lstrip().startswith("timeline"):
        return render_timeline(block, diagram_no)
    return render_flowchart(block, diagram_no)


def transform_file(
    path: Path,
    diagram_counter: list[int],
    redrawn_mermaid: list[dict[str, object]],
) -> str:
    text = path.read_text(encoding="utf-8")
    output = []
    pos = 0
    rel = path.relative_to(BOOK_DIR).as_posix()
    for match in MERMAID_BLOCK.finditer(text):
        output.append(clean_markdown_text(text[pos : match.start()]))
        diagram_counter[0] += 1
        typst, info = render_mermaid(match.group(1), diagram_counter[0])
        info["number"] = diagram_counter[0]
        info["source"] = rel
        redrawn_mermaid.append(info)
        output.append(f"\n\n```{{=typst}}\n{typst}\n```\n\n")
        pos = match.end()
    output.append(clean_markdown_text(text[pos:]))
    return "\n".join(part.strip("\n") for part in output if part is not None).strip() + "\n"


def manuscript_files() -> list[Path]:
    files = [
        path
        for path in sorted(BOOK_DIR.rglob("*.md"))
        if path.name != "README.md" and "typst" not in path.relative_to(BOOK_DIR).parts
    ]
    return files


def volume_call(dirname: str) -> str | None:
    if dirname == "00-前言":
        return "```{=typst}\n#part-entry(\"前言\")\n```\n"
    if dirname not in VOLUMES:
        return None
    kicker, title, subtitle = VOLUMES[dirname]
    outline_title = f"{kicker} · {title}"
    return (
        "```{=typst}\n"
        f"#volume-page({q(kicker)}, {q(title)}, subtitle: {q(subtitle)}, outline-title: {q(outline_title)})\n"
        "```\n"
    )


def build_combined(files: list[Path], redrawn_mermaid: list[dict[str, object]]) -> str:
    chunks = []
    current_dir = None
    diagram_counter = [0]
    for path in files:
        top = path.relative_to(BOOK_DIR).parts[0]
        if top != current_dir:
            current_dir = top
            call = volume_call(top)
            if call:
                chunks.append(call)
        chunks.append(transform_file(path, diagram_counter, redrawn_mermaid))
    return "\n\n".join(chunks).strip() + "\n"


def fraction_columns(match: re.Match[str]) -> str:
    count = int(match.group(1))
    if count <= 1 or count > 10:
        return match.group(0)
    return "columns: (" + ", ".join("1fr" for _ in range(count)) + "),"


TABLE_COLUMNS = re.compile(
    r"columns: \((?P<cols>1fr(?:, 1fr){1,9})\),\n"
    r"(?P<rest>\s+align: \([^)]*,\),\n\s+table\.header\((?P<header>[^\n]+)\),)"
)
TABLE_AUTO_ALIGN = re.compile(r"(?m)^(?P<indent>\s*)align: \((?P<items>auto(?:,auto)*,?)\),$")


def tuned_table_columns(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        header = match.group("header")
        count = match.group("cols").count("1fr")
        columns = None

        if header.startswith("[读法], [怎么读], [适合谁]"):
            columns = "0.82fr, 1.72fr, 0.94fr"
        elif header.startswith("[标签], [内容]"):
            columns = "0.72fr, 2.35fr"
        elif header.startswith("[层], [来源], [风格], [词长], [例]"):
            columns = "0.75fr, 0.95fr, 1.55fr, 0.62fr, 0.9fr"
        elif header.startswith("[词根或组合形式]") and count == 5:
            columns = "1.08fr, 1.68fr, 1.92fr, 0.58fr, 0.52fr"
        elif header.startswith("[前缀]") and count == 5:
            columns = "0.86fr, 1.68fr, 1.96fr, 0.66fr, 0.44fr"
        elif header.startswith("[前缀]") and count == 4:
            columns = "0.9fr, 1.84fr, 2.06fr, 0.74fr"
        elif header.startswith("[后缀]") and count == 5:
            columns = "0.82fr, 1.7fr, 1.98fr, 0.66fr, 0.44fr"
        elif header.startswith("[后缀]") and count == 4:
            columns = "0.84fr, 1.86fr, 2.08fr, 0.74fr"

        if columns is None:
            return match.group(0)
        return f"columns: ({columns}),\n{match.group('rest')}"

    return TABLE_COLUMNS.sub(repl, value)


def left_align_table_cells(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        count = match.group("items").count("auto")
        alignments = ", ".join("left + horizon" for _ in range(count))
        return f"{match.group('indent')}align: ({alignments},),"

    return TABLE_AUTO_ALIGN.sub(repl, value)


def unwrap_table_figures(value: str) -> str:
    return re.sub(
        r"#figure\(\n\s+align\(center\)\[#table\((.*?)\n\s+\)\]\n\s+, kind: table\n\s+\)",
        r"#table(\1\n  )",
        value,
        flags=re.S,
    )


def demote_headings(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        level = min(len(match.group(1)) + 1, 6)
        return "=" * level + match.group(2)

    return re.sub(r"(?m)^(=+)(\s+)", repl, value)


def insert_chapter_breaks(value: str) -> str:
    return re.sub(
        r"(?m)^(== (?:第 \d+ 章|附录 [A-Z])(?:[^\n]*))$",
        r"#pagebreak(weak: true)\n\n\1",
        value,
    )


TABLE_HEADER_LINE = re.compile(r"(?m)^(?P<indent>\s*)table\.header\((?P<cells>.*),\),$")
HEADER_CELL = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]")


def style_table_headers(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        cells = HEADER_CELL.sub(lambda cell: f"th([{cell.group(1)}])", match.group("cells"))
        return f"{match.group('indent')}table.header({cells},),"

    return TABLE_HEADER_LINE.sub(repl, value)


def postprocess_body(value: str) -> str:
    value = re.sub(r"columns:\s*(\d+),", fraction_columns, value)
    value = tuned_table_columns(value)
    value = left_align_table_cells(value)
    value = value.replace("[来源], [章节],)", "[来源], [章],)")
    value = unwrap_table_figures(value)
    value = style_table_headers(value)
    value = re.sub(r"\n#horizontalrule\n\n(?=(?:#volume-page|= ))", "\n", value)
    value = value.replace(
        "\n#horizontalrule\n\n== 二、后缀\n<二后缀>\n",
        "\n#pagebreak(weak: true)\n\n== 二、后缀\n<二后缀>\n",
    )
    value = demote_headings(value)
    value = insert_chapter_breaks(value)
    value = remove_typst_cjk_markup_spaces(value)
    imports = (
        '#import "template.typ": part-entry, volume-page, horizontalrule, diagram-panel, d-node, '
        "d-flow, d-down, d-target, relation-group, timeline-date, timeline-entry, timeline-section, "
        "th, fnode, fedge, f-diagram\n\n"
    )
    return imports + value


def write_main() -> None:
    main = f'''#import "template.typ": book

#show: book.with(
  title: {q(TITLE)},
  subtitle: {q(SUBTITLE)},
  author: {q(AUTHOR)},
)

#include "body.typ"
'''
    (TYPST_DIR / "main.typ").write_text(main, encoding="utf-8")


def main() -> int:
    versions = require_tools()
    TYPST_DIR.mkdir(exist_ok=True)
    (TYPST_DIR / "build").mkdir(exist_ok=True)

    redrawn_mermaid: list[dict[str, object]] = []
    report = {
        "title": TITLE,
        "subtitle": SUBTITLE,
        "source": str(BOOK_DIR),
        "tool_versions": versions,
        "files": [],
        "redrawn_mermaid": redrawn_mermaid,
        "external_images": [],
        "notes": [
            "All Mermaid diagrams are converted into native Typst diagram panels.",
            "No raster or SVG source images were found in the manuscript.",
            "Markdown <br/> tags outside diagrams are normalized before Pandoc conversion.",
            "Half-width punctuation in CJK context is normalized to full-width "
            "(commas, colons, quotes, parentheses) outside code fences.",
        ],
    }

    files = manuscript_files()
    report["files"] = [path.relative_to(BOOK_DIR).as_posix() for path in files]

    combined = build_combined(files, redrawn_mermaid)
    source_path = TYPST_DIR / "build" / "source-preprocessed.md"
    source_path.write_text(combined, encoding="utf-8")

    body_path = TYPST_DIR / "body.typ"
    proc = run(
        [
            "pandoc",
            str(source_path),
            "-f",
            "gfm+raw_attribute+tex_math_dollars",
            "-t",
            "typst",
            "--wrap=none",
            "-o",
            str(body_path),
        ],
        cwd=BOOK_DIR,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode

    body_path.write_text(postprocess_body(body_path.read_text(encoding="utf-8")), encoding="utf-8")
    write_main()

    report_path = TYPST_DIR / "conversion-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {body_path.relative_to(BOOK_DIR)}")
    print(f"Redrawn Mermaid diagrams: {len(report['redrawn_mermaid'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
