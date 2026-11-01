"""Validate one AMC audience-exposure CSV and build an offline dashboard.

Uses only the Python standard library. Run `inspect` before `build` in the
Skill workflow; `build` validates the same input again before writing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from html import escape
from pathlib import Path


SP_ONLY = "Exposed - Sp. Ads"
DSP_ONLY = "Exposed - DSP"
BOTH = "Exposed - DSP & Sp. Ads"
UNEXPOSED = "Not Exposed"
CATEGORIES = (SP_ONLY, DSP_ONLY, BOTH, UNEXPOSED)
REQUIRED = ("exposure", "segment_id", "segment_name", "user_count")
TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "dashboard_template.html"


class InputError(ValueError):
    pass


def read_csv(path: Path) -> dict:
    if path.suffix.lower() != ".csv":
        raise InputError("需要上传 CSV 表格；当前文件不是 .csv。")
    if not path.is_file():
        raise InputError(f"找不到上传的 CSV：{path}")
    raw = path.read_bytes()
    if not raw:
        raise InputError("CSV 文件为空。")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("CSV 必须为 UTF-8 编码（允许 BOM）。") from exc

    reader = csv.reader(text.splitlines(keepends=True), strict=True)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise InputError("CSV 缺少表头。") from exc
    except csv.Error as exc:
        raise InputError(f"CSV 表头格式错误：{exc}") from exc
    header = [cell.strip() for cell in header]
    if len(header) != len(set(header)):
        raise InputError("CSV 表头存在重复字段。")
    missing = [field for field in REQUIRED if field not in header]
    if missing:
        raise InputError("CSV 缺少必需字段：" + ", ".join(missing))
    index = {name: header.index(name) for name in REQUIRED}

    segments: dict[str, dict] = defaultdict(lambda: {"name": "", **{c: None for c in CATEGORIES}})
    present: set[str] = set()
    blank_rows = 0
    accepted_rows = 0
    try:
        for line_number, cells in enumerate(reader, 2):
            if len(cells) != len(header):
                raise InputError(f"第 {line_number} 条数据的列数与表头不一致。")
            row = {field: cells[position].strip() for field, position in index.items()}
            category = row["exposure"]
            if category not in CATEGORIES:
                raise InputError(f"第 {line_number} 条数据的 exposure 不受支持：{category!r}")
            if not re.fullmatch(r"[0-9]+", row["user_count"]):
                raise InputError(f"第 {line_number} 条数据的 user_count 必须是非负整数。")
            segment_id, name = row["segment_id"], row["segment_name"]
            if not segment_id and not name:
                blank_rows += 1
                continue
            if not segment_id or not name:
                raise InputError(f"第 {line_number} 条数据的人群 ID 和名称必须同时有值。")
            item = segments[segment_id]
            if item["name"] and item["name"] != name:
                raise InputError(f"人群 ID {segment_id!r} 对应了不同的名称。")
            if item[category] is not None:
                raise InputError(f"人群 ID {segment_id!r} 的 {category!r} 类别重复。")
            item["name"] = name
            item[category] = int(row["user_count"])
            present.add(category)
            accepted_rows += 1
    except csv.Error as exc:
        raise InputError(f"CSV 引号或分隔符格式错误：{exc}") from exc

    if not accepted_rows:
        raise InputError("CSV 没有可用的人群记录。")
    has_dsp = DSP_ONLY in present or BOTH in present
    needed = CATEGORIES if has_dsp else (SP_ONLY, UNEXPOSED)
    ranked: list[dict] = []
    incomplete: list[dict] = []
    for segment_id, item in segments.items():
        base = {"id": segment_id, "name": item["name"]}
        if any(item[category] is None for category in needed):
            incomplete.append({**base, "missing": [c for c in needed if item[c] is None]})
            continue
        denominator = sum(item[category] for category in needed)
        if denominator == 0:
            incomplete.append({**base, "missing": ["zero denominator"]})
            continue
        sp_only = item[SP_ONLY]
        dsp_only = item[DSP_ONLY] if has_dsp else None
        both = item[BOTH] if has_dsp else None
        sp_exposed = sp_only + (both if both is not None else 0)
        combined = sp_only + dsp_only + both if has_dsp else None
        ranked.append({
            **base,
            "sp_exposed": sp_exposed,
            "total": denominator,
            "sp_rate": sp_exposed / denominator,
            "dsp_only_rate": dsp_only / denominator if has_dsp else None,
            "both_rate": both / denominator if has_dsp else None,
            "combined_rate": combined / denominator if has_dsp else None,
            "rank_rate": (combined if has_dsp else sp_exposed) / denominator,
        })
    if not ranked:
        raise InputError("没有可计算触达率的人群：所需曝光类别缺失或分母均为零。")
    ranked.sort(key=lambda item: (-item["rank_rate"], -item["sp_exposed"], item["id"]))
    for rank, item in enumerate(ranked, 1):
        item["rank"] = rank
    incomplete.sort(key=lambda item: (item["name"].casefold(), item["id"]))
    for item in incomplete:
        item.update(rank=None, sp_exposed=None, total=None, sp_rate=None,
                    dsp_only_rate=None, both_rate=None, combined_rate=None)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows_accepted": accepted_rows,
        "blank_rows_excluded": blank_rows,
        "categories_present": [c for c in CATEGORIES if c in present],
        "mode": "four-category" if has_dsp else "sponsored-ads-only",
        "ranked": ranked,
        "incomplete": incomplete,
    }


def inspection(result: dict) -> dict:
    return {
        "status": "valid",
        "source_sha256": result["sha256"],
        "mode": result["mode"],
        "categories_present": result["categories_present"],
        "rows_accepted": result["rows_accepted"],
        "audiences_ranked": len(result["ranked"]),
        "audiences_incomplete": len(result["incomplete"]),
        "blank_rows_excluded": result["blank_rows_excluded"],
        "top_audiences": [
            {"rank": x["rank"], "segment_id": x["id"], "rate": x["rank_rate"]}
            for x in result["ranked"][:10]
        ],
    }


def build_html(result: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    expected = ("__ROWS__", "__DATA__", "__HAS_DSP__", "__RANK_NOTE__",
                "__FORMULA_NOTE__", "__TOTAL__", "__DEFAULT_COUNT__",
                "__BLANK_NOTE__", "__INCOMPLETE_NOTE__")
    if any(template.count(token) != 1 for token in expected):
        raise ValueError("包内看板模板的占位符不完整或重复。")
    has_dsp = result["mode"] == "four-category"
    audiences = result["ranked"] + result["incomplete"]

    def rate_cell(rate: float | None, label: str, heat: bool = False, tone: str = "") -> str:
        if rate is None:
            return '<td class="missing" title="当前数据未提供该曝光类别">—</td>'
        css = (f' class="heat heat-{min(5, max(1, int(rate * 100)))}"'
               if heat else f' class="metric {tone}"')
        return f'<td{css} title="{escape(label)}">{rate * 100:.2f}%</td>'

    rows = []
    for item in result["ranked"][:10]:
        rows.append(
            f'<tr><th scope="row" class="rank">{item["rank"]}</th>'
            f'<td class="name"><strong>{escape(item["name"])}</strong>'
            f'<small>人群 ID：{escape(item["id"])}</small></td>'
            + rate_cell(item["sp_rate"], "Sponsored Ads 触达（含共同曝光）", not has_dsp)
            + rate_cell(item["dsp_only_rate"], DSP_ONLY, tone="metric-dsp")
            + rate_cell(item["both_rate"], BOTH, tone="metric-overlap")
            + rate_cell(item["combined_rate"], "两类广告合并触达", has_dsp)
            + f'<td class="num">{item["sp_exposed"]:,}</td>'
            f'<td class="num">{item["total"]:,}</td></tr>'
        )
    data = [[x["rank"], x["id"], x["name"], x["sp_rate"], x["dsp_only_rate"],
             x["both_rate"], x["combined_rate"], x["sp_exposed"], x["total"]]
            for x in audiences]
    embedded = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    embedded = embedded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    rank_note = ("按当前数据的合并触达率从高到低排序" if has_dsp else
                 "按当前数据的 Sponsored Ads 触达率从高到低排序")
    formula_note = (
        "分母 = 仅 Sponsored Ads + 仅 DSP + 共同曝光 + 未曝光；Sponsored Ads 触达率包含共同曝光，合并触达率 = Sponsored Ads 触达率 + 仅 DSP 触达率。"
        if has_dsp else
        "当前文件只有 Exposed - Sp. Ads 与 Not Exposed；Sponsored Ads 触达率 = Exposed - Sp. Ads ÷ 两类计数之和。"
    )
    blank = result["blank_rows_excluded"]
    incomplete = len(result["incomplete"])
    replacements = {
        "__ROWS__": "".join(rows),
        "__DATA__": embedded,
        "__HAS_DSP__": "true" if has_dsp else "false",
        "__RANK_NOTE__": rank_note,
        "__FORMULA_NOTE__": formula_note,
        "__TOTAL__": f"{len(audiences):,}",
        "__DEFAULT_COUNT__": str(min(10, len(result["ranked"]))),
        "__BLANK_NOTE__": f"<p>已排除 {blank} 条缺少人群 ID 和名称的记录。</p>" if blank else "",
        "__INCOMPLETE_NOTE__": (f"<p>另有 {incomplete} 个人群缺少当前模式所需的完整曝光类别或分母为零，"
                                "列于“全部人群”末尾，触达率未计算。</p>") if incomplete else "",
    }
    pattern = re.compile("|".join(re.escape(token) for token in replacements))
    return pattern.sub(lambda match: replacements[match.group()], template)


def main() -> int:
    parser = argparse.ArgumentParser(description="跨境吴老师 AMC 目标人群触达率看板")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "build"):
        command = commands.add_parser(name)
        command.add_argument("--input", required=True, type=Path, help="本次上传的 UTF-8 CSV")
        if name == "build":
            command.add_argument("--output", required=True, type=Path, help="新 HTML 文件路径")
    args = parser.parse_args()
    try:
        result = read_csv(args.input)
        report = inspection(result)
        if args.command == "build":
            output = args.output
            if output.resolve() == args.input.resolve():
                raise InputError("输出不能覆盖输入 CSV。")
            html = build_html(result)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as handle:
                handle.write(html)
            report["output"] = str(output.resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (InputError, FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
