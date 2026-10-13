#!/usr/bin/env python3
"""이슈 생성 → 한글 라벨 부착 → 워크트리/브랜치 생성을 한 번에 수행한다.

사용:
  python start_issue.py --title "[기능] 정류장별 환승 비율 분석" --body-file body.md \
      --type 기능 --topics 정류장·OD --slug transfer-ratio [--prefix feat] [--base main]

같은 제목의 열린 이슈가 있으면 새로 만들지 않고 그 이슈를 재사용한다.
마지막 줄에 결과를 JSON 한 줄로 출력한다.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ensure_labels import ALL_LABELS, STATUS_LABELS, TOPIC_LABELS, TYPE_LABELS, ensure_labels  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

PREFIX_BY_TYPE = {"기능": "feat", "버그": "fix", "문서": "docs", "개선": "feat", "리팩터링": "refactor", "질문": "docs"}


def run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        sys.exit(f"실패: {' '.join(cmd)}\n{r.stderr.strip()}")
    return r


def repo_slug():
    url = run(["git", "remote", "get-url", "origin"]).stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
    if not m:
        sys.exit(f"origin이 GitHub 저장소가 아닙니다: {url}")
    return m.group(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--type", required=True, choices=[n for n, _, _ in TYPE_LABELS])
    ap.add_argument("--topics", default="", help="쉼표 구분, 최대 2개")
    ap.add_argument("--slug", required=True, help="영문 소문자-하이픈")
    ap.add_argument("--prefix")
    ap.add_argument("--base", default="main")
    a = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", a.slug):
        sys.exit("--slug는 영문 소문자·숫자·하이픈만 가능합니다.")
    topics = [t.strip() for t in a.topics.split(",") if t.strip()]
    valid_topics = {n for n, _, _ in TOPIC_LABELS}
    bad = [t for t in topics if t not in valid_topics]
    if bad or len(topics) > 2:
        sys.exit(f"주제 라벨 오류: {bad or '2개 초과'} (허용: {sorted(valid_topics)})")

    run(["gh", "auth", "status"])
    repo = repo_slug()
    ensure_labels(repo)

    labels = [a.type, *topics, "상태:진행중"]

    # 중복 확인: 같은 제목의 열린 이슈는 재사용
    found = json.loads(run(["gh", "issue", "list", "--repo", repo, "--state", "open",
                            "--search", a.title, "--json", "number,title,url"]).stdout)
    same = [i for i in found if i["title"] == a.title]
    if same:
        number, url, reused = same[0]["number"], same[0]["url"], True
    else:
        url = run(["gh", "issue", "create", "--repo", repo, "--title", a.title,
                   "--body-file", a.body_file, "--label", ",".join(labels)]).stdout.strip().splitlines()[-1]
        number, reused = int(url.rsplit("/", 1)[-1]), False

    # 워크트리: 저장소 밖 형제 디렉터리
    top = Path(run(["git", "rev-parse", "--show-toplevel"]).stdout.strip())
    prefix = a.prefix or PREFIX_BY_TYPE[a.type]
    branch = f"{prefix}/{number}-{a.slug}"
    wt = top.parent / f"{top.name}-worktrees" / f"{number}-{a.slug}"

    existing = run(["git", "worktree", "list", "--porcelain"]).stdout
    if branch in existing or f"refs/heads/{branch}" in existing:
        status = "reused-worktree"
    else:
        wt.parent.mkdir(parents=True, exist_ok=True)
        has_branch = run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], check=False).returncode == 0
        cmd = ["git", "worktree", "add", str(wt)] + ([branch] if has_branch else ["-b", branch, a.base])
        run(cmd)
        status = "created-worktree"

    print(json.dumps({"issue": number, "url": url, "issue_reused": reused, "labels": labels,
                      "branch": branch, "worktree": str(wt), "worktree_status": status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
