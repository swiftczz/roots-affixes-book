// Refined academic book template for "词根词缀的故事".

#import "@preview/fletcher:0.5.8" as fletcher

// Body CJK font stacks intentionally keep Latin glyphs in the same family so
// mixed Chinese/Latin inline text does not disturb line height.
#let latin-serif = ("Iowan Old Style", "Libertinus Serif", "New Computer Modern", "STIX Two Text", "Apple Symbols")
#let cjk-serif = ("New Computer Modern", "Songti SC", "LiSong Pro", "STSong", "STIX Two Text", "Apple Symbols")
#let cjk-kai = ("Kaiti SC", "STKaiti", "Kai", "STIX Two Text", "Apple Symbols")
#let cjk-sans = ("PingFang SC", "Heiti SC", "STHeiti", "Apple Symbols")
#let mono-font = ("Menlo", "Maple Mono", "FiraCode Nerd Font Mono", "Courier New")

#let paper = rgb("#fbfaf6")
#let paper-deep = rgb("#f4efe4")
#let panel-bg = rgb("#fcfdfa")
#let ink = rgb("#272724")
#let muted = rgb("#73786f")
#let hairline = rgb("#d9ded7")
#let accent = rgb("#4f7f83")
#let accent-dark = rgb("#285963")
#let accent-soft = rgb("#e8f2ef")
#let gold = rgb("#b9903e")
#let gold-soft = rgb("#fbf0d8")
#let plum = rgb("#8f6f68")
#let plum-soft = rgb("#f7eaea")

#let plain-text(it) = {
  if type(it) == str { it } else if type(it) != content { "" } else if it.has("text") { it.text } else if it.has(
    "children",
  ) { it.children.fold("", (acc, child) => acc + plain-text(child)) } else if it.has("body") {
    plain-text(it.body)
  } else { "" }
}

#let line-text(value, size: 10pt, weight: "regular", fill: ink, font: cjk-kai) = {
  set text(font: font)
  set par(first-line-indent: 0pt, justify: false, leading: 0.58em, spacing: 0pt)
  let lines = value.split("\n")
  for (i, line) in lines.enumerate() {
    if i > 0 { linebreak() }
    text(size: size, weight: weight, fill: fill)[#line]
  }
}

#let cover-rule(width: 72%, stroke: 0.75pt + accent) = {
  line(length: width, stroke: stroke)
}

#let horizontalrule = {
  v(1em, weak: true)
  line(length: 100%, stroke: 0.5pt + hairline)
  v(1em, weak: true)
}

#let th(body) = table.cell(fill: paper-deep)[#text(weight: "semibold")[#body]]


#let part-entry(title) = {
  heading(level: 1, outlined: true)[#title]
}

#let volume-page(kicker, title, subtitle: none, outline-title: none) = {
  page(header: none, footer: [])[
    #part-entry(if outline-title == none { title } else { outline-title })
    #align(center + horizon)[
      #text(font: latin-serif, size: 10pt, fill: muted)[ROOTS / AFFIXES]
      #v(0.8em)
      #text(font: cjk-sans, size: 10pt, weight: "semibold", fill: accent-dark)[#kicker]
      #v(1.2em)
      #cover-rule(width: 34%, stroke: 0.7pt + gold)
      #v(1.3em)
      #text(font: cjk-serif, size: 27pt, weight: "semibold", fill: ink)[#title]
      #if subtitle != none [
        #v(0.9em)
        #text(font: cjk-kai, size: 11pt, fill: muted)[#subtitle]
      ]
    ]
  ]
}

#let d-node(label, kind: "node") = {
  let fill = if kind == "root" { gold-soft } else if kind == "warn" { plum-soft } else { accent-soft }
  let stroke-color = if kind == "root" { gold } else if kind == "warn" { plum } else { accent }
  let text-color = if kind == "root" { rgb("#725617") } else if kind == "warn" { plum } else { accent-dark }
  box(
    width: 100%,
    inset: (x: 6pt, y: 4.8pt),
    radius: 5pt,
    fill: fill,
    stroke: 0.7pt + stroke-color,
  )[
    #align(center)[#line-text(label, size: 10pt, fill: text-color)]
  ]
}

#let d-flow(mark: "→", label: none, dotted: false) = {
  align(center + horizon)[
    #box(width: 100%)[
      #line(length: 100%, stroke: (if dotted { 0.5pt + muted } else { 0.55pt + accent }))
      #place(center, dy: -4.8pt)[
        #box(inset: (x: 3pt, y: 0.5pt), fill: panel-bg)[
          #text(font: latin-serif, size: 10pt, fill: accent-dark)[#mark]
        ]
      ]
    ]
    #if label != none [
      #v(1.5pt)
      #line-text(label, size: 10pt, fill: muted)
    ]
  ]
}

#let d-down(mark: "↓", label: none) = {
  block(width: 100%, above: 1.6pt, below: 1.6pt)[
    #align(center)[
      #text(font: latin-serif, size: 10.5pt, fill: accent-dark)[#mark]
      #if label != none [
        #linebreak()
        #line-text(label, size: 10pt, fill: muted)
      ]
    ]
  ]
}

#let d-target(label, edge: none, mark: "→", kind: "node") = {
  let border = if kind == "root" { gold } else if mark == "⇢" or mark == "⇄" { plum } else { accent }
  block(width: 100%, inset: 0pt, above: 2.5pt, below: 2.5pt)[
    #table(
      columns: (16pt, 1fr),
      stroke: none,
      column-gutter: 4pt,
      align: top,
      [#text(font: latin-serif, size: 10pt, fill: border)[#mark]],
      [
        #set par(first-line-indent: 0pt, justify: false, leading: 0.5em, spacing: 0pt)
        #if edge != none [
          #text(font: cjk-kai, size: 10pt, fill: muted)[#edge]
          #linebreak()
        ]
        #line-text(label, size: 10pt, fill: ink)
        #v(2pt)
        #line(length: 100%, stroke: 0.35pt + hairline)
      ],
    )
  ]
}

// Fletcher-based graph primitives: real node-and-edge diagrams laid out
// left-to-right (rank = column), replacing the flattened relation lists.
#let fnode(pos, label, kind: "node", w: auto, size: 8pt) = {
  let fill = if kind == "root" { gold-soft } else if kind == "note" { plum-soft } else { accent-soft }
  let stroke-color = if kind == "root" { gold } else if kind == "note" { plum } else { accent }
  let text-color = if kind == "root" { rgb("#725617") } else if kind == "note" { rgb("#6d4a42") } else {
    accent-dark
  }
  let dash = if kind == "note" { "dashed" } else { none }
  fletcher.node(
    pos,
    align(center)[#line-text(label, size: size, fill: text-color)],
    width: w,
    fill: fill,
    stroke: (paint: stroke-color, thickness: 0.65pt, dash: dash),
    corner-radius: 4pt,
    inset: 3.5pt,
  )
}

#let fedge(from, to, kind: "solid", label: none, bend: 0deg) = {
  let spec = (
    solid: (accent, none, (none, "head")),
    dashed: (plum, "dashed", (none, "head")),
    plain: (accent, none, (none, none)),
    faint: (muted, "dotted", (none, none)),
    bidir: (plum, none, ("head", "head")),
    bidir-dashed: (plum, "dashed", ("head", "head")),
  ).at(kind)
  let label-args = if label == none { (:) } else {
    (
      label: box(inset: (x: 1pt))[#line-text(label, size: 7.5pt, fill: rgb("#5c635b"))],
      label-fill: panel-bg,
      label-sep: 0pt,
    )
  }
  fletcher.edge(
    from,
    to,
    marks: spec.at(2),
    stroke: (paint: spec.at(0), thickness: 0.55pt, dash: spec.at(1)),
    bend: bend,
    ..label-args,
  )
}

#let f-diagram(spacing: (7mm, 4mm), ..args) = {
  set par(justify: false)
  fletcher.diagram(
    spacing: spacing,
    node-outset: 1pt,
    mark-scale: 68%,
    ..args,
  )
}

// Cover mark: abstract etymology tree drawn with bare lines and small pills.
#let cover-mark() = {
  box(width: 44mm, height: 44mm)[
    #place(dx: 21mm, dy: 4mm, line(start: (0mm, 0mm), end: (0mm, 31mm), stroke: 0.85pt + accent-dark))
    #place(dx: 21mm, dy: 12mm, line(start: (0mm, 0mm), end: (-13mm, -6mm), stroke: 0.85pt + accent-dark))
    #place(dx: 21mm, dy: 12mm, line(start: (0mm, 0mm), end: (13mm, -6mm), stroke: 0.85pt + accent-dark))
    #place(dx: 21mm, dy: 25mm, line(start: (0mm, 0mm), end: (-12mm, 8mm), stroke: 0.85pt + accent-dark))
    #place(dx: 21mm, dy: 25mm, line(start: (0mm, 0mm), end: (12mm, 8mm), stroke: 0.85pt + accent-dark))
    #for (x, y, label, tone) in (
      (4mm, 3mm, "PIE", "root"),
      (31mm, 3mm, "Lat.", "leaf"),
      (1mm, 31mm, "Gr.", "leaf"),
      (29mm, 31mm, "Eng.", "leaf"),
      (14mm, 36mm, "root", "root"),
    ) {
      let fill = if tone == "root" { gold-soft } else { accent-soft }
      let stroke = if tone == "root" { gold } else { accent }
      place(dx: x, dy: y, box(
        inset: (x: 4pt, y: 2.2pt),
        radius: 6pt,
        fill: fill,
        stroke: 0.55pt + stroke,
      )[#text(font: latin-serif, size: 10pt, fill: accent-dark)[#label]])
    }
  ]
}

#let relation-group(source, kind: "root", body) = {
  block(width: 100%, inset: 0pt, below: 5pt, breakable: false)[
    #table(
      columns: (0.76fr, 1.75fr),
      stroke: none,
      column-gutter: 8pt,
      align: horizon,
      d-node(source, kind: kind),
      body,
    )
  ]
}

#let diagram-panel(title: "图示", breakable: false, body) = {
  block(
    width: 100%,
    inset: (x: 9pt, y: 8pt),
    radius: 4pt,
    fill: panel-bg,
    stroke: (left: 1.4pt + accent, rest: 0.45pt + hairline),
    breakable: breakable,
    above: 0.8em,
    below: 0.8em,
  )[
    #set par(first-line-indent: 0pt, justify: false, spacing: 0pt)
    #context [#metadata((title: title, page: here().page()))<diagram-panel-loc>]
    #text(font: cjk-kai, size: 10pt, weight: "semibold", fill: accent-dark)[#title]
    #v(6pt)
    #body
  ]
}

#let timeline-date(value) = box(
  width: 100%,
  inset: (x: 4pt, y: 3pt),
  radius: 3pt,
  fill: gold-soft,
  stroke: 0.5pt + gold,
)[#align(center)[#line-text(value, size: 10pt, fill: rgb("#6f561b"))]]

#let timeline-entry(value) = {
  block(width: 100%, inset: (left: 8pt), stroke: (left: 0.6pt + accent))[#line-text(value, size: 10pt)]
}

#let timeline-section(value) = {
  block(width: 100%, inset: (x: 5pt, y: 3pt), fill: accent-soft, radius: 3pt)[
    #text(font: cjk-kai, size: 10pt, weight: "semibold", fill: accent-dark)[#value]
  ]
}

#let book(title: "词根词缀的故事", subtitle: none, author: none, body) = {
  set document(
    title: title,
    author: if author == none { () } else { (author,) },
  )
  set page(
    paper: "iso-b5",
    fill: paper,
    margin: (left: 20mm, right: 18mm, top: 18mm, bottom: 18mm),
    numbering: none,
    header: none,
  )
  set text(
    font: cjk-serif,
    size: 10pt,
    lang: "zh",
    region: "cn",
    fill: ink,
  )
  set par(
    justify: true,
    leading: 1em,
    spacing: 1.1em,
    first-line-indent: (amount: 1.8em, all: true),
  )
  set heading(outlined: true, numbering: none)
  set table(
    inset: (x: 4.4pt, y: 3.8pt),
    stroke: 0.45pt + hairline,
    align: left + horizon,
  )
  set list(indent: 1.2em, body-indent: 0.6em)
  set enum(indent: 1.2em, body-indent: 0.6em)

  show list: set par(first-line-indent: 0pt)
  show enum: set par(first-line-indent: 0pt)
  show terms: set par(first-line-indent: 0pt)
  show outline: set par(first-line-indent: 0pt)

  show emph: it => text(size: 1em, fill: rgb("#303734"))[#it.body]
  show strong: it => text(size: 1em, fill: rgb("#30302c"))[#it.body]
  show raw.where(block: false): it => text(font: cjk-serif, size: 10pt, fill: accent-dark)[#it.text]

  show heading.where(level: 1): it => none
  show heading.where(level: 5): it => {
    block(width: 100%, above: 1em, below: 1em, sticky: true)[
      #set par(first-line-indent: 0pt, justify: false)
      #text(font: cjk-serif, size: 11pt, weight: "semibold", fill: rgb("#4f524d"))[#it.body]
    ]
  }

  show outline.entry.where(level: 1): it => {
    v(0.38em)
    text(font: cjk-sans, size: 10.8pt, weight: "semibold", fill: ink)[#it]
  }
  show outline.entry.where(level: 2): it => {
    v(0.08em)
    text(font: cjk-kai, size: 10pt, fill: rgb("#4f5550"))[#it]
  }

  show heading.where(level: 2): it => {
    let label-text = plain-text(it.body)
    let kicker = if label-text.starts-with("附录") { "APPENDIX" } else if label-text.starts-with("前言") {
      "PREFACE"
    } else { "ETYMOLOGY CHAPTER" }
    block(width: 100%, above: 1em, below: 1em, sticky: true)[
      #set par(first-line-indent: 0pt, justify: false, leading: 0.6em)
      #text(font: latin-serif, size: 10pt, fill: gold)[#kicker]
      #v(0.5em)
      #text(font: cjk-sans, size: 22pt, weight: "semibold", fill: ink)[#it.body]
      #v(0.5em)
      #line(length: 30%, stroke: 1pt + gold)
    ]
  }
  show heading.where(level: 3): it => {
    block(width: 100%, above: 1em, below: 1em, sticky: true)[
      #set par(first-line-indent: 0pt, justify: false)
      #text(font: cjk-serif, size: 13pt, weight: "semibold", fill: accent-dark)[#it.body]
    ]
  }
  show heading.where(level: 4): it => {
    block(width: 100%, above: 1em, below: 1em, sticky: true)[
      #set par(first-line-indent: 0pt, justify: false)
      #text(font: cjk-serif, size: 12pt, weight: "semibold", fill: rgb("#474c48"))[#it.body]
    ]
  }
  show quote: it => block(
    width: 100%,
    inset: (left: 12pt, right: 12pt, top: 6pt, bottom: 6pt),
    radius: 4pt,
    fill: rgb("#f7f3ea"),
    stroke: (left: 2pt + gold, rest: 0.4pt + rgb("#e5dcc8")),
    breakable: true,
    above: 1em,
    below: 1em,
  )[
    #set text(font: cjk-kai, size: 10pt, fill: rgb("#42413b"))
    #set par(first-line-indent: 0pt, justify: true, leading: 0.8em, spacing: 1em)
    #it.body
  ]
  show table: it => {
    set text(font: cjk-kai, size: 10pt)
    set par(first-line-indent: 0pt, justify: false, leading: 0.6em)
    block(width: 100%, above: 0.8em, below: 0.8em)[#it]
  }
  show raw.where(block: true): it => block(
    width: 100%,
    inset: 8pt,
    radius: 4pt,
    fill: rgb("#f2f4ef"),
    stroke: 0.5pt + hairline,
    above: 0.8em,
    below: 0.8em,
  )[
    #set text(font: mono-font, size: 10pt)
    #it
  ]
  show figure: it => {
    block(width: 100%, breakable: true, above: 0.8em, below: 0.8em)[#align(center)[#it]]
  }

  // ---- Cover ----
  // Double hairline frame, inset from the page edge (content origin sits at
  // the 20mm/18mm margins, hence the negative offsets).
  place(top + left, dx: -10mm, dy: -8mm, rect(width: 156mm, height: 230mm, stroke: 0.6pt + accent-dark))
  place(top + left, dx: -7.5mm, dy: -5.5mm, rect(width: 151mm, height: 225mm, stroke: 0.45pt + gold))
  block(width: 100%, height: 100%)[
    #set align(center)
    #v(14mm)
    #text(font: latin-serif, size: 10pt, fill: gold, tracking: 3.5pt)[ETYMOLOGY · ROOTS · AFFIXES]
    #v(1fr)
    #cover-mark()
    #v(1.7em)
    #cover-rule(width: 62%, stroke: 0.75pt + accent-dark)
    #v(1.55em)
    #text(font: cjk-serif, size: 32pt, weight: "semibold", fill: ink)[#title]
    #if subtitle != none [
      #v(0.85em)
      #text(font: cjk-kai, size: 12.5pt, fill: muted)[#subtitle]
    ]
    #v(1.3em)
    #cover-rule(width: 30%, stroke: 0.7pt + gold)
    #v(1fr)
    #if author != none [
      #text(font: cjk-serif, size: 12.5pt, weight: "semibold", fill: ink, tracking: 2pt)[#author 著]
      #v(3.5mm)
    ]
    #cover-rule(width: 16%, stroke: 0.6pt + accent-dark)
    #v(9mm)
  ]

  pagebreak()
  block(width: 100%, below: 0.8em)[
    #set par(first-line-indent: 0pt, justify: false)
    #text(font: cjk-serif, size: 24pt, weight: "semibold", fill: ink)[目录]
    #v(0.45em)
    #line(length: 42%, stroke: 0.7pt + accent)
  ]
  outline(title: none, depth: 2, indent: auto)
  pagebreak()
  set page(
    paper: "iso-b5",
    fill: paper,
    margin: (left: 20mm, right: 18mm, top: 18mm, bottom: 18mm),
    numbering: "1",
    number-align: center,
    header: context {
      let chapters = query(heading.where(level: 2))
      let on-page = chapters.filter(h => h.location().page() == here().page())
      let before-page = chapters.filter(h => h.location().page() < here().page())
      let current = if on-page.len() > 0 { on-page.first() } else if before-page.len() > 0 {
        before-page.last()
      } else { none }
      block(width: 100%)[
        #grid(
          columns: (1fr, auto),
          column-gutter: 6mm,
          align(left)[#text(font: cjk-kai, size: 9.5pt, fill: muted)[#if current != none [#current.body]]],
          align(right)[#text(font: cjk-kai, size: 9.5pt, fill: muted)[#title]],
        )
        #v(2pt)
        #line(length: 100%, stroke: 0.35pt + hairline)
      ]
    },
  )
  counter(page).update(1)

  body
}
