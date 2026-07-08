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

VOLUMES = {
    "01-阅读准备": ("第一卷", "阅读准备", "英语词汇的历史坐标"),
    "02-拉丁之根": ("第二卷", "拉丁之根", "古罗马留给英语的制度、法律与学术词汇"),
    "03-希腊之光": ("第三卷", "希腊之光", "科学、哲学与学科命名的古典源头"),
    "04-日耳曼之骨": ("第四卷", "日耳曼之骨", "英语日常核心词的底层结构"),
    "05-法语之饰": ("第五卷", "法语之饰", "诺曼征服后的语体分层与双词汇系统"),
    "06-词缀的故事": ("第六卷", "词缀的故事", "前缀、后缀与英语造词机制"),
    "07-附录": ("附录", "索引与辨正", "词根、词缀、民间词源与思考题答案"),
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
    return "\n".join(line for line in lines if line).strip()


def clean_markdown_text(value: str) -> str:
    lines = [line for line in value.splitlines() if not NAV_LINE.match(line.strip())]
    value = "\n".join(lines)
    value = BR.sub("；", value)
    value = value.replace("Mermaid 图", "图示")
    return value


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
            arrows.append((match.group(1), clean_label(match.group(2)) or None))
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


def node_kind(node_id: str, incoming: set[str]) -> str:
    return "root" if node_id not in incoming else "node"


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


def chunked_relation_groups(
    grouped: list[tuple[str, list[Edge]]],
    max_groups: int = 4,
    max_targets: int = 11,
) -> list[list[tuple[str, list[Edge]]]]:
    expanded = []
    for source, source_edges in grouped:
        for start in range(0, len(source_edges), 7):
            expanded.append((source, source_edges[start : start + 7]))

    chunks = []
    current = []
    target_count = 0
    for source, source_edges in expanded:
        if current and (len(current) >= max_groups or target_count + len(source_edges) > max_targets):
            chunks.append(current)
            current = []
            target_count = 0
        current.append((source, source_edges))
        target_count += len(source_edges)
    if current:
        chunks.append(current)
    return chunks


def render_relation_panels(
    title: str,
    nodes: dict[str, Node],
    edges: list[Edge],
    incoming: set[str],
) -> str:
    grouped_map = defaultdict(list)
    order = []
    for edge in edges:
        if edge.source not in grouped_map:
            order.append(edge.source)
        grouped_map[edge.source].append(edge)
    grouped = [(source, grouped_map[source]) for source in order]
    chunks = chunked_relation_groups(grouped)
    panels = []
    for index, chunk in enumerate(chunks, start=1):
        suffix = f" · {index}/{len(chunks)}" if len(chunks) > 1 else ""
        groups = []
        for source, source_edges in chunk:
            source_node = nodes.get(source, Node(source, source))
            kind = node_kind(source, incoming)
            targets = []
            for edge in source_edges:
                target = nodes.get(edge.target, Node(edge.target, edge.target))
                label_arg = f", edge: {q(edge.label)}" if edge.label else ""
                targets.append(
                    f"    #d-target({q(target.label)}, mark: {q(arrow_mark(edge.token))}{label_arg})"
                )
            groups.append(
                f"#relation-group({q(source_node.label)}, kind: {q(kind)})[\n"
                + "\n".join(targets)
                + "\n]"
            )
        panels.append(
            f"#diagram-panel(title: {q(title + suffix)}, breakable: false)[\n"
            + "\n#v(2pt)\n".join(groups)
            + "\n]"
        )
    return "\n\n".join(panels)

def render_flowchart(block: str, diagram_no: int) -> tuple[str, dict[str, object]]:
    direction, nodes, edges = parse_flowchart(block)
    incoming = {edge.target for edge in edges}
    title = f"图示 {diagram_no} · 关系图"

    chain = chain_edges(nodes, edges)
    mode = "relation"
    if chain and len(nodes) <= 5:
        typst = render_chain(f"图示 {diagram_no} · 词源路径", nodes, chain)
        mode = "chain"
    elif edges:
        typst = render_relation_panels(title, nodes, edges, incoming)
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
        return "```{=typst}\n#part-entry(\"00 前言\")\n```\n"
    if dirname not in VOLUMES:
        return None
    kicker, title, subtitle = VOLUMES[dirname]
    outline_title = dirname.replace("-", " ", 1)
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
    def repl(match: re.Match[str]) -> str:
        heading = match.group(1)
        if heading.startswith("== 第 29 章"):
            return heading
        return f"#pagebreak(weak: true)\n\n{heading}"

    return re.sub(r"(?m)^(== (?:第 \d+ 章|附录 [A-Z])(?:[^\n]*))$", repl, value)


def compact_final_section(value: str) -> str:
    return value.replace(
        "\n=== 全书结束语\n<全书结束语>\n",
        "\n#compact-section-title(\"全书结束语\")\n<全书结束语>\n#set par(leading: 0.76em, spacing: 0.42em)\n",
    )


def postprocess_body(value: str) -> str:
    value = re.sub(r"columns:\s*(\d+),", fraction_columns, value)
    value = tuned_table_columns(value)
    value = value.replace("[来源], [章节],)", "[来源], [章],)")
    value = unwrap_table_figures(value)
    value = re.sub(r"\n#horizontalrule\n\n(?=(?:#volume-page|= ))", "\n", value)
    value = value.replace("#link(", "#link(")
    value = value.replace(
        "\n#horizontalrule\n\n== 二、后缀\n<二后缀>\n",
        "\n#pagebreak(weak: true)\n\n== 二、后缀\n<二后缀>\n",
    )
    value = demote_headings(value)
    value = insert_chapter_breaks(value)
    value = compact_final_section(value)
    imports = (
        '#import "template.typ": part-entry, volume-page, horizontalrule, diagram-panel, d-node, '
        "d-flow, d-down, d-target, relation-group, timeline-date, timeline-entry, timeline-section, "
        "compact-section-title\n\n"
    )
    return imports + value


def write_main() -> None:
    main = f'''#import "template.typ": book

#show: book.with(
  title: {q(TITLE)},
  subtitle: {q(SUBTITLE)},
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
