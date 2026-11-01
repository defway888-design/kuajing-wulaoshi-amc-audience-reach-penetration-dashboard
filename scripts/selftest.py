"""Small data-contract tests using synthetic CSVs; no customer data is bundled."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("audience_reach_dashboard.py")
SPEC = importlib.util.spec_from_file_location("audience_reach_dashboard", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def write_csv(path: Path, rows: list[list[str]], header: list[str] | None = None) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header or ["exposure", "segment_id", "segment_name", "user_count"])
        writer.writerows(rows)


def check_invalid(path: Path, rows: list[list[str]], expected: str,
                  header: list[str] | None = None) -> None:
    write_csv(path, rows, header)
    try:
        module.read_csv(path)
    except module.InputError as exc:
        assert expected in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected validation failure: {expected}")


def run() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "upload.csv"
        output = root / "dashboard.html"
        two = [
            ["Exposed - Sp. Ads", "A", "Audience A", "3"],
            ["Not Exposed", "A", "Audience A", "1"],
            ["Exposed - Sp. Ads", "B", "Audience B", "1"],
            ["Not Exposed", "B", "Audience B", "3"],
            ["Exposed - Sp. Ads", "C", "Audience C", "2"],
        ]
        write_csv(source, two + [["Exposed - Sp. Ads", "", "", "1"]])
        result = module.read_csv(source)
        assert result["mode"] == "sponsored-ads-only"
        assert len(result["ranked"]) == 2 and len(result["incomplete"]) == 1
        assert result["blank_rows_excluded"] == 1
        assert result["ranked"][0]["sp_rate"] == 0.75
        assert result["ranked"][0]["combined_rate"] is None
        html = module.build_html(result)
        assert "显示 2 / 3 人群" in html
        assert "75.00%" in html
        assert "Reach penetration within target audience广告触达人群率看板" in html
        assert "data:image/jpeg;base64," in html
        assert not re.search(r"[A-Za-z]:[\\/]", html)
        assert "__ROWS__" not in html and "__DATA__" not in html
        assert "前50人群" in html and "前100人群" in html and "全部人群" in html
        assert "下载当前筛选 CSV" in html

        inspect = subprocess.run([sys.executable, str(SCRIPT), "inspect", "--input", str(source)],
                                 capture_output=True, text=True, check=True)
        report = json.loads(inspect.stdout)
        assert report["status"] == "valid" and report["audiences_ranked"] == 2
        assert not output.exists(), "inspect must not write a dashboard"
        build = subprocess.run([sys.executable, str(SCRIPT), "build", "--input", str(source),
                                "--output", str(output)], capture_output=True, text=True, check=True)
        assert json.loads(build.stdout)["source_sha256"] == report["source_sha256"]
        assert output.is_file()
        overwrite = subprocess.run([sys.executable, str(SCRIPT), "build", "--input", str(source),
                                    "--output", str(output)], capture_output=True, text=True)
        assert overwrite.returncode != 0

        full = []
        for category, count in (("Exposed - Sp. Ads", "20"), ("Exposed - DSP", "10"),
                                ("Exposed - DSP & Sp. Ads", "5"), ("Not Exposed", "65")):
            full.append([category, "Z", "Audience Z", count])
        write_csv(source, full)
        result = module.read_csv(source)
        top = result["ranked"][0]
        assert result["mode"] == "four-category"
        assert top["total"] == 100 and top["sp_exposed"] == 25
        assert top["sp_rate"] == 0.25 and top["dsp_only_rate"] == 0.10
        assert top["both_rate"] == 0.05 and top["combined_rate"] == 0.35
        assert "35.00%" in module.build_html(result)

        check_invalid(source, [["Exposed - Sp. Ads", "A", "A", "1"]], "缺少必需字段",
                      ["exposure", "segment_id", "segment_name", "wrong"])
        check_invalid(source, [["Other", "A", "A", "1"]], "不受支持")
        check_invalid(source, [["Not Exposed", "A", "A", "-1"]], "非负整数")
        check_invalid(source, [["Not Exposed", "A", "A", "1"],
                               ["Not Exposed", "A", "A", "2"]], "类别重复")
        check_invalid(source, [["Not Exposed", "A", "A", "1"],
                               ["Exposed - Sp. Ads", "A", "B", "2"]], "不同的名称")
        check_invalid(source, [["Not Exposed", "A", "", "1"]], "同时有值")
    print("selftest: PASS")


if __name__ == "__main__":
    run()
