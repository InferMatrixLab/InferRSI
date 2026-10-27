"""Original editable InferRSI knowledge diagrams, based on the pinned audit tree.

Author configuration: gpt-6.1-sol / xhigh, explicitly configured for this delegated task.
Run with the bundled Python runtime. Requires existing Pillow and CairoSVG.
All output is confined to this script's directory.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import json
import xml.etree.ElementTree as ET

import cairosvg
from PIL import Image, ImageFont

OUT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1600, 1050
BASELINE = "4817f92121df73fd9cd5fb4a319e3c56a68b4a5b"
PALETTE = {
    "ink": "#1e293b", "body": "#526782", "muted": "#7c8da8",
    "panel": "#f6f8fc", "panel_stroke": "#dce5f1",
    "card": "#ffffff", "card_stroke": "#c5d3e8",
    "blue": "#5482ff", "blue_fill": "#edf3ff", "blue_ink": "#2149bc",
    "green": "#37ad70", "green_fill": "#effaf4", "green_ink": "#238051",
    "purple": "#966bd7", "line": "#a9b8cc",
}


@dataclass
class Card:
    y: int
    h: int
    title: str
    lines: list[str]
    style: str = "plain"
    line_height: int = 20


EN = {
    "title": "InferRSI Knowledge Architecture",
    "subtitle": "Canonical sources → build & authorities → retrieval → exact reads & explicit use",
    "top_note": "K0/K1 foundation · K2 operations",
    "heads": ["1 · CANONICAL SOURCES", "2 · BUILD & AUTHORITIES", "3 · RETRIEVAL", "4 · READ & USE"],
    "cards": [
        [
            Card(185, 125, "Complete skill library", ["SKILL.md: name + procedure", "metadata.json: state + applicability", "references/ + cases/: owner-local", "Licenses and source inventories"]),
            Card(326, 120, "Imported catalog sources", ["repo_packs/ + knowledge_packs/", "Existing IDs, tiers, scope and sources", "Contribution · dependency · peer"]),
            Card(462, 147, "Typed source identities", ["Git commit + inspected paths", "Paper version · document snapshot", "Internal run + artifact identity", "Source pin ≠ content revision", "Frozen evidence stays at its owner"]),
            Card(625, 129, "Ownership and qualification", ["hardware/ · frameworks/", "repositories/ · methods/ · workflows/", "State ≠ validation ≠ permission", "Backend scope ≠ compatibility", "Unknown provenance/licenses retained"], "dashed", line_height=17),
        ],
        [
            Card(185, 103, "Stable-ID registry", ["skill-index.json", "Skill IDs → paths + backend", "Separate from generated records"]),
            Card(304, 172, "Source-pinned projection", ["tools/build_skill_index.py", "Fixed source commit + per-file SHA256", "inferrsi.<backend>.skills.*", "kind=knowledge · packaged-skill index", "Imported state belongs to the record", "Projection ≠ content authority"], "blue"),
            Card(492, 145, "Explicit authorities", ["package: installed bundle, read-only", "checkout: selected root, read-only", "store: authorized local candidates", "Create / Update retain immutable history", "Adaptations need a distinct derived ID"]),
            Card(653, 101, "Bundle identity contract", ["Qualified ref = <authority>:<id>", "Metadata + content + resources", "+ dependency revisions → SHA256"], "blue"),
        ],
        [
            Card(185, 125, "Legacy: knowledge search", ["Catalog JSON discovery", "AND substring tokens", "Occurrence count; ties by ID", "Existing repo/backend/tier filters"]),
            Card(326, 145, "Default: Collect", ["Query + metadata filters (reader API)", "Deterministic qualified-identity order", "IDs · revisions · limit · max_bytes", "No-match / omissions / collisions explicit", "Packaged material → record.json"], "green"),
            Card(487, 267, "Two independent opt-ins", ["relevance: separate lexical cue", "Discovery: generated packaged skills", "4 title · 3 desc · 2 tags/applicability", "1 full core; score ↓, then qualified ref", "Ranking → item and byte limits", "Explicit IDs keep members + order", "context_bytes: explicit byte budget", "Whole-file core + required references", "Optional owner files selected by cue", "Stale projection → index_unavailable"], "green"),
        ],
        [
            Card(185, 125, "Exact-revision access", ["read(ref, revision) / resource(...)", "Full dependency-closed Bundle", "Ambiguous identity is an error", "Unavailable old bytes never use latest"]),
            Card(326, 187, "Complete context contract", ["Full canonical SKILL.md", "+ declared refs + provenance readsets", "+ required licenses and notices", "Exact UTF-8 resource-body bytes", "Required set over budget: omit context", "Mandatory instructions never truncated", "Other links still need exact reads"], "blue"),
            Card(529, 101, "Inspectable returned material", ["Ref + revision + paths + SHA256", "Sources · attribution · limitations", "Whole resources + explicit omissions"]),
            Card(646, 108, "Agent chooses explicit use", ["Goal + authorization + applicability", "Read before acting; honor limitations", "Reading never executes or promotes"], "dashed"),
        ],
    ],
    "evidence_head": "5 · RETAINED EVIDENCE & REVIEWED MAINTENANCE",
    "bottom": [
        ("Frozen evidence", "Plans · results · patches · validators"),
        ("Reference Matrix", "Sources · inspected scope · extraction"),
        ("SearchSpace Matrix", "Resource × optimization-stage coverage"),
        ("Reviewed repository changes", "Content + matrices + projection refresh"),
    ],
    "reference_note": "Frozen evidence: read-only references.",
    "review_note": "Reviewed content + matrices; store candidates are not repository coverage.",
    "legend": ["Contract", "Retrieval", "Data flow", "Reference / review"],
    "footer": "InferRSI · source 4817f92121df · no automatic execution or promotion",
}

ZH = {
    "title": "InferRSI 知识库架构",
    "subtitle": "规范内容源 → 构建与权威边界 → 检索 → 精确修订读取与显式使用",
    "top_note": "K0/K1 内容基础 · K2 读写操作",
    "heads": ["1 · 规范内容源", "2 · 构建与权威边界", "3 · 检索", "4 · 读取与使用"],
    "cards": [
        [
            Card(185, 125, "完整技能库", ["SKILL.md：名称、描述与完整步骤", "metadata.json：溯源、状态与适用性", "references/ 与 cases/：归属技能本地", "保留许可证与来源清单"]),
            Card(326, 120, "导入的目录来源", ["repo_packs/ + knowledge_packs/", "保留既有 ID、层级、范围与来源", "贡献对象 · 依赖对象 · 同类参考"]),
            Card(462, 147, "按类型保存来源身份", ["Git 提交与已检查路径", "论文版本、文档版本或快照", "内部运行与产物身份", "来源版本 ≠ 本地内容修订", "原始证据保留于冻结产物的所有者"]),
            Card(625, 129, "内容归属与验证边界", ["硬件 / 框架 / 仓库 / 方法 / 工作流", "状态 ≠ 实测验证 ≠ 使用授权", "后端适用范围 ≠ 兼容性认证", "未知来源与许可证保持未知"], "dashed"),
        ],
        [
            Card(185, 103, "稳定 ID 注册表", ["skill-index.json", "技能 ID → 分类路径与 backend", "与生成的目录记录是不同对象"]),
            Card(304, 172, "固定来源的生成投影", ["tools/build_skill_index.py", "固定来源提交与每个文件的 SHA256", "inferrsi.<backend>.skills.*", "kind=knowledge；packaged-skill 索引", "imported 描述目录记录自身状态", "生成投影 ≠ 内容权威"], "blue"),
            Card(492, 145, "显式选择三类权威", ["package：已安装内容，只读", "checkout：指定技能根目录，只读", "store：获授权的本地候选内容", "Create / Update 保留不可变历史", "改编须使用不同 ID 并记录派生来源"]),
            Card(653, 101, "完整包身份契约", ["限定引用：<authority>:<id>", "元数据、正文、资源字节", "+ 依赖修订 → SHA256 内容修订"], "blue"),
        ],
        [
            Card(185, 125, "既有入口：knowledge search", ["对目录 JSON 进行发现检索", "AND 子串匹配", "按出现次数排序，再按 ID 排序", "保留 repo/backend/tier 等筛选"]),
            Card(326, 145, "默认入口：Collect", ["查询与元数据筛选（Reader API）", "默认按限定身份确定性排序", "ID、修订、条数与 max_bytes 上限", "显式报告无匹配、遗漏和身份冲突", "包目录的 material 返回 record.json"], "green"),
            Card(487, 267, "两项相互独立的可选能力", ["relevance：独立的词法提示", "发现范围仅限生成的已打包技能", "标题 4、描述 3、标签/适用范围 2", "完整核心 1；分数降序后按限定引用", "排序后施加条数与字节上限", "显式 ID 保留成员与调用者顺序", "context_bytes：显式字节预算", "完整核心与强制引用按整文件返回", "可选本地资源按提示选择", "投影过期 → index_unavailable"], "green"),
        ],
        [
            Card(185, 125, "读取精确内容修订", ["read(ref, revision) / resource(...)", "读取依赖闭合的完整 Bundle", "未限定的歧义身份直接报错", "旧字节不可用时不替换为最新内容"]),
            Card(326, 187, "完整上下文契约", ["完整的规范 SKILL.md", "+ 已声明引用与来源检查材料", "+ 强制保留的许可证和通知", "按 UTF-8 资源正文字节计量", "必需资源超预算：仅省略上下文", "强制指令从不截断", "其他链接仍须按精确修订继续读取"], "blue"),
            Card(529, 101, "可检查的返回材料", ["引用、修订、路径与 SHA256", "来源、署名和适用限制", "完整资源及显式遗漏原因"]),
            Card(646, 108, "Agent 显式决定使用", ["结合目标、授权与适用条件", "先读取，再按适用限制行动", "读取不会执行内容或提升候选状态"], "dashed"),
        ],
    ],
    "evidence_head": "5 · 冻结证据与经过审查的维护",
    "bottom": [
        ("冻结的原始证据", "计划、结果、补丁与验证器"),
        ("Reference Matrix", "来源、已检查范围与提取内容"),
        ("SearchSpace Matrix", "资源 × 优化阶段的覆盖情况"),
        ("经过审查的仓库变更", "规范内容、两个矩阵与投影刷新"),
    ],
    "reference_note": "冻结证据只作引用；运行时不改写。",
    "review_note": "规范内容与双矩阵经审查后变更；store 候选不等于仓库覆盖。",
    "legend": ["契约", "检索", "数据流", "引用 / 审查"],
    "footer": "InferRSI · 来源 4817f92121df · 不自动执行或提升候选状态",
}


def make_svg(locale: str, copy: dict) -> tuple[str, dict]:
    chinese = locale == "zh-CN"
    family = "Microsoft YaHei, Noto Sans SC, Segoe UI, sans-serif" if chinese else "Segoe UI, Arial, sans-serif"
    normal = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc" if chinese else "C:/Windows/Fonts/segoeui.ttf", 15)
    bold = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc" if chinese else "C:/Windows/Fonts/segoeuib.ttf", 16)
    pieces: list[str] = []
    audit = {"locale": locale, "width": WIDTH, "height": HEIGHT, "baseline": BASELINE,
             "author_model": "gpt-6.1-sol", "author_reasoning_effort": "xhigh", "text_checks": []}

    def rect(x, y, w, h, fill, stroke, radius=9, dashed=False):
        dash = ' stroke-dasharray="4 4"' if dashed else ''
        pieces.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.25"{dash}/>')

    def text(x, y, value, size=15, color=None, weight=400, anchor="start", spacing=None):
        ls = f' letter-spacing="{spacing}"' if spacing else ''
        pieces.append(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color or PALETTE["body"]}"{ls}>{escape(value)}</text>')

    def path(d, color, dashed=False, marker=None, width=1.5):
        dash = ' stroke-dasharray="5 5"' if dashed else ''
        end = f' marker-end="url(#{marker})"' if marker else ''
        pieces.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash}{end}/>')

    def card(x, w, item: Card):
        special = item.style
        stroke = PALETTE["blue"] if special == "blue" else PALETTE["green"] if special == "green" else PALETTE["card_stroke"]
        fill = PALETTE["blue_fill"] if special == "blue" else "#ffffff"
        rect(x, item.y, w, item.h, fill, stroke, dashed=special == "dashed")
        title_color = PALETTE["blue_ink"] if special == "blue" else PALETTE["green_ink"] if special == "green" else PALETTE["ink"]
        text(x + 16, item.y + 27, item.title, 16, title_color, 600)
        title_width = bold.getlength(item.title)
        assert title_width <= w - 30, (locale, item.title, title_width, w)
        for i, line in enumerate(item.lines):
            measured = normal.getlength(line)
            assert measured <= w - 30, (locale, item.title, line, measured, w)
            baseline = item.y + 48 + item.line_height * i
            assert baseline + 4 <= item.y + item.h - 9, (item.title, baseline, item.y + item.h)
            text(x + 16, baseline, line)
        audit["text_checks"].append({"title": item.title, "line_count": len(item.lines), "title_width": round(title_width, 2), "available_width": w - 30})

    pieces.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc" xml:lang="{locale}">')
    pieces.append(f'<title id="title">{escape(copy["title"])}</title>')
    pieces.append('<desc id="desc">Canonical sources feed source-pinned generated projections and explicit read/write authorities. Legacy search, default Collect and optional lexical selection/context remain separate. Exact-revision reads return complete required resources; the agent decides authorized use. Frozen evidence and reviewed matrices retain their ownership.</desc>')
    pieces.append('<defs><marker id="flow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#5482ff"/></marker><marker id="reference" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#966bd7"/></marker><marker id="review" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#7c8da8"/></marker></defs>')
    pieces.append('<rect width="1600" height="1050" fill="#ffffff"/>')
    text(56, 61, copy["title"], 31, PALETTE["ink"], 650)
    text(56, 94, copy["subtitle"], 16)
    text(1544, 59, copy["top_note"], 14, PALETTE["muted"], anchor="end")
    path("M56 113 H1544", PALETTE["panel_stroke"], width=1.2)

    columns = [(56, 330), (414, 362), (804, 358), (1190, 354)]
    for index, ((x, w), heading, cards) in enumerate(zip(columns, copy["heads"], copy["cards"])):
        pieces.append(f'<g id="column-{index + 1}">')
        rect(x, 134, w, 642, PALETTE["green_fill"] if index == 2 else PALETTE["panel"], "#b2e5c8" if index == 2 else PALETTE["panel_stroke"], radius=12)
        text(x + 20, 164, heading, 14, PALETTE["green_ink"] if index == 2 else PALETTE["muted"], 600, spacing=None if chinese else 1.1)
        for item in cards:
            card(x + 20, w - 40, item)
        pieces.append('</g>')

    for start, end in [(386, 414), (776, 804), (1162, 1190)]:
        path(f"M{start + 2} 423 H{end - 4}", PALETTE["blue"], marker="flow", width=1.7)

    path("M232 884 V821 H216 V778", PALETTE["purple"], dashed=True, marker="reference")
    text(257, 826, copy["reference_note"], 15, PALETTE["purple"])
    path("M1366 884 V856 H594 V778", PALETTE["muted"], dashed=True, marker="review")
    text(660, 848, copy["review_note"], 15, PALETTE["muted"])

    pieces.append('<g id="evidence-and-maintenance">')
    rect(56, 884, 1488, 118, "#fafbfe", PALETTE["panel_stroke"], radius=12)
    text(76, 912, copy["evidence_head"], 14, PALETTE["muted"], 600, spacing=None if chinese else 1.1)
    for x, w, (title, detail) in zip([76, 436, 796, 1156], [344, 344, 344, 368], copy["bottom"]):
        rect(x, 928, w, 56, "#ffffff", PALETTE["card_stroke"], radius=8)
        text(x + 15, 950, title, 16, PALETTE["ink"], 600)
        text(x + 15, 972, detail, 14)
    pieces.append('</g>')

    rect(56, 1021, 14, 11, PALETTE["blue_fill"], PALETTE["blue"], radius=2)
    text(80, 1032, copy["legend"][0], 14)
    rect(184, 1021, 14, 11, PALETTE["green_fill"], PALETTE["green"], radius=2)
    text(208, 1032, copy["legend"][1], 14)
    path("M320 1027 H354", PALETTE["blue"], width=1.7)
    text(365, 1032, copy["legend"][2], 14)
    path("M482 1027 H516", PALETTE["purple"], dashed=True)
    text(527, 1032, copy["legend"][3], 14)
    text(1544, 1032, copy["footer"], 14, PALETTE["muted"], anchor="end")
    pieces.append('</svg>')
    svg = "\n".join(pieces) + "\n"
    ET.fromstring(svg)
    return svg, audit


def main():
    audits = []
    for locale, copy in [("en", EN), ("zh-CN", ZH)]:
        svg, audit = make_svg(locale, copy)
        stem = OUT / f"inferrsi-knowledge-architecture.{locale}"
        svg_path = stem.with_suffix(f".{locale}.svg")
        png_path = stem.with_suffix(f".{locale}.png")
        svg_path.write_text(svg, encoding="utf-8", newline="\n")
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png_path), output_width=3200, output_height=2100)
        with Image.open(png_path) as rendered:
            assert rendered.size == (3200, 2100)
            assert rendered.getpixel((0, 0))[:3] == (255, 255, 255)
        audit["svg"] = svg_path.name
        audit["png"] = png_path.name
        audit["render_size"] = [3200, 2100]
        audits.append(audit)
        print(f"Created {svg_path.name} and {png_path.name}")
    (OUT / "layout-checks.json").write_text(json.dumps(audits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
