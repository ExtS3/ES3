#!/usr/bin/env python3

import os
import re
import sys
import json
import subprocess
import urllib.request
import urllib.error

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.returncode

def github_api(method, endpoint, data=None, token=None):
    url = f"https://api.github.com{endpoint}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        try:
            error_body = json.loads(e.read())
        except Exception:
            error_body = {}
        return error_body, e.code


def branch_to_pr_title(branch_name):
    parts = branch_name.split("/", 1)
    if len(parts) < 2:
        return branch_name.replace("-", " ").title()

    prefix, rest = parts[0], parts[1]
    prefix_label = prefix.capitalize()

    issue_match = re.match(r'^(\d+)[-_](.+)$', rest)
    if issue_match:
        issue_num = issue_match.group(1)
        description = issue_match.group(2).replace("-", " ").replace("_", " ")
        return f"[{prefix_label}] #{issue_num} {description.title()}"
    else:
        description = rest.replace("-", " ").replace("_", " ")
        return f"[{prefix_label}] {description.title()}"


def get_changed_files(base_branch="develop"):
    candidates = [f"origin/{base_branch}", "HEAD~1"]

    for base in candidates:
        files, code = run_cmd(f"git diff --name-only {base}...HEAD 2>/dev/null")
        if code == 0 and files:
            return files.split("\n"), base.replace("origin/", "")

    return [], base_branch


def build_pr_body(branch_name, changed_files, rule_results, base_branch):
    lines = [
        "## 🤖 자동 생성된 Pull Request",
        "",
        f"**브랜치:** `{branch_name}` → `{base_branch}`",
        "",
    ]

    lines += ["### 📁 변경된 파일", ""]
    if changed_files:
        for f in changed_files[:20]:  # 최대 20개
            lines.append(f"- `{f}`")
        if len(changed_files) > 20:
            lines.append(f"- ... 외 {len(changed_files) - 20}개")
    else:
        lines.append("- (변경 파일을 감지할 수 없습니다)")
    lines.append("")

    lines += ["### ✅ 규칙 검사 결과", ""]
    lines += ["| 규칙 | 상태 | 내용 |", "|------|------|------|"]

    status_icons = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "WARNING": "⚠️ WARNING"}
    rule_names = {
        "rule1_branch":         "브랜치 이름",
        "rule2_readme":         "README 양식",
        "rule3_required_files": "필수 파일",
        "rule4_blocked_files":  "금지 파일",
        "rule5_commit_message": "커밋 메시지",
    }
    for key, data in rule_results.get("rules", {}).items():
        icon = status_icons.get(data["status"], data["status"])
        msg = data["messages"][0][:80] if data["messages"] else ""
        lines.append(f"| {rule_names.get(key, key)} | {icon} | {msg} |")
    lines.append("")

    warnings = rule_results.get("warnings", [])
    if warnings:
        lines += ["### ⚠️ 경고 항목", ""]
        for w in warnings:
            lines.append(f"> {w}")
        lines.append("")

    lines += [
        "---",
        "*이 PR은 Git Flow 자동 PR 파이프라인에 의해 생성되었습니다.*"
    ]
    return "\n".join(lines)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo  = os.environ.get("GITHUB_REPOSITORY")
    branch_name = (
        os.environ.get("GITHUB_HEAD_REF") or
        os.environ.get("GITHUB_REF_NAME") or
        run_cmd("git rev-parse --abbrev-ref HEAD")[0]
    )

    if not token:
        print("❌ GITHUB_TOKEN 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
    if not repo:
        print("❌ GITHUB_REPOSITORY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    print(f"\n🚀 PR 자동 생성 시작")
    print(f"   레포지토리: {repo}")
    print(f"   브랜치:     {branch_name}")

    rule_results = {}
    if os.path.exists("rule_check_result.json"):
        with open("rule_check_result.json") as f:
            rule_results = json.load(f)

    config_base = os.environ.get("PR_BASE_BRANCH", "develop")
    allow_fallback_to_main = os.environ.get("PR_ALLOW_FALLBACK_TO_MAIN", "false").lower() == "true"

    branches_data, _ = github_api("GET", f"/repos/{repo}/branches", token=token)
    branch_names = [b["name"] for b in (branches_data if isinstance(branches_data, list) else [])]

    if config_base in branch_names:
        base_branch = config_base
    elif allow_fallback_to_main and "main" in branch_names:
        base_branch = "main"
    else:
        print(f"❌ PR 대상 브랜치 '{config_base}'가 없습니다.")
        print("   팀 Git Flow 규칙에 따라 main으로 자동 대체하지 않습니다.")
        print("   GitHub에서 develop 브랜치를 먼저 생성하고 default branch로 설정해 주세요.")
        sys.exit(1)

    print(f"   Base 브랜치: {base_branch}")

    existing_prs, _ = github_api(
        "GET",
        f"/repos/{repo}/pulls?state=open&head={repo.split('/')[0]}:{branch_name}",
        token=token
    )
    if isinstance(existing_prs, list) and existing_prs:
        pr = existing_prs[0]
        print(f"\n⚠️  이미 열린 PR이 있습니다: {pr['html_url']}")
        print(f"   PR #{pr['number']}: {pr['title']}")
        sys.exit(0)

    pr_title = branch_to_pr_title(branch_name)
    changed_files, _ = get_changed_files(base_branch)
    pr_body = build_pr_body(branch_name, changed_files, rule_results, base_branch)

    print(f"\n   PR 제목: {pr_title}")

    pr_data = {
        "title": pr_title,
        "body":  pr_body,
        "head":  branch_name,
        "base":  base_branch,
    }
    response, status_code = github_api("POST", f"/repos/{repo}/pulls", data=pr_data, token=token)

    if status_code in (200, 201):
        print(f"\n✅ PR이 성공적으로 생성되었습니다!")
        print(f"   URL: {response.get('html_url')}")
        print(f"   PR #{response.get('number')}: {response.get('title')}")

        with open("created_pr_url.txt", "w") as f:
            f.write(response.get("html_url", ""))
    else:
        print(f"\n❌ PR 생성 실패 (HTTP {status_code})")
        print(f"   오류: {response.get('message', response)}")
        if "errors" in response:
            for err in response["errors"]:
                print(f"   - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
