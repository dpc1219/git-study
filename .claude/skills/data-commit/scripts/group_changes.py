#!/usr/bin/env python3
"""변경 파일을 (타입, 스코프) 후보 그룹으로 분류해 JSON으로 출력한다.

경로·확장자 기반의 초안이므로 최종 판단은 diff를 보고 사람이/Claude가 한다.

사용:
  python group_changes.py                 # 작업 트리 + staged + untracked
  python group_changes.py --range A B     # 과거 두 커밋 사이 (검증·학습용)
"""
import argparse
import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import PurePosixPath

sys.stdout.reconfigure(encoding="utf-8")

CODE_EXT = {".py", ".sql", ".r", ".sh"}
DATA_EXT = {".xlsx", ".xls", ".csv", ".parquet", ".json", ".feather", ".tsv"}
IMG_EXT = {".png", ".svg", ".jpg", ".jpeg", ".html"}
ENV_NAMES = {"requirements.txt", "environment.yml", "pyproject.toml", "setup.cfg", "poetry.lock"}
CHORE_NAMES = {".gitignore", ".gitattributes", ".editorconfig"}
RESULT_DIRS = {"output", "outputs", "result", "results", "report", "reports"}
SKIP_PARTS = {"__pycache__", ".ipynb_checkpoints", ".pytest_cache"}

ORDER = ["env", "chore", "data", "feat", "qa", "test", "result", "docs", "other"]


def git(*args):
    out = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return out.stdout


def changed_files(rng):
    files = OrderedDict()
    if rng:
        for line in git("diff", "--name-status", rng[0], rng[1]).splitlines():
            status, _, path = line.partition("\t")
            files[path.split("\t")[-1]] = status[0]
        return files
    for line in git("status", "--porcelain", "-uall").splitlines():
        status, path = line[:2].strip() or "M", line[3:]
        if " -> " in path:
            path = path.split(" -> ")[1]
        files[path.strip('"')] = "A" if status in ("??", "A") else status[0]
    return files


def classify(path):
    p = PurePosixPath(path)
    parts = [x.lower() for x in p.parts]
    name, ext = p.name.lower(), p.suffix.lower()

    if SKIP_PARTS & set(parts) or name.startswith("~$"):
        return "skip", ""
    if name in ENV_NAMES or (name.startswith("requirements") and ext == ".txt"):
        return "env", ""
    if name in CHORE_NAMES:
        return "chore", ""
    if ext in {".md", ".rst", ".txt"} or "docs" in parts:
        return "docs", ""
    if name.startswith("test_") or "tests" in parts:
        return "test", ""

    # 산출물: output/results 폴더 아래 → 바로 다음 폴더명이 분석 주제
    for i, part in enumerate(parts[:-1]):
        if part in RESULT_DIRS:
            scope = p.parts[i + 1] if i + 1 < len(p.parts) - 1 else ""
            return "result", scope
    if ext in IMG_EXT:
        return "result", ""

    if ext in CODE_EXT or ext == ".ipynb":
        return ("qa" if "quality" in name else "feat"), p.stem
    if ext in DATA_EXT:
        return "data", ""
    return "other", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--range", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()

    groups, skipped = OrderedDict(), []
    for path, status in changed_files(args.range).items():
        kind, scope = classify(path)
        if kind == "skip":
            skipped.append(path)
            continue
        groups.setdefault((kind, scope), []).append({"path": path, "status": status})

    ordered = sorted(groups.items(), key=lambda kv: (ORDER.index(kv[0][0]), kv[0][1]))
    print(json.dumps({
        "groups": [{"type": k, "scope": s, "files": f} for (k, s), f in ordered],
        "skipped": skipped,
        "note": "초안입니다. 타입(feat/fix/refactor 등)은 diff를 보고 확정하세요.",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
