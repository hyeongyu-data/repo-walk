import hashlib
import json
import sys


CLASSIFIER_VERSION = "1"


def is_critical_path(path: str) -> bool:
    return (
        path.startswith((".github/workflows/", "github/workflows/"))
        or path in {".claude-plugin/plugin.json", "claude-plugin/plugin.json"}
        or path.endswith(("/.codex-plugin/plugin.json", "/codex-plugin/plugin.json"))
    )


def is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        path.startswith(("test/", "tests/", "spec/", "specs/"))
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
    )


def is_generated_or_vendor_path(path: str) -> bool:
    return path.startswith(("vendor/", "generated/", "dist/", "build/", "coverage/"))


def is_docs_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.startswith(("docs/", ".claude/docs/")) or name.lower().startswith("readme") or name.endswith(".md")


def is_runtime_path(path: str) -> bool:
    return path.startswith(("src/", "lib/", "scripts/", "bin/"))


def classify_path(path: str, repository: str) -> str:
    normalized = path.replace("\\", "/").lstrip("./")
    if repository == "hyeongyu-data/repo-walk" and (
        normalized == "commands/repo-walk.md"
        or normalized.startswith("plugins/repo-walk/skills/")
        or normalized.startswith("codex/prompts/")
    ):
        return "runtime"
    if is_critical_path(normalized):
        return "critical"
    if is_test_path(normalized):
        return "test"
    if is_generated_or_vendor_path(normalized):
        return "generated"
    if is_docs_path(normalized):
        return "docs"
    if is_runtime_path(normalized):
        return "runtime"
    return "other"


def validate_classification_input(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("입력은 객체여야 합니다.")
    repository = payload.get("repository")
    pr = payload.get("pr")
    if not isinstance(repository, str) or not repository:
        raise ValueError("repository는 비어 있지 않은 문자열이어야 합니다.")
    if not isinstance(pr, dict):
        raise ValueError("pr은 객체여야 합니다.")
    if not isinstance(pr.get("number"), int) or isinstance(pr["number"], bool):
        raise ValueError("pr.number는 정수여야 합니다.")
    if not isinstance(pr.get("state"), str):
        raise ValueError("pr.state는 문자열이어야 합니다.")
    if pr.get("mergedAt") is not None and not isinstance(pr["mergedAt"], str):
        raise ValueError("pr.mergedAt은 문자열 또는 null이어야 합니다.")
    if not isinstance(pr.get("changedFiles"), int) or isinstance(pr["changedFiles"], bool) or pr["changedFiles"] < 0:
        raise ValueError("pr.changedFiles는 0 이상의 정수여야 합니다.")
    if not isinstance(pr.get("files"), list):
        raise ValueError("pr.files는 배열이어야 합니다.")
    for item in pr["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"]:
            raise ValueError("pr.files의 각 항목에는 비어 있지 않은 path 문자열이 필요합니다.")
    return {"repository": repository, "pr": pr}


def input_digest(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classification_result(payload: dict, decision: str, reason: str, roles=None, candidate_kind=None) -> dict:
    return {
        "decision": decision,
        "reason": reason,
        "roles": roles if roles is not None else [],
        "candidateKind": candidate_kind,
        "classifierVersion": CLASSIFIER_VERSION,
        "inputDigest": input_digest(payload),
    }


def sole_or_mixed_non_runtime_reason(roles: list[str]) -> str:
    unique_roles = set(roles)
    if unique_roles == {"docs"}:
        return "docs_only"
    if unique_roles == {"test"}:
        return "tests_only"
    if unique_roles == {"generated"}:
        return "generated_only"
    return "non_runtime_files"


def classify_pull_request(payload: dict) -> dict:
    validated = validate_classification_input(payload)
    pr = validated["pr"]
    if pr["state"] != "MERGED" or not pr["mergedAt"]:
        return classification_result(validated, "exclude", "unmerged")
    if pr["changedFiles"] != len(pr["files"]):
        return classification_result(validated, "review", "incomplete_metadata")
    roles = [classify_path(item["path"], validated["repository"]) for item in pr["files"]]
    if not roles or set(roles) == {"other"}:
        return classification_result(validated, "review", "unknown_files", roles)
    if set(roles) <= {"docs", "test", "generated"}:
        reason = sole_or_mixed_non_runtime_reason(roles)
        return classification_result(validated, "exclude", reason, roles)
    candidate_kind = "critical" if "critical" in roles else "runtime"
    return classification_result(validated, "candidate", "eligible_files", roles, candidate_kind)


def main() -> None:
    payload = json.load(sys.stdin)
    json.dump(classify_pull_request(payload), sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
