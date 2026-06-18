#!/usr/bin/env python3
"""
PR 코드 리뷰 스크립트
────────────────────
역할: PR의 변경 코드를 정밀 분석하여 PM이 Merge 판단에 쓸 수 있는
      구조화된 리포트를 JSON + Markdown으로 생성한다.

분석 항목:
  1. 변경 요약   — 어떤 파일이 어떻게 바뀌었는가
  2. 신규 로직   — 추가된 함수·클래스·엔드포인트 목록
  3. 삭제/수정   — 기존 인터페이스의 변경·제거 여부
  4. 의존성 변화 — requirements.txt 추가·삭제·버전 변경
  5. import 검증 — 새로 추가된 import가 requirements에 있는지
  6. 정적 오류   — pyflakes 기반 undefined/unused 심볼
  7. 복잡도 경고 — 함수 길이·중첩 깊이가 임계값 초과 여부
  8. 위험 패턴   — eval/exec/subprocess/os.system/하드코딩 시크릿
  9. 종합 판정   — MERGE_READY / NEEDS_REVIEW / BLOCK
"""

import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────
# 데이터 모델
# ──────────────────────────────────────────────

@dataclass
class FileChange:
    path: str
    status: str          # added | modified | deleted | renamed
    additions: int = 0
    deletions: int = 0
    new_functions: list  = field(default_factory=list)
    removed_functions: list = field(default_factory=list)
    new_classes: list    = field(default_factory=list)
    new_endpoints: list  = field(default_factory=list)   # FastAPI @app.get 등
    new_imports: list    = field(default_factory=list)


@dataclass
class DependencyChange:
    package: str
    before: Optional[str]   # None = 신규
    after:  Optional[str]   # None = 삭제
    kind: str               # added | removed | upgraded | downgraded


@dataclass
class Issue:
    severity: str   # BLOCK | HIGH | MEDIUM | LOW
    category: str   # static_error | risk_pattern | complexity | dependency | interface
    file: str
    line: int
    message: str


@dataclass
class ReviewReport:
    pr_number: str
    base_sha: str
    head_sha: str
    branch: str
    changed_files: list     = field(default_factory=list)
    dependency_changes: list= field(default_factory=list)
    issues: list            = field(default_factory=list)
    new_symbols: dict       = field(default_factory=dict)  # {file: [func/class/endpoint]}
    removed_symbols: dict   = field(default_factory=dict)
    verdict: str = "MERGE_READY"   # MERGE_READY | NEEDS_REVIEW | BLOCK
    verdict_reason: str = ""
    summary: str = ""


# ──────────────────────────────────────────────
# Git 유틸
# ──────────────────────────────────────────────

def run(cmd: str, check=False) -> tuple[str, int]:
    r = subprocess.run(cmd, shell=True, capture_output=True)
    try:
        stdout = r.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        try:
            stdout = r.stdout.decode("utf-16").strip()
        except UnicodeDecodeError:
            stdout = r.stdout.decode("latin-1").strip()
    return stdout, r.returncode


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def get_changed_files(base: str, head: str) -> list[dict]:
    out, _ = run(f"git diff --name-status {base}...{head}")
    files = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        status_raw = parts[0]
        if status_raw.startswith("R"):          # Renamed
            path = parts[2] if len(parts) > 2 else parts[1]
            status = "renamed"
        else:
            path = parts[1] if len(parts) > 1 else ""
            status_map = {"A": "added", "M": "modified", "D": "deleted"}
            status = status_map.get(status_raw, "modified")
        if path:
            files.append({"path": path, "status": status})
    return files


def get_file_at(sha: str, path: str) -> Optional[str]:
    content, code = run(f"git show {sha}:{path} 2>/dev/null")
    return content if code == 0 else None


def get_diff_stat(base: str, head: str, path: str) -> tuple[int, int]:
    out, _ = run(f"git diff --numstat {base}...{head} -- {path}")
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                return int(parts[0]), int(parts[1])
            except ValueError:
                pass
    return 0, 0


# ──────────────────────────────────────────────
# AST 분석
# ──────────────────────────────────────────────

def extract_symbols(source: str) -> dict:
    """함수·클래스·FastAPI 엔드포인트·import를 추출한다."""
    result = {
        "functions": [],
        "classes": [],
        "endpoints": [],
        "imports": [],
    }
    if not source:
        return result
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return result

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # FastAPI 엔드포인트 감지 (@app.get / @router.post 등)
            for dec in node.decorator_list:
                dec_str = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                if re.search(r'\.(get|post|put|delete|patch|websocket)\s*\(', dec_str):
                    result["endpoints"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "decorator": dec_str,
                    })
            result["functions"].append({
                "name": node.name,
                "line": node.lineno,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "args": [a.arg for a in node.args.args],
            })

        elif isinstance(node, ast.ClassDef):
            result["classes"].append({
                "name": node.name,
                "line": node.lineno,
            })

        elif isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                result["imports"].append(node.module.split(".")[0])

    return result


def diff_symbols(before: dict, after: dict) -> tuple[list, list]:
    """(새로 추가된 심볼, 제거된 심볼) 반환"""
    def names(sym_list):
        return {s["name"] for s in sym_list}

    before_fns  = names(before.get("functions", []))
    after_fns   = names(after.get("functions", []))
    before_cls  = names(before.get("classes", []))
    after_cls   = names(after.get("classes", []))

    added   = sorted((after_fns - before_fns) | (after_cls - before_cls))
    removed = sorted((before_fns - after_fns) | (before_cls - after_cls))
    return added, removed


# ──────────────────────────────────────────────
# 복잡도 / 위험 패턴 분석
# ──────────────────────────────────────────────

RISK_PATTERNS = [
    (r"\beval\s*\(",           "BLOCK",  "eval() 사용 — 코드 인젝션 위험"),
    (r"\bexec\s*\(",           "BLOCK",  "exec() 사용 — 코드 인젝션 위험"),
    (r"os\.system\s*\(",       "HIGH",   "os.system() — subprocess로 대체 권장"),
    (r"subprocess\.call.*shell\s*=\s*True",
                               "HIGH",   "shell=True subprocess — 인젝션 위험"),
    (r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{6,}['\"]",
                               "HIGH",   "하드코딩된 시크릿 의심"),
    (r"pickle\.loads?\s*\(",   "HIGH",   "pickle.load — 신뢰할 수 없는 데이터에 위험"),
    (r"__import__\s*\(",       "MEDIUM", "__import__() 동적 임포트"),
    (r"open\([^,)]+,\s*['\"]w['\"]",
                               "LOW",    "파일 쓰기 — 경로 검증 여부 확인 필요"),
]

MAX_FUNC_LINES   = 80
MAX_NEST_DEPTH   = 5


def check_risk_patterns(source: str, path: str) -> list[Issue]:
    issues = []
    for lineno, line in enumerate(source.splitlines(), 1):
        for pattern, severity, msg in RISK_PATTERNS:
            if re.search(pattern, line):
                issues.append(Issue(
                    severity=severity,
                    category="risk_pattern",
                    file=path,
                    line=lineno,
                    message=msg,
                ))
    return issues


def check_complexity(source: str, path: str) -> list[Issue]:
    issues = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return issues

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # 함수 길이
        end_line = getattr(node, "end_lineno", node.lineno)
        length = end_line - node.lineno
        if length > MAX_FUNC_LINES:
            issues.append(Issue(
                severity="MEDIUM",
                category="complexity",
                file=path,
                line=node.lineno,
                message=f"함수 `{node.name}` 길이 {length}줄 (권장 {MAX_FUNC_LINES}줄 이하)",
            ))

        # 중첩 깊이
        depth = _max_depth(node)
        if depth > MAX_NEST_DEPTH:
            issues.append(Issue(
                severity="LOW",
                category="complexity",
                file=path,
                line=node.lineno,
                message=f"함수 `{node.name}` 중첩 깊이 {depth} (권장 {MAX_NEST_DEPTH} 이하)",
            ))

    return issues


def _max_depth(node: ast.AST, current: int = 0) -> int:
    branch_nodes = (ast.If, ast.For, ast.While, ast.With,
                    ast.Try, ast.ExceptHandler, ast.AsyncFor, ast.AsyncWith)
    if isinstance(node, branch_nodes):
        current += 1
    return max(
        [current] +
        [_max_depth(child, current) for child in ast.iter_child_nodes(node)]
    )


# ──────────────────────────────────────────────
# pyflakes 기반 정적 오류
# ──────────────────────────────────────────────

def run_pyflakes(path: str) -> list[Issue]:
    issues = []
    out, _ = run(f"python -m pyflakes {path} 2>&1")
    for line in out.splitlines():
        m = re.match(r"(.+?):(\d+):\d+\s+(.*)", line)
        if not m:
            m = re.match(r"(.+?):(\d+)\s+(.*)", line)
        if m:
            msg = m.group(3)
            # undefined name은 HIGH, unused는 LOW
            sev = "HIGH" if "undefined name" in msg else "LOW"
            issues.append(Issue(
                severity=sev,
                category="static_error",
                file=path,
                line=int(m.group(2)),
                message=msg,
            ))
    return issues


# ──────────────────────────────────────────────
# 의존성 분석
# ──────────────────────────────────────────────

def parse_requirements(text: str) -> dict[str, str]:
    pkgs = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z0-9_\-\.]+)\s*(?:==|>=|<=|~=|!=)?\s*([\d\.]*)", line)
        if m:
            pkgs[m.group(1).lower()] = m.group(2)
    return pkgs


def diff_requirements(before_text: Optional[str], after_text: Optional[str]) -> list[DependencyChange]:
    before = parse_requirements(before_text or "")
    after  = parse_requirements(after_text  or "")
    changes = []

    all_keys = set(before) | set(after)
    for pkg in sorted(all_keys):
        bv, av = before.get(pkg), after.get(pkg)
        if bv is None and av is not None:
            changes.append(DependencyChange(pkg, None, av, "added"))
        elif av is None and bv is not None:
            changes.append(DependencyChange(pkg, bv, None, "removed"))
        elif bv != av:
            kind = "upgraded" if av > bv else "downgraded"
            changes.append(DependencyChange(pkg, bv, av, kind))
    return changes


def check_import_vs_requirements(new_imports: list[str], req_text: str) -> list[str]:
    """requirements에 없는 신규 import 반환 (stdlib 제외)"""
    stdlib = {
        "os", "sys", "re", "json", "ast", "io", "abc", "copy", "math",
        "time", "datetime", "pathlib", "typing", "dataclasses", "functools",
        "itertools", "collections", "contextlib", "threading", "asyncio",
        "subprocess", "shutil", "tempfile", "hashlib", "hmac", "base64",
        "struct", "enum", "logging", "warnings", "traceback", "inspect",
        "unittest", "argparse", "csv", "xml", "html", "http", "urllib",
        "socket", "ssl", "email", "uuid", "random", "string", "textwrap",
        "__future__", "builtins", "weakref", "gc", "platform", "signal",
        "queue", "heapq", "bisect", "array", "decimal", "fractions",
        "statistics", "cmath", "numbers", "operator", "types", "abc",
    }
    req_pkgs = parse_requirements(req_text)
    missing = []
    for imp in new_imports:
        norm = imp.lower().replace("-", "_")
        if norm in stdlib:
            continue
        # requirements에서 찾기 (패키지명 정규화)
        if norm not in req_pkgs and norm.replace("_", "-") not in req_pkgs:
            missing.append(imp)
    return missing


# ──────────────────────────────────────────────
# 리포트 렌더링
# ──────────────────────────────────────────────

VERDICT_EMOJI = {
    "MERGE_READY": "✅",
    "NEEDS_REVIEW": "⚠️",
    "BLOCK": "🚫",
}

SEVERITY_EMOJI = {
    "BLOCK": "🚫",
    "HIGH": "🔴",
    "MEDIUM": "🟠",
    "LOW": "🟡",
}

CATEGORY_KO = {
    "static_error":  "정적 오류",
    "risk_pattern":  "위험 패턴",
    "complexity":    "복잡도",
    "dependency":    "의존성",
    "interface":     "인터페이스 변경",
}


def render_markdown(report: ReviewReport) -> str:
    v_emoji = VERDICT_EMOJI.get(report.verdict, "❓")
    lines = [
        f"## {v_emoji} PR 코드 리뷰 — `{report.branch}`",
        "",
        f"> **판정: {report.verdict}** — {report.verdict_reason}",
        "",
    ]

    # ── 1. 변경 요약 ──────────────────────────
    lines += ["### 📁 변경 파일 요약", ""]
    lines += ["| 파일 | 상태 | +추가 | -삭제 |", "|------|------|:-----:|:-----:|"]
    for fc in report.changed_files:
        status_ko = {"added": "신규", "modified": "수정", "deleted": "삭제", "renamed": "이름변경"}.get(fc["status"], fc["status"])
        lines.append(f"| `{fc['path']}` | {status_ko} | +{fc.get('additions',0)} | -{fc.get('deletions',0)} |")
    lines.append("")

    # ── 2. 신규 심볼 ──────────────────────────
    all_new = []
    for f, syms in report.new_symbols.items():
        for s in syms:
            all_new.append((f, s))
    if all_new:
        lines += ["### 🆕 신규 추가된 함수 / 클래스 / 엔드포인트", ""]
        for fpath, sym in all_new:
            lines.append(f"- `{fpath}` — **{sym}**")
        lines.append("")

    # ── 3. 제거된 심볼 ────────────────────────
    all_removed = []
    for f, syms in report.removed_symbols.items():
        for s in syms:
            all_removed.append((f, s))
    if all_removed:
        lines += ["### 🗑️ 제거된 함수 / 클래스 (인터페이스 변경 주의)", ""]
        for fpath, sym in all_removed:
            lines.append(f"- `{fpath}` — ~~{sym}~~")
        lines.append("")

    # ── 4. 의존성 변화 ────────────────────────
    if report.dependency_changes:
        lines += ["### 📦 의존성 변화", ""]
        lines += ["| 패키지 | 변화 | 이전 버전 | 변경 후 |", "|--------|------|:---------:|:-------:|"]
        for dc in report.dependency_changes:
            kind_ko = {"added": "➕ 추가", "removed": "➖ 삭제", "upgraded": "⬆️ 업그레이드", "downgraded": "⬇️ 다운그레이드"}.get(dc["kind"], dc["kind"])
            lines.append(f"| `{dc['package']}` | {kind_ko} | {dc.get('before') or '-'} | {dc.get('after') or '-'} |")
        lines.append("")

    # ── 5. 이슈 목록 ──────────────────────────
    if report.issues:
        lines += ["### 🔎 발견된 이슈", ""]
        # 심각도 순 정렬
        order = {"BLOCK": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        sorted_issues = sorted(report.issues, key=lambda i: order.get(i["severity"], 9))

        lines += ["| 심각도 | 분류 | 파일 | 줄 | 내용 |", "|:------:|------|------|----|------|"]
        for iss in sorted_issues:
            sev_str = f"{SEVERITY_EMOJI.get(iss['severity'],'')} {iss['severity']}"
            cat_str = CATEGORY_KO.get(iss["category"], iss["category"])
            lines.append(f"| {sev_str} | {cat_str} | `{iss['file']}` | {iss['line']} | {iss['message']} |")
        lines.append("")

    # ── 6. 전체 요약 ──────────────────────────
    lines += ["### 📋 PM 판단 요약", ""]
    lines.append(report.summary)
    lines += [
        "",
        "---",
        "*🤖 자동 생성 — Code Review Pipeline (Static Analysis)*",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 메인 분석 흐름
# ──────────────────────────────────────────────

def determine_verdict(issues: list[dict], dep_changes: list[dict],
                       removed_symbols: dict) -> tuple[str, str]:
    block_count  = sum(1 for i in issues if i["severity"] == "BLOCK")
    high_count   = sum(1 for i in issues if i["severity"] == "HIGH")
    medium_count = sum(1 for i in issues if i["severity"] == "MEDIUM")
    removed_count = sum(len(v) for v in removed_symbols.values())
    removed_deps  = [d for d in dep_changes if d["kind"] == "removed"]
    downgraded    = [d for d in dep_changes if d["kind"] == "downgraded"]

    reasons = []

    if block_count > 0:
        reasons.append(f"BLOCK 이슈 {block_count}건 (eval/exec/하드코딩 시크릿 등)")
        return "BLOCK", " | ".join(reasons)

    if high_count > 0:
        reasons.append(f"HIGH 이슈 {high_count}건")
    if removed_count > 0:
        reasons.append(f"기존 함수·클래스 {removed_count}개 제거됨 (인터페이스 파괴 위험)")
    if removed_deps:
        reasons.append(f"의존성 {len(removed_deps)}개 삭제: {', '.join(d['package'] for d in removed_deps)}")
    if downgraded:
        reasons.append(f"의존성 다운그레이드 {len(downgraded)}건")

    if reasons:
        return "NEEDS_REVIEW", " | ".join(reasons)

    if medium_count > 3:
        return "NEEDS_REVIEW", f"MEDIUM 이슈 {medium_count}건 다수"

    return "MERGE_READY", "주요 이슈 없음"


def build_summary(report: ReviewReport) -> str:
    fc_count = len(report.changed_files)
    new_sym_count = sum(len(v) for v in report.new_symbols.values())
    rem_sym_count = sum(len(v) for v in report.removed_symbols.values())
    dep_count = len(report.dependency_changes)
    block = sum(1 for i in report.issues if i["severity"] == "BLOCK")
    high  = sum(1 for i in report.issues if i["severity"] == "HIGH")
    med   = sum(1 for i in report.issues if i["severity"] == "MEDIUM")
    low   = sum(1 for i in report.issues if i["severity"] == "LOW")

    parts = [
        f"총 **{fc_count}개 파일** 변경.",
        f"신규 심볼 **{new_sym_count}개** 추가" + (f", 기존 심볼 **{rem_sym_count}개 제거** (⚠️ 호환성 검토 필요)" if rem_sym_count else "."),
    ]
    if dep_count:
        parts.append(f"의존성 **{dep_count}건** 변경.")
    if block or high or med or low:
        parts.append(
            f"발견된 이슈: 🚫 BLOCK {block}건 / 🔴 HIGH {high}건 / 🟠 MEDIUM {med}건 / 🟡 LOW {low}건."
        )
    else:
        parts.append("자동 분석에서 이슈가 발견되지 않았습니다.")

    return " ".join(parts)


def main():
    base_sha = get_env("REVIEW_BASE_SHA") or get_env("GITHUB_BASE_SHA")
    head_sha = get_env("REVIEW_HEAD_SHA") or get_env("GITHUB_HEAD_SHA") or "HEAD"
    branch   = get_env("REVIEW_BRANCH")   or get_env("GITHUB_HEAD_REF", "unknown")
    pr_num   = get_env("REVIEW_PR_NUMBER")or get_env("PR_NUMBER", "0")

    if not base_sha:
        # fallback: PR base를 origin/develop으로
        base_sha, _ = run("git merge-base origin/develop HEAD 2>/dev/null || git rev-parse HEAD~1")
    if not base_sha:
        print("❌ base SHA를 결정할 수 없습니다. REVIEW_BASE_SHA 환경변수를 설정하세요.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  🔍 PR 코드 리뷰 분석 시작")
    print(f"  브랜치  : {branch}")
    print(f"  Base SHA: {base_sha[:12]}")
    print(f"  Head SHA: {head_sha[:12]}")
    print(f"{'='*60}\n")

    report = ReviewReport(
        pr_number=pr_num,
        base_sha=base_sha,
        head_sha=head_sha,
        branch=branch,
    )

    # ── 변경 파일 목록 ────────────────────────
    changed = get_changed_files(base_sha, head_sha)
    print(f"[1/6] 변경 파일 감지: {len(changed)}개")

    py_files = [f for f in changed if f["path"].endswith(".py")]
    req_files = [f for f in changed if "requirements" in f["path"] and f["path"].endswith(".txt")]

    # ── requirements 의존성 diff ──────────────
    print(f"[2/6] 의존성 변화 분석: {len(req_files)}개 requirements 파일")
    for rf in req_files:
        before_text = get_file_at(base_sha, rf["path"])
        after_text  = get_file_at(head_sha, rf["path"])
        dep_changes = diff_requirements(before_text, after_text)
        for dc in dep_changes:
            report.dependency_changes.append(asdict(dc))

    # ── Python 파일 분석 ──────────────────────
    print(f"[3/6] Python 파일 심볼 + 위험 패턴 분석: {len(py_files)}개")

    all_new_imports = []

    for fc in changed:
        path = fc["path"]
        status = fc["status"]
        add, rem = get_diff_stat(base_sha, head_sha, path)
        fc_record = {
            "path": path,
            "status": status,
            "additions": add,
            "deletions": rem,
        }

        if path.endswith(".py") and status != "deleted":
            before_src = get_file_at(base_sha, path) or ""
            after_src  = get_file_at(head_sha, path) or ""

            before_syms = extract_symbols(before_src)
            after_syms  = extract_symbols(after_src)

            added_syms, removed_syms = diff_symbols(before_syms, after_syms)
            if added_syms:
                report.new_symbols[path] = added_syms
            if removed_syms:
                report.removed_symbols[path] = removed_syms
                # 인터페이스 제거는 이슈로도 등록
                for sym in removed_syms:
                    report.issues.append(asdict(Issue(
                        severity="HIGH",
                        category="interface",
                        file=path,
                        line=0,
                        message=f"`{sym}` 삭제됨 — 다른 모듈에서 사용 중인지 확인 필요",
                    )))

            # 신규 import 수집 (added/modified 파일만)
            if status in ("added", "modified"):
                before_imp = set(before_syms.get("imports", []))
                after_imp  = set(after_syms.get("imports", []))
                new_imps   = list(after_imp - before_imp)
                all_new_imports.extend(new_imps)

            fc_record["new_endpoints"] = after_syms.get("endpoints", [])

        report.changed_files.append(fc_record)

    # ── import vs requirements 검증 ───────────
    print(f"[4/6] Import-Requirements 정합성 검사")
    req_content_after = ""
    for rf in req_files:
        rc = get_file_at(head_sha, rf["path"])
        if rc:
            req_content_after += rc + "\n"
    if not req_content_after:
        # HEAD의 requirements.txt를 직접 읽기 (인코딩 자동 감지)
        req_path = Path("requirements.txt")
        if req_path.exists():
            raw = req_path.read_bytes()
            for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
                try:
                    req_content_after = raw.decode(enc)
                    break
                except (UnicodeDecodeError, Exception):
                    continue

    if all_new_imports and req_content_after:
        missing = check_import_vs_requirements(all_new_imports, req_content_after)
        for pkg in missing:
            report.issues.append(asdict(Issue(
                severity="HIGH",
                category="dependency",
                file="requirements.txt",
                line=0,
                message=f"`import {pkg}` 추가됐으나 requirements.txt에 없음",
            )))

    # ── 위험 패턴 + 복잡도 (변경된 파일만) ──
    # CI 도구 자체(review_pr.py)는 패턴 문자열이 포함돼 있으므로 분석 제외
    SELF_SKIP = {"scripts/review_pr.py"}

    print(f"[5/6] 위험 패턴 / 복잡도 분석")
    for fc in py_files:
        if fc["status"] == "deleted":
            continue
        path = fc["path"]
        if path in SELF_SKIP:
            print(f"  ⏭  {path} — CI 도구 파일, 위험 패턴 분석 제외")
            continue
        # 임시 파일로 저장해서 pyflakes 실행
        after_src = get_file_at(head_sha, path) or ""
        if not after_src:
            continue

        tmp_path = f"/tmp/_review_{path.replace('/', '_')}"
        Path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(after_src)

        risk_issues    = check_risk_patterns(after_src, path)
        complex_issues = check_complexity(after_src, path)
        pyflakes_issues = run_pyflakes(tmp_path)
        # pyflakes 결과의 파일명을 원래 path로 교정
        for iss in pyflakes_issues:
            iss.file = path

        for iss in risk_issues + complex_issues + pyflakes_issues:
            report.issues.append(asdict(iss))

        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # ── 판정 ──────────────────────────────────
    print(f"[6/6] 종합 판정")
    verdict, reason = determine_verdict(
        report.issues,
        report.dependency_changes,
        report.removed_symbols,
    )
    report.verdict        = verdict
    report.verdict_reason = reason
    report.summary        = build_summary(report)

    # ── 출력 ──────────────────────────────────
    result_dict = asdict(report)

    with open("pr_review_result.json", "w", encoding="utf-8") as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2)

    md = render_markdown(report)          # ← dict 아닌 ReviewReport 객체를 전달
    with open("pr_review_result.md", "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n{'='*60}")
    v_emoji = VERDICT_EMOJI.get(verdict, "❓")
    print(f"  {v_emoji} 판정: {verdict}")
    print(f"  이유: {reason}")
    issue_count = len(report.issues)
    print(f"  이슈: {issue_count}건")
    print(f"  결과 파일: pr_review_result.json / pr_review_result.md")
    print(f"{'='*60}\n")

    # BLOCK이면 exit 1 → GitHub Actions에서 Check 실패로 표시
    sys.exit(1 if verdict == "BLOCK" else 0)


if __name__ == "__main__":
    main()