#!/usr/bin/env python3

import os
import re
import sys
import json
import subprocess
import fnmatch

try:
    import yaml
except ImportError:
    print("❌ PyYAML이 설치되어 있지 않습니다.")
    print("   GitHub Actions workflow에서 'pip install pyyaml'을 먼저 실행하세요.")
    sys.exit(1)

RULES_FILE = ".github/pipeline-rules.yml"

if not os.path.exists(RULES_FILE):
    print(f"❌ 필수 규칙 파일이 없습니다: {RULES_FILE}")
    print("   해당 파일을 생성한 뒤 다시 push해 주세요.")
    sys.exit(1)

with open(RULES_FILE, encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

if not isinstance(CONFIG, dict):
    print(f"❌ 규칙 파일 형식이 올바르지 않습니다: {RULES_FILE}")
    print("   YAML 최상위 구조는 key-value 형태여야 합니다.")
    sys.exit(1)

def get_required_config(path):
    keys = path.split(".")
    val = CONFIG

    for key in keys:
        if isinstance(val, dict) and key in val:
            val = val[key]
        else:
            print(f"❌ 필수 설정 누락: {path}")
            print(f"   {RULES_FILE}에 '{path}' 값을 추가해 주세요.")
            sys.exit(1)

    if val is None:
        print(f"❌ 필수 설정 값이 비어 있습니다: {path}")
        print(f"   {RULES_FILE}에서 '{path}' 값을 채워 주세요.")
        sys.exit(1)

    return val

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

def print_result(rule_num, rule_name, status, message=""):
    icons = {
        "PASS": f"{GREEN}✅ PASS{RESET}",
        "FAIL": f"{RED}❌ FAIL{RESET}",
        "WARNING": f"{YELLOW}⚠️  WARN{RESET}",
        "SKIP": "⏭️  SKIP",
    }

    icon = icons.get(status, status)
    print(f"  [{icon}] 규칙 {rule_num}: {rule_name}")

    if message:
        for line in message.split("\n"):
            print(f"         {line}")

def run_cmd(cmd):
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip(), result.returncode

def check_rule1_branch(branch_name):
    results = []
    status = "PASS"

    skip_branches = ["main", "develop", "staging"]
    if branch_name in skip_branches:
        return "SKIP", [f"'{branch_name}' 브랜치는 파이프라인 미적용 대상입니다."]

    allowed_prefixes = get_required_config("branch.allowed_prefixes")
    if not any(branch_name.startswith(prefix) for prefix in allowed_prefixes):
        status = "FAIL"
        results.append(f"브랜치명이 허용된 prefix로 시작하지 않습니다: {allowed_prefixes}")

    if not re.match(r"^[a-z0-9\-/]+$", branch_name):
        status = "FAIL"
        results.append("브랜치명에 허용되지 않는 문자가 포함되어 있습니다. 영문 소문자, 숫자, 하이픈, 슬래시만 허용됩니다.")

    max_length = get_required_config("branch.max_length")
    if len(branch_name) > max_length:
        status = "FAIL"
        results.append(f"브랜치명이 {max_length}자를 초과합니다. 현재: {len(branch_name)}자")

    if not results:
        results.append("브랜치 이름 규칙을 통과했습니다.")

    return status, results

def check_rule2_readme(repo_root="."):
    readme_path = os.path.join(repo_root, "README.md")

    if not os.path.exists(readme_path):
        return "FAIL", ["README.md 파일이 존재하지 않습니다."]

    with open(readme_path, encoding="utf-8", errors="ignore") as f:
        content = f.read()
        lines = content.splitlines()

    if not content.strip():
        return "FAIL", ["README.md가 비어 있습니다."]

    results = []
    status = "PASS"

    min_lines = get_required_config("readme.min_lines")
    if len(lines) < min_lines:
        status = "FAIL"
        results.append(f"README.md가 너무 짧습니다. 현재: {len(lines)}줄, 최소: {min_lines}줄")

    if status == "PASS":
        results.append(f"README.md 검사 통과: {len(lines)}줄")

    return status, results

def check_rule3_required_files(repo_root="."):
    required = get_required_config("required_files")
    missing = []

    for filename in required:
        if filename == "LICENSE":
            variants = ["LICENSE", "LICENSE.md", "LICENSE.txt"]
            if not any(os.path.exists(os.path.join(repo_root, variant)) for variant in variants):
                missing.append("LICENSE 또는 LICENSE.md 또는 LICENSE.txt")
        else:
            if not os.path.exists(os.path.join(repo_root, filename)):
                missing.append(filename)

    if missing:
        return "FAIL", [f"누락된 필수 파일: {', '.join(missing)}"]

    return "PASS", ["모든 필수 파일이 존재합니다."]

def check_rule4_blocked_files(repo_root="."):
    patterns = get_required_config("blocked_files.patterns")
    blocked = []

    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d != ".git"]

        for filename in files:
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, repo_root)

            for pattern in patterns:
                if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                    blocked.append(f"{rel_path} (패턴: {pattern})")
                    break

    results = []
    status = "PASS"

    if blocked:
        status = "FAIL"
        results.append("금지된 파일이 발견되었습니다:")
        results.extend([f"  - {item}" for item in blocked])

    if status == "PASS":
        results.append("금지 파일 없음.")

    return status, results

def check_rule5_commit_message(commit_msg):
    cc_level = get_required_config("commit_message.conventional_commits")
    allowed_types = get_required_config("commit_message.allowed_types")

    pattern = rf'^({"|".join(allowed_types)})(\([a-zA-Z0-9\-_]+\))?: .+'
    first_line = commit_msg.strip().split("\n")[0]

    if re.match(pattern, first_line):
        return "PASS", [f"커밋 메시지 형식 준수: '{first_line[:60]}'"]

    msg = (
        "커밋 메시지 형식을 따르지 않습니다.\n"
        f"  입력: '{first_line[:60]}'\n"
        "  형식: <type>: <description> 또는 <type>(<scope>): <description>\n"
        f"  허용 타입: {', '.join(allowed_types)}"
    )

    if cc_level == "fail":
        return "FAIL", [msg]

    return "WARNING", [msg]

def write_summary(all_results, has_fail, warnings):
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")

    if not summary_file:
        return

    rule_names = {
        "rule1_branch": "브랜치 이름",
        "rule2_readme": "README 양식",
        "rule3_required_files": "필수 파일",
        "rule4_blocked_files": "금지 파일",
        "rule5_commit_message": "커밋 메시지",
    }

    status_icons = {
        "PASS": "✅",
        "FAIL": "❌",
        "WARNING": "⚠️",
        "SKIP": "⏭️",
    }

    with open(summary_file, "a", encoding="utf-8") as sf:
        sf.write("## 🔍 규칙 검사 결과\n\n")
        sf.write("| 규칙 | 이름 | 상태 | 메시지 |\n")
        sf.write("|------|------|------|--------|\n")

        for i, (key, data) in enumerate(all_results.items(), 1):
            icon = status_icons.get(data["status"], "❓")
            msg = data["messages"][0][:80] if data["messages"] else ""
            sf.write(
                f"| {i} | {rule_names.get(key, key)} | "
                f"{icon} {data['status']} | {msg} |\n"
            )

        sf.write("\n")

        if has_fail:
            sf.write("### ❌ 검사 실패 - PR이 생성되지 않습니다.\n")
            sf.write("실패한 규칙을 수정한 뒤 다시 push해 주세요.\n")
        elif warnings:
            sf.write("### ⚠️ 경고 있음 - PR은 생성되지만 경고 내용을 확인해 주세요.\n")
        else:
            sf.write("### ✅ 모든 검사 통과 - PR을 자동 생성합니다.\n")

def main():
    branch_name = (
        os.environ.get("GITHUB_HEAD_REF")
        or os.environ.get("GITHUB_REF_NAME")
        or run_cmd("git rev-parse --abbrev-ref HEAD")[0]
    )

    commit_msg, _ = run_cmd("git log -1 --pretty=%B")
    repo_root = os.environ.get("GITHUB_WORKSPACE", ".")

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  🔍 자동 PR 파이프라인 - 규칙 검사{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"  브랜치: {branch_name}")
    print(f"  커밋:   {commit_msg.split(chr(10))[0][:60]}")
    print(f"  규칙 파일: {RULES_FILE}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    all_results = {}
    has_fail = False
    warnings = []

    status1, msgs1 = check_rule1_branch(branch_name)
    all_results["rule1_branch"] = {
        "status": status1,
        "messages": msgs1,
    }

    if status1 == "SKIP":
        print_result(1, "브랜치 이름 규칙", status1, "\n".join(msgs1))

        result_json = {
            "branch": branch_name,
            "skip": True,
            "reason": msgs1[0],
        }

        with open("rule_check_result.json", "w", encoding="utf-8") as f:
            json.dump(result_json, f, ensure_ascii=False, indent=2)

        sys.exit(0)

    print_result(1, "브랜치 이름 규칙", status1, "\n".join(msgs1))

    if status1 == "FAIL":
        has_fail = True
    elif status1 == "WARNING":
        warnings.extend(msgs1)

    status2, msgs2 = check_rule2_readme(repo_root)
    all_results["rule2_readme"] = {
        "status": status2,
        "messages": msgs2,
    }

    print_result(2, "README.md 양식 규칙", status2, "\n".join(msgs2))

    if status2 == "FAIL":
        has_fail = True
    elif status2 == "WARNING":
        warnings.extend(msgs2)

    status3, msgs3 = check_rule3_required_files(repo_root)
    all_results["rule3_required_files"] = {
        "status": status3,
        "messages": msgs3,
    }

    print_result(3, "필수 파일 존재 여부", status3, "\n".join(msgs3))

    if status3 == "FAIL":
        has_fail = True
    elif status3 == "WARNING":
        warnings.extend(msgs3)

    status4, msgs4 = check_rule4_blocked_files(repo_root)
    all_results["rule4_blocked_files"] = {
        "status": status4,
        "messages": msgs4,
    }

    print_result(4, "금지 파일 차단", status4, "\n".join(msgs4))

    if status4 == "FAIL":
        has_fail = True
    elif status4 == "WARNING":
        warnings.extend(msgs4)

    status5, msgs5 = check_rule5_commit_message(commit_msg)
    all_results["rule5_commit_message"] = {
        "status": status5,
        "messages": msgs5,
    }

    print_result(5, "커밋 메시지 형식", status5, "\n".join(msgs5))

    if status5 == "FAIL":
        has_fail = True
    elif status5 == "WARNING":
        warnings.extend(msgs5)

    print(f"\n{BOLD}{'=' * 60}{RESET}")

    if has_fail:
        print(f"  {RED}{BOLD}결과: FAIL - PR이 생성되지 않습니다.{RESET}")
    elif warnings:
        print(f"  {YELLOW}{BOLD}결과: WARNING - PR이 생성되며 경고 내용이 포함됩니다.{RESET}")
    else:
        print(f"  {GREEN}{BOLD}결과: PASS - PR을 자동 생성합니다.{RESET}")

    print(f"{BOLD}{'=' * 60}{RESET}\n")

    result_data = {
        "branch": branch_name,
        "commit_message": commit_msg.split("\n")[0],
        "has_fail": has_fail,
        "warnings": warnings,
        "rules": all_results,
    }

    with open("rule_check_result.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print("  결과 저장: rule_check_result.json")

    write_summary(all_results, has_fail, warnings)

    sys.exit(1 if has_fail else 0)

if __name__ == "__main__":
    main()
