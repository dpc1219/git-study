# git-study

Git 사용법을 정리한 학습용 저장소입니다. 설치와 초기 설정부터 커밋, 브랜치, 원격 저장소, 병합, 되돌리기까지 기본 흐름을 순서대로 다룹니다.

---

## 목차

1. [Git이란?](#1-git이란)
2. [설치 및 초기 설정](#2-설치-및-초기-설정)
3. [저장소 만들기와 복제](#3-저장소-만들기와-복제)
4. [기본 작업 흐름](#4-기본-작업-흐름)
5. [커밋 메시지 작성법](#5-커밋-메시지-작성법)
6. [브랜치](#6-브랜치)
7. [원격 저장소(GitHub 등)](#7-원격-저장소github-등)
8. [병합(merge)과 리베이스(rebase)](#8-병합merge과-리베이스rebase)
9. [충돌(conflict) 해결](#9-충돌conflict-해결)
10. [되돌리기](#10-되돌리기)
11. [.gitignore](#11-gitignore)
12. [자주 쓰는 명령어 요약](#12-자주-쓰는-명령어-요약)

---

## 1. Git이란?

Git은 파일의 **변경 이력을 기록하고 관리하는 분산 버전 관리 시스템**입니다.

- 언제든 과거 시점의 파일 상태로 돌아갈 수 있습니다.
- 여러 사람이 같은 프로젝트에서 동시에 작업해도 변경 사항을 합칠 수 있습니다.
- 기능별로 **브랜치**를 나눠 안전하게 실험할 수 있습니다.

### 핵심 개념

| 용어 | 설명 |
| --- | --- |
| 저장소(Repository) | 프로젝트와 그 변경 이력이 담긴 공간. `.git` 폴더에 이력이 저장됩니다. |
| 작업 디렉터리(Working Directory) | 실제로 파일을 편집하는 폴더 |
| 스테이징 영역(Staging Area / Index) | 다음 커밋에 포함될 변경 사항을 모아두는 공간 |
| 커밋(Commit) | 스테이징된 변경 사항을 하나의 기록으로 저장한 것 |
| 브랜치(Branch) | 커밋들을 가리키는 이동 가능한 포인터. 독립된 작업 흐름을 만듭니다. |
| HEAD | 현재 작업 중인 브랜치(또는 커밋)를 가리키는 포인터 |
| 원격 저장소(Remote) | GitHub 같은 서버에 있는 저장소. 보통 이름은 `origin`입니다. |

파일의 상태는 다음 세 가지 중 하나입니다.

```
Modified (수정됨)  →  git add  →  Staged (스테이징됨)  →  git commit  →  Committed (커밋됨)
```

---

## 2. 설치 및 초기 설정

### 설치 확인

```bash
git --version
```

Windows는 [Git for Windows](https://git-scm.com/download/win)에서 설치할 수 있습니다.

### 사용자 정보 설정 (최초 1회)

커밋할 때마다 작성자 정보가 함께 기록됩니다.

```bash
git config --global user.name "이름"
git config --global user.email "이메일@example.com"
```

### 기본 브랜치 이름 설정 (선택)

```bash
git config --global init.defaultBranch main
```

### 설정 확인

```bash
git config --list
```

---

## 3. 저장소 만들기와 복제

### 새 저장소 만들기

이미 있는 폴더를 Git 저장소로 만듭니다.

```bash
cd 프로젝트폴더
git init
```

### 원격 저장소 복제(clone)

GitHub 등에 있는 저장소를 내 컴퓨터로 가져옵니다.

```bash
git clone https://github.com/사용자명/저장소명.git
```

---

## 4. 기본 작업 흐름

Git 작업의 대부분은 아래 순서를 반복합니다.

```
파일 수정  →  git add  →  git commit  →  git push
```

### 1단계: 상태 확인

```bash
git status
```

어떤 파일이 수정되었고, 스테이징되었는지, 추적되지 않는(untracked) 파일이 있는지 보여줍니다.

### 2단계: 변경 내용 확인

```bash
git diff            # 작업 디렉터리의 변경 내용 (아직 add 전)
git diff --staged   # 스테이징된 변경 내용 (add 후, commit 전)
```

### 3단계: 스테이징

```bash
git add 파일명        # 특정 파일만 추가
git add .            # 현재 폴더의 모든 변경 사항 추가
git add -p           # 변경 조각(hunk)을 하나씩 골라서 추가
```

### 4단계: 커밋

```bash
git commit -m "커밋 메시지"
```

메시지 없이 실행하면 편집기가 열립니다. 긴 메시지를 쓸 때 편리합니다.

```bash
git commit
```

### 5단계: 이력 확인

```bash
git log                       # 전체 이력
git log --oneline             # 한 줄씩 간단히
git log --oneline --graph     # 브랜치 구조를 그래프로
```

---

## 5. 커밋 메시지 작성법

좋은 커밋 메시지는 **무엇을, 왜** 바꿨는지 드러냅니다.

```
<타입>: <제목 요약>

<본문 (선택): 변경 이유와 맥락>
```

자주 쓰는 타입 예시는 다음과 같습니다.

| 타입 | 의미 |
| --- | --- |
| `feat` | 새 기능 추가 |
| `fix` | 버그 수정 |
| `docs` | 문서 수정 |
| `style` | 코드 포맷, 세미콜론 등 동작에 영향 없는 변경 |
| `refactor` | 기능 변화 없이 코드 구조 개선 |
| `chore` | 빌드 설정, 패키지 관리 등 기타 작업 |

예시:

```
docs: README에 Git 사용법 정리

설치, 기본 작업 흐름, 브랜치, 원격 저장소 내용을 추가함.
```

> 제목은 50자 안팎으로 짧게, 현재형 명령문으로 작성하는 것이 일반적입니다.

---

## 6. 브랜치

브랜치를 사용하면 메인 코드를 건드리지 않고 새 기능이나 실험을 진행할 수 있습니다.

### 브랜치 목록 보기

```bash
git branch          # 로컬 브랜치
git branch -a       # 원격 브랜치 포함
```

### 브랜치 만들기와 이동

```bash
git branch 기능이름            # 브랜치만 생성
git switch 기능이름            # 브랜치로 이동 (최신 방식)
git switch -c 기능이름         # 생성 + 이동을 한 번에
```

> 예전 방식인 `git checkout 브랜치명`, `git checkout -b 브랜치명`도 같은 역할을 합니다.

### 브랜치 삭제

```bash
git branch -d 기능이름        # 병합이 끝난 브랜치 삭제
git branch -D 기능이름        # 병합 여부와 상관없이 강제 삭제
```

### 브랜치 이름 변경

```bash
git branch -m 새이름
```

### 일반적인 브랜치 작업 흐름

```bash
git switch main                  # 1. 메인으로 이동
git pull                         # 2. 최신 상태로 갱신
git switch -c feature/login      # 3. 작업 브랜치 생성
# ... 파일 수정 ...
git add .
git commit -m "feat: 로그인 화면 추가"
git push -u origin feature/login # 4. 원격에 올리기
```

---

## 7. 원격 저장소(GitHub 등)

### 원격 저장소 연결 확인

```bash
git remote -v
```

### 원격 저장소 추가

```bash
git remote add origin https://github.com/사용자명/저장소명.git
```

### 올리기 (push)

```bash
git push                    # 현재 브랜치를 원격에 올림
git push -u origin main     # 처음 올릴 때: 업스트림 설정 포함
```

### 내려받기 (fetch / pull)

```bash
git fetch            # 원격의 변경 사항만 가져옴 (내 작업에는 반영 안 됨)
git pull             # fetch + merge: 원격 변경 사항을 가져와 현재 브랜치에 합침
```

> `git fetch`로 먼저 내용을 확인한 뒤 병합하는 습관을 들이면 충돌을 줄일 수 있습니다.

---

## 8. 병합(merge)과 리베이스(rebase)

두 브랜치의 작업을 하나로 합치는 방법은 두 가지입니다.

### 병합 (merge)

```bash
git switch main
git merge 기능이름
```

두 브랜치의 이력을 **그대로 보존**하고 병합 커밋을 하나 만듭니다. 이력이 실제 작업 흐름대로 남습니다.

### 리베이스 (rebase)

```bash
git switch 기능이름
git rebase main
```

내 브랜치의 커밋들을 `main` 최신 커밋 위로 **옮겨 붙여** 이력을 일직선으로 만듭니다.

| 구분 | merge | rebase |
| --- | --- | --- |
| 이력 | 분기와 합침이 그대로 남음 | 일직선으로 정리됨 |
| 안전성 | 이미 공유한 브랜치에도 안전 | 공유된 커밋을 다시 쓰면 위험 |
| 권장 상황 | 협업 브랜치, 기능 통합 | 내 로컬 브랜치를 최신 main에 맞출 때 |

> **규칙:** 이미 원격에 push하여 다른 사람과 공유한 커밋은 rebase하지 않습니다.

---

## 9. 충돌(conflict) 해결

같은 파일의 같은 부분을 서로 다르게 수정하면 병합 시 충돌이 발생합니다.

```bash
git merge 기능이름
# CONFLICT (content): Merge conflict in 파일명
```

충돌 파일에는 다음과 같은 표시가 생깁니다.

```
<<<<<<< HEAD
현재 브랜치의 내용
=======
합치려는 브랜치의 내용
>>>>>>> 기능이름
```

해결 방법은 다음과 같습니다.

1. 파일을 열어 **남길 내용을 정하고** 표시 줄(`<<<<<<<`, `=======`, `>>>>>>>`)을 지웁니다.
2. 수정한 파일을 스테이징합니다.
3. 커밋해서 병합을 마무리합니다.

```bash
git add 파일명
git commit
```

병합을 취소하고 싶다면 다음을 실행합니다.

```bash
git merge --abort
```

---

## 10. 되돌리기

상황에 따라 적절한 명령어가 다릅니다.

### 작업 디렉터리의 수정 취소

아직 `add`하지 않은 변경을 버립니다. **복구할 수 없으니 주의하세요.**

```bash
git restore 파일명
```

### 스테이징 취소

`add`한 파일을 다시 수정 상태로 되돌립니다. 내용은 유지됩니다.

```bash
git restore --staged 파일명
```

### 마지막 커밋 메시지 수정

```bash
git commit --amend -m "새 메시지"
```

> 이미 push한 커밋은 amend하지 않는 것이 좋습니다.

### 커밋 되돌리기 (revert)

이력을 남긴 채로 **새 커밋을 만들어** 특정 커밋의 변경을 취소합니다. 공유된 브랜치에서 안전한 방법입니다.

```bash
git revert 커밋해시
```

### 커밋 되돌리기 (reset)

브랜치를 특정 커밋 위치로 **되돌립니다.** 이력을 지우므로 로컬 작업에서만 사용합니다.

```bash
git reset --soft HEAD~1    # 커밋만 취소, 변경 사항은 스테이징 상태로 유지
git reset --mixed HEAD~1   # 커밋과 스테이징 취소, 변경 사항은 작업 디렉터리에 유지 (기본값)
git reset --hard HEAD~1    # 커밋과 변경 사항 모두 삭제 (복구 어려움)
```

| 옵션 | 커밋 | 스테이징 | 작업 파일 |
| --- | --- | --- | --- |
| `--soft` | 취소 | 유지 | 유지 |
| `--mixed` | 취소 | 취소 | 유지 |
| `--hard` | 취소 | 취소 | **삭제** |

### 임시 저장 (stash)

커밋하기 애매한 작업을 잠시 치워 두고 싶을 때 사용합니다.

```bash
git stash              # 현재 변경 사항을 임시 저장
git stash list         # 임시 저장 목록 확인
git stash pop          # 가장 최근 임시 저장을 꺼내 적용
```

### 과거 파일 상태 확인

```bash
git show 커밋해시
git checkout 커밋해시 -- 파일명   # 특정 커밋 시점의 파일을 가져옴
```

---

## 11. .gitignore

Git이 추적하지 않아야 할 파일(빌드 결과물, 비밀번호가 담긴 설정 파일, 에디터 설정 등)은 `.gitignore`에 적습니다.

```gitignore
# 의존성 폴더
node_modules/

# 빌드 결과물
dist/
build/

# 환경 변수 및 비밀 정보
.env

# OS / 에디터 설정
.DS_Store
Thumbs.db
.vscode/
```

- `#`으로 시작하는 줄은 주석입니다.
- `/`로 끝나면 폴더, 아니면 파일 또는 폴더를 뜻합니다.
- 이미 추적 중인 파일은 `.gitignore`에 적어도 무시되지 않습니다. 추적을 끊으려면 다음을 실행합니다.

```bash
git rm --cached 파일명
```

---

## 12. 자주 쓰는 명령어 요약

| 목적 | 명령어 |
| --- | --- |
| 저장소 생성 | `git init` |
| 저장소 복제 | `git clone 주소` |
| 상태 확인 | `git status` |
| 변경 내용 확인 | `git diff` / `git diff --staged` |
| 스테이징 | `git add 파일명` / `git add .` |
| 커밋 | `git commit -m "메시지"` |
| 이력 보기 | `git log --oneline --graph` |
| 브랜치 목록 | `git branch` |
| 브랜치 생성 + 이동 | `git switch -c 이름` |
| 브랜치 이동 | `git switch 이름` |
| 브랜치 병합 | `git merge 이름` |
| 브랜치 재배치 | `git rebase 이름` |
| 원격 연결 확인 | `git remote -v` |
| 원격에 올리기 | `git push` |
| 원격에서 가져오기 | `git fetch` / `git pull` |
| 스테이징 취소 | `git restore --staged 파일명` |
| 수정 취소 | `git restore 파일명` |
| 커밋 되돌리기(안전) | `git revert 커밋해시` |
| 임시 저장 | `git stash` / `git stash pop` |

---

## 참고 자료

- [Pro Git 책 (한국어 번역)](https://git-scm.com/book/ko/v2)
- [Git 공식 문서](https://git-scm.com/docs)
- [Learn Git Branching (시각적 실습)](https://learngitbranching.js.org/?locale=ko)
