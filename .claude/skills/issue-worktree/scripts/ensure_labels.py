#!/usr/bin/env python3
"""한글 라벨 세트를 저장소에 보장한다(멱등). 이미 있는 라벨은 색·설명을 건드리지 않는다.

사용: python ensure_labels.py [--repo owner/repo] [--dry-run]
"""
import argparse
import json
import subprocess
import sys

# Windows 콘솔 기본 인코딩(cp949)에서 한글이 깨지지 않도록 UTF-8 고정
sys.stdout.reconfigure(encoding="utf-8")

# (이름, 색, 설명)
TYPE_LABELS = [
    ("기능", "a2eeef", "새로운 기능 추가"),
    ("버그", "d73a4a", "동작 오류 수정"),
    ("문서", "0075ca", "문서 추가·수정"),
    ("개선", "c5def5", "기존 기능 개선"),
    ("리팩터링", "bfdadc", "동작 변경 없는 구조 정리"),
    ("질문", "d876e3", "확인·논의 필요"),
]
TOPIC_LABELS = [
    ("노선분석", "5319e7", "노선별 운영 성과 분석"),
    ("정류장·OD", "1d76db", "정류장 및 OD 분석"),
    ("시간대수요", "0e8a16", "시간대별 수요 패턴 분석"),
    ("데이터품질", "fbca04", "데이터 품질 점검·보정"),
    ("이용자행태", "f9d0c4", "이용자 행태 분석"),
    ("데이터준비", "ededed", "원천·더미 데이터 준비"),
]
STATUS_LABELS = [
    ("상태:대기", "ededed", "착수 전"),
    ("상태:진행중", "fef2c0", "작업 진행 중"),
    ("상태:리뷰중", "d4c5f9", "PR 리뷰 중"),
    ("상태:완료", "0e8a16", "작업 완료"),
]
ALL_LABELS = TYPE_LABELS + TOPIC_LABELS + STATUS_LABELS


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def ensure_labels(repo=None, dry_run=False):
    """없는 라벨만 생성하고 새로 만든 이름 목록을 반환한다."""
    repo_args = ["--repo", repo] if repo else []
    r = run(["gh", "label", "list", *repo_args, "--limit", "200", "--json", "name"])
    if r.returncode:
        sys.exit(f"라벨 목록 조회 실패: {r.stderr.strip()}")
    existing = {x["name"] for x in json.loads(r.stdout)}
    created = []
    for name, color, desc in ALL_LABELS:
        if name in existing:
            continue
        if not dry_run:
            c = run(["gh", "label", "create", name, *repo_args,
                     "--color", color, "--description", desc])
            if c.returncode:
                sys.exit(f"라벨 생성 실패({name}): {c.stderr.strip()}")
        created.append(name)
    return created


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    made = ensure_labels(a.repo, a.dry_run)
    print(("생성 예정: " if a.dry_run else "생성됨: ") + (", ".join(made) if made else "없음(이미 모두 존재)"))
