import argparse
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit


CLASSIFIER_VERSION = "1"

DEPENDENCY_FILENAMES = {
    "bun.lock",
    "bun.lockb",
    "cargo.lock",
    "cargo.toml",
    "composer.json",
    "composer.lock",
    "deno.json",
    "deno.jsonc",
    "flake.lock",
    "flake.nix",
    "gemfile",
    "gemfile.lock",
    "go.mod",
    "go.sum",
    "gradle.lockfile",
    "mix.exs",
    "mix.lock",
    "npm-shrinkwrap.json",
    "package-lock.json",
    "package.json",
    "package.resolved",
    "package.swift",
    "packages.lock.json",
    "pipfile",
    "pipfile.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pom.xml",
    "pubspec.lock",
    "pubspec.yaml",
    "pyproject.toml",
    "uv.lock",
    "yarn.lock",
}
GENERATED_SEGMENTS = {
    ".next",
    "build",
    "coverage",
    "dist",
    "generated",
    "node_modules",
    "out",
    "target",
    "vendor",
}
SOURCE_SUFFIXES = {
    ".bash",
    ".c",
    ".cc",
    ".clj",
    ".cljs",
    ".cpp",
    ".cs",
    ".dart",
    ".erl",
    ".ex",
    ".exs",
    ".fish",
    ".fs",
    ".go",
    ".h",
    ".hpp",
    ".hrl",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".lua",
    ".mjs",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sol",
    ".svelte",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
    ".zsh",
}


class ReportValidationError(ValueError):
    pass


def path_parts(path: str) -> tuple[str, ...]:
    return tuple(part.lower() for part in path.split("/") if part)


def is_critical_path(path: str) -> bool:
    parts = path_parts(path)
    name = parts[-1] if parts else ""
    suffix = Path(name).suffix.lower()
    if name in DEPENDENCY_FILENAMES:
        return True
    if (
        (name.startswith("requirements") and suffix in {".in", ".txt"})
        or name.endswith((".csproj", ".fsproj", ".gradle", ".gradle.kts", ".nuspec", ".vbproj"))
    ):
        return True
    if (
        path in {".claude-plugin/plugin.json", ".codex-plugin/plugin.json"}
        or path.endswith(("/.claude-plugin/plugin.json", "/.codex-plugin/plugin.json"))
    ):
        return True
    if (
        path.startswith((".github/actions/", ".github/workflows/"))
        or name in {
            ".gitlab-ci.yml",
            ".releaserc",
            ".releaserc.json",
            ".travis.yml",
            "action.yml",
            "action.yaml",
            "azure-pipelines.yml",
            "docker-compose.yml",
            "docker-compose.yaml",
            "dockerfile",
            "jenkinsfile",
            "makefile",
            "release-please-config.json",
            "setup.cfg",
            "setup.py",
        }
        or name.startswith("dockerfile.")
        or suffix in {".tf", ".tfvars"}
        or set(parts) & {
            ".circleci",
            "ansible",
            "cloudformation",
            "deploy",
            "deployment",
            "helm",
            "infra",
            "infrastructure",
            "k8s",
            "kubernetes",
            "packaging",
            "pulumi",
            "release",
            "releases",
            "terraform",
        }
    ):
        return True
    if (
        suffix in {".gql", ".graphql", ".prisma", ".proto", ".sql"}
        or name.startswith(("openapi.", "swagger."))
        or set(parts) & {"database", "db", "migration", "migrations", "schema", "schemas"}
    ):
        return True
    stem = Path(name).stem.lower()
    security_names = {
        "auth",
        "authentication",
        "authorization",
        "crypto",
        "cryptography",
        "oauth",
        "security",
    }
    return suffix in SOURCE_SUFFIXES and (
        bool(set(parts) & security_names)
        or stem in security_names
        or any(stem.startswith(f"{prefix}_") for prefix in security_names)
    )


def is_test_path(path: str) -> bool:
    parts = path_parts(path)
    name = path.rsplit("/", 1)[-1]
    return (
        bool(set(parts) & {"__tests__", "spec", "specs", "test", "tests"})
        or name.lower().startswith("test_")
        or "_test." in name.lower()
        or ".test." in name.lower()
        or ".spec." in name.lower()
        or name.endswith(("Test.java", "Test.kt", "Tests.cs"))
    )


def is_generated_or_vendor_path(path: str) -> bool:
    return bool(set(path_parts(path)) & GENERATED_SEGMENTS)


def is_docs_path(path: str) -> bool:
    parts = path_parts(path)
    name = parts[-1] if parts else ""
    stem = name.split(".", 1)[0]
    return (
        bool(set(parts) & {"doc", "docs", "documentation"})
        or stem in {"changelog", "contributing", "readme"}
        or name.endswith((".adoc", ".markdown", ".md", ".mdx", ".rst"))
    )


def is_runtime_path(path: str) -> bool:
    parts = path_parts(path)
    name = parts[-1] if parts else ""
    return (
        Path(name).suffix.lower() in SOURCE_SUFFIXES
        or name in {"rakefile"}
        or bool(set(parts) & {"bin", "cmd", "lib", "scripts", "src"})
    )


def classify_path(path: str, repository: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    if repository == "hyeongyu-data/repo-walk" and (
        normalized == "commands/repo-walk.md"
        or normalized.startswith("plugins/repo-walk/skills/")
        or normalized.startswith("codex/prompts/")
    ):
        return "runtime"
    if is_test_path(normalized):
        return "test"
    if is_generated_or_vendor_path(normalized):
        return "generated"
    if is_docs_path(normalized):
        return "docs"
    if is_critical_path(normalized):
        return "critical"
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
        return "test_only"
    if unique_roles == {"generated"}:
        return "generated_only"
    return "non_runtime_only"


def classify_pull_request(payload: dict) -> dict:
    validated = validate_classification_input(payload)
    pr = validated["pr"]
    if pr["state"] != "MERGED" or not pr["mergedAt"]:
        return classification_result(validated, "exclude", "unmerged")
    if pr["changedFiles"] != len(pr["files"]):
        return classification_result(validated, "review", "incomplete_metadata")
    roles = [classify_path(item["path"], validated["repository"]) for item in pr["files"]]
    role_set = set(roles)
    if "runtime" not in role_set and "critical" not in role_set and (
        not roles or "other" in role_set
    ):
        return classification_result(validated, "review", "unknown_files", roles)
    if role_set <= {"docs", "test", "generated"}:
        reason = sole_or_mixed_non_runtime_reason(roles)
        return classification_result(validated, "exclude", reason, roles)
    candidate_kind = "critical" if "critical" in roles else "runtime"
    return classification_result(validated, "candidate", "eligible_files", roles, candidate_kind)


def require_mapping(value, name: str) -> dict:
    if not isinstance(value, dict):
        raise ReportValidationError(f"{name}은 객체여야 합니다.")
    return value


def require_equal(mapping: dict, key: str, expected) -> None:
    if mapping.get(key) != expected or type(mapping.get(key)) is not type(expected):
        raise ReportValidationError(f"{key} 값은 {expected!r}이어야 합니다.")


def require_string(mapping: dict, key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ReportValidationError(f"{key}는 비어 있지 않은 문자열이어야 합니다.")
    return value


def require_integer(mapping: dict, key: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ReportValidationError(f"{key}는 1 이상의 정수여야 합니다.")
    return value


def require_string_list(mapping: dict, key: str, *, nonempty: bool = False) -> list[str]:
    value = mapping.get(key)
    if (
        not isinstance(value, list)
        or (nonempty and not value)
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ReportValidationError(f"{key}는 비어 있지 않은 문자열의 배열이어야 합니다.")
    return value


def require_enum(mapping: dict, key: str, allowed: set[str]) -> str:
    value = require_string(mapping, key)
    if value not in allowed:
        raise ReportValidationError(f"{key} 값이 허용된 범위에 없습니다.")
    return value


def validate_pr(value) -> dict:
    pr = require_mapping(value, "pr")
    require_integer(pr, "number")
    for key in ("title", "url", "mergedAt"):
        require_string(pr, key)
    return pr


def validate_classification(value) -> dict:
    classification = require_mapping(value, "classification")
    require_equal(classification, "decision", "include")
    require_enum(classification, "kind", {"behavior", "critical"})
    behavior_changed = classification.get("behaviorChanged")
    if not isinstance(behavior_changed, bool):
        raise ReportValidationError("behaviorChanged는 boolean이어야 합니다.")
    operational_impact = require_enum(
        classification,
        "operationalImpact",
        {"none", "material", "critical"},
    )
    require_enum(classification, "confidence", {"low", "medium", "high"})
    require_string_list(classification, "reasons", nonempty=True)
    files = require_string_list(classification, "files", nonempty=True)
    evidence = classification.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ReportValidationError("evidence는 비어 있지 않은 배열이어야 합니다.")
    for index, item in enumerate(evidence):
        item = require_mapping(item, f"evidence[{index}]")
        path = require_string(item, "path")
        require_string(item, "claim")
        if path not in files:
            raise ReportValidationError("evidence.path는 classification.files에 있어야 합니다.")
    require_string(classification, "classifierVersion")
    digest = require_string(classification, "inputDigest")
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ReportValidationError("inputDigest는 소문자 SHA-256이어야 합니다.")
    if not behavior_changed and operational_impact == "none":
        raise ReportValidationError("동작 또는 운영 영향이 없는 리포트는 포함할 수 없습니다.")
    return classification


def validate_overview(value) -> dict:
    overview = require_mapping(value, "overview")
    for key in ("problem", "keyChanges", "impact", "next"):
        require_string(overview, key)
    return overview


def validate_block(value, section_index: int, block_index: int) -> dict:
    name = f"sections[{section_index}].blocks[{block_index}]"
    block = require_mapping(value, name)
    block_type = require_string(block, "type")
    fields_by_type = {
        "paragraph": ("text",),
        "code": ("path", "language", "code"),
        "quote": ("author", "text"),
        "finding": ("severity", "confidence", "path", "finding", "suggestion"),
        "question": ("question", "importance", "answer"),
    }
    if block_type == "list":
        require_string_list(block, "items")
    elif block_type in fields_by_type:
        for key in fields_by_type[block_type]:
            require_string(block, key)
        if block_type in {"code", "finding"}:
            require_integer(block, "line")
    else:
        raise ReportValidationError(f"{name}.type {block_type!r}은 지원되지 않습니다.")
    return block


def validate_sections(value) -> list[dict]:
    if not isinstance(value, list):
        raise ReportValidationError("sections는 배열이어야 합니다.")
    for section_index, section_value in enumerate(value):
        section = require_mapping(section_value, f"sections[{section_index}]")
        require_string(section, "title")
        blocks = section.get("blocks")
        if not isinstance(blocks, list):
            raise ReportValidationError(f"sections[{section_index}].blocks는 배열이어야 합니다.")
        for block_index, block in enumerate(blocks):
            validate_block(block, section_index, block_index)
    return value


def validate_report(payload: dict) -> dict:
    require_mapping(payload, "report")
    require_equal(payload, "schemaVersion", 1)
    require_string(payload, "repository")
    require_string(payload, "generatedAt")
    validate_pr(payload.get("pr"))
    validate_classification(payload.get("classification"))
    require_string(payload, "summary")
    validate_overview(payload.get("overview"))
    validate_sections(payload.get("sections"))
    return payload


def render_supported_non_code_block(block: dict) -> str:
    block_type = block["type"]
    if block_type == "list":
        items = "".join(f"<li>{escape(item)}</li>" for item in block["items"])
        return f"<ul>{items}</ul>"
    if block_type == "quote":
        return (
            f"<blockquote><p>{escape(block['text'])}</p>"
            f"<footer>— {escape(block['author'])}</footer></blockquote>"
        )
    if block_type == "finding":
        label = f"{block['path']}:{block['line']}"
        return (
            '<article class="finding">'
            f"<h3>{escape(block['severity'])} · 신뢰도 {escape(block['confidence'])}</h3>"
            f"<p class=\"location\">{escape(label)}</p>"
            f"<p>{escape(block['finding'])}</p>"
            f"<p><strong>제안</strong> {escape(block['suggestion'])}</p>"
            "</article>"
        )
    if block_type == "question":
        return (
            '<article class="question">'
            f"<h3>{escape(block['question'])}</h3>"
            f"<p><strong>왜 중요한가</strong> {escape(block['importance'])}</p>"
            f"<p><strong>모범 답안</strong> {escape(block['answer'])}</p>"
            "</article>"
        )
    raise ReportValidationError(f"지원되지 않는 block type: {block_type!r}")


def render_block(block: dict) -> str:
    block_type = block["type"]
    if block_type == "paragraph":
        return f"<p>{escape(block['text'])}</p>"
    if block_type == "code":
        label = f"{block['path']}:{block['line']}"
        return (
            f'<figure class="code"><figcaption>{escape(label)}</figcaption>'
            f"<pre><code>{escape(block['code'])}</code></pre></figure>"
        )
    return render_supported_non_code_block(block)


def safe_github_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.netloc.lower() == "github.com"
        and parsed.username is None
        and parsed.password is None
    )


def render_pr_url(url: str) -> str:
    escaped_url = escape(url, quote=True)
    if safe_github_url(url):
        return f'<a href="{escaped_url}">{escaped_url}</a>'
    return escaped_url


def render_unit_html(payload: dict) -> str:
    pr = payload["pr"]
    classification = payload["classification"]
    overview = payload["overview"]
    sections = "".join(
        f"<section><h2>{escape(section['title'])}</h2>"
        + "".join(render_block(block) for block in section["blocks"])
        + "</section>"
        for section in payload["sections"]
    )
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in classification["reasons"])
    files = "".join(f"<li><code>{escape(path)}</code></li>" for path in classification["files"])
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PR #{pr['number']} · {escape(pr['title'])}</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, sans-serif; color: #202124; background: #f6f8fa; }}
body {{ margin: 0 auto; max-width: 920px; padding: 2rem 1rem 4rem; line-height: 1.65; overflow-wrap: anywhere; }}
header, section {{ background: white; border: 1px solid #d0d7de; border-radius: 12px; margin: 1rem 0; padding: 1.25rem; }}
h1, h2, h3 {{ line-height: 1.25; }}
.meta, .location {{ color: #59636e; }}
.overview {{ display: grid; gap: .75rem; }}
.overview dt {{ font-weight: 700; }}
.overview dd {{ margin: 0; }}
.code pre {{ background: #161b22; color: #f0f6fc; overflow-x: auto; overflow-wrap: normal; padding: 1rem; border-radius: 8px; white-space: pre; }}
blockquote, .finding, .question {{ border-left: 4px solid #8250df; margin: 1rem 0; padding: .25rem 1rem; }}
.finding {{ border-color: #bf8700; }}
</style>
</head>
<body>
<header>
<p class="meta">PR #{pr['number']} · {escape(pr['mergedAt'])}</p>
<h1>{escape(pr['title'])}</h1>
<p>{escape(payload['summary'])}</p>
<p>{render_pr_url(pr['url'])}</p>
</header>
<section>
<h2>개요</h2>
<dl class="overview">
<dt>문제</dt><dd>{escape(overview['problem'])}</dd>
<dt>핵심 변경</dt><dd>{escape(overview['keyChanges'])}</dd>
<dt>영향</dt><dd>{escape(overview['impact'])}</dd>
<dt>다음 단계</dt><dd>{escape(overview['next'])}</dd>
</dl>
</section>
<section>
<h2>분류</h2>
<p>{escape(classification['kind'])} · {escape(classification['operationalImpact'])} · {escape(classification['confidence'])}</p>
<h3>근거</h3><ul>{reasons}</ul>
<h3>파일</h3><ul>{files}</ul>
</section>
{sections}
</body>
</html>
"""


def manifest_entry(payload: dict) -> dict:
    return {
        "number": payload["pr"]["number"],
        "title": payload["pr"]["title"],
        "url": payload["pr"]["url"],
        "mergedAt": payload["pr"]["mergedAt"],
        "summary": payload["summary"],
        "kind": payload["classification"]["kind"],
        "operationalImpact": payload["classification"]["operationalImpact"],
        "confidence": payload["classification"]["confidence"],
        "reasons": list(payload["classification"]["reasons"]),
        "files": list(payload["classification"]["files"]),
    }


def render_index_html(manifest: dict) -> str:
    cards = []
    for entry in manifest["reports"]:
        kind = entry["kind"]
        badge_class = "badge critical" if kind == "critical" else "badge"
        reasons = "".join(f"<li>{escape(reason)}</li>" for reason in entry["reasons"])
        files = "".join(f"<li><code>{escape(path)}</code></li>" for path in entry["files"])
        cards.append(
            '<article class="card">'
            f'<p><span class="{badge_class}">{escape(kind)}</span> '
            f"{escape(entry['operationalImpact'])} · {escape(entry['confidence'])}</p>"
            f'<h2><a href="prs/pr-{entry["number"]}.html">'
            f"PR #{entry['number']} · {escape(entry['title'])}</a></h2>"
            f"<p>{escape(entry['summary'])}</p>"
            f"<p class=\"meta\">{escape(entry['mergedAt'])} · {render_pr_url(entry['url'])}</p>"
            f"<h3>포함 이유</h3><ul>{reasons}</ul>"
            f"<h3>영향 파일</h3><ul>{files}</ul>"
            "</article>"
        )
    kind_counts = manifest["kindCounts"]
    impact_counts = manifest["operationalImpactCounts"]
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>repo-walk PR 리포트</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, sans-serif; color: #202124; background: #f6f8fa; }}
body {{ margin: 0 auto; max-width: 920px; padding: 2rem 1rem 4rem; line-height: 1.6; overflow-wrap: anywhere; }}
.card {{ background: white; border: 1px solid #d0d7de; border-radius: 12px; margin: 1rem 0; padding: 1.25rem; }}
.badge {{ background: #ddf4ff; border-radius: 999px; display: inline-block; padding: .15rem .55rem; }}
.badge.critical {{ background: #ffebe9; color: #a40e26; }}
.meta {{ color: #59636e; }}
</style>
</head>
<body>
<header>
<h1>{escape(manifest["repository"])} PR 리포트</h1>
<p class="meta">생성 시각 {escape(manifest["generatedAt"])} · 총 {manifest["reportCount"]}개</p>
<p>종류: behavior {kind_counts["behavior"]} · critical {kind_counts["critical"]}</p>
<p>운영 영향: none {impact_counts["none"]} · material {impact_counts["material"]} · critical {impact_counts["critical"]}</p>
</header>
<main>{"".join(cards)}</main>
</body>
</html>
"""


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, serialize_json(payload))


def serialize_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def collect_valid_reports(output_root: Path, replacement: dict = None) -> list[dict]:
    reports = []
    for data_path in sorted((output_root / "data").glob("pr-*.json")):
        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            validated = validate_report(payload)
        except (UnicodeError, json.JSONDecodeError, ReportValidationError):
            continue
        except OSError:
            print("경고: 읽을 수 없는 PR data 항목을 건너뜁니다.", file=sys.stderr)
            continue
        reports.append(validated)
    if replacement is not None:
        reports.append(replacement)
    repositories = {payload["repository"] for payload in reports}
    if len(repositories) > 1:
        raise ReportValidationError("서로 다른 repository 리포트를 합칠 수 없습니다.")
    reports_by_number = {
        payload["pr"]["number"]: payload
        for payload in reports
    }
    return sorted(
        reports_by_number.values(),
        key=lambda payload: (payload["pr"]["mergedAt"], payload["pr"]["number"]),
        reverse=True,
    )


def atomic_replace_text_files(outputs: list[tuple[Path, str]]) -> None:
    staged = {}
    backups = {}
    replaced = []
    try:
        for path, content in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, delete=False
            )
            temporary = Path(handle.name)
            staged[path] = temporary
            with handle:
                handle.write(content)

        for path in staged:
            if path.exists():
                handle = NamedTemporaryFile("wb", dir=path.parent, delete=False)
                backup = Path(handle.name)
                backups[path] = backup
                with handle:
                    handle.write(path.read_bytes())
            else:
                backups[path] = None

        for path, temporary in staged.items():
            os.replace(temporary, path)
            staged[path] = None
            replaced.append(path)
    except BaseException as error:
        rollback_error = None
        for path in reversed(replaced):
            try:
                backup = backups[path]
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    os.replace(backup, path)
                    backups[path] = None
            except BaseException as current_error:
                if rollback_error is None:
                    rollback_error = current_error
        if rollback_error is not None:
            raise rollback_error from error
        raise
    finally:
        for temporary in staged.values():
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        for backup in backups.values():
            if backup is not None:
                backup.unlink(missing_ok=True)


def index_outputs(output_root: Path, replacement: dict = None) -> tuple[str, str]:
    reports = collect_valid_reports(output_root, replacement)
    entries = [manifest_entry(payload) for payload in reports]
    kind_counts = {"behavior": 0, "critical": 0}
    impact_counts = {"none": 0, "material": 0, "critical": 0}
    for entry in entries:
        kind_counts[entry["kind"]] += 1
        impact_counts[entry["operationalImpact"]] += 1
    manifest = {
        "schemaVersion": 1,
        "repository": reports[0]["repository"] if reports else "",
        "generatedAt": max(
            (payload["generatedAt"] for payload in reports),
            default="",
        ),
        "reportCount": len(entries),
        "kindCounts": kind_counts,
        "operationalImpactCounts": impact_counts,
        "reports": entries,
    }
    return (
        serialize_json(manifest),
        render_index_html(manifest),
    )


def rebuild_index(output_root: Path) -> Path:
    output_root = Path(output_root)
    manifest_content, index_content = index_outputs(output_root)
    index_path = output_root / "index.html"
    atomic_replace_text_files([
        (output_root / "manifest.json", manifest_content),
        (index_path, index_content),
    ])
    return index_path


def render_report(payload: dict, output_root: Path) -> Path:
    validated = validate_report(payload)
    output_root = Path(output_root)
    number = validated["pr"]["number"]
    unit_path = output_root / f"prs/pr-{number}.html"
    manifest_content, index_content = index_outputs(output_root, validated)
    atomic_replace_text_files([
        (output_root / f"data/pr-{number}.json", serialize_json(validated)),
        (unit_path, render_unit_html(validated)),
        (output_root / "manifest.json", manifest_content),
        (output_root / "index.html", index_content),
    ])
    return unit_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="repo-walk HTML 리포트 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify = subparsers.add_parser("classify")
    classify.add_argument("--input", required=True, type=Path)

    render = subparsers.add_parser("render")
    render.add_argument("--input", required=True, type=Path)
    render.add_argument("--output-dir", required=True, type=Path)

    rebuild = subparsers.add_parser("rebuild-index")
    rebuild.add_argument("--output-dir", required=True, type=Path)
    return parser


def write_stdout_json(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_command(arguments: argparse.Namespace) -> None:
    if arguments.command == "classify":
        write_stdout_json(classify_pull_request(load_json(arguments.input)))
    elif arguments.command == "render":
        render_report(load_json(arguments.input), arguments.output_dir)
    else:
        rebuild_index(arguments.output_dir)


def main(argv=None) -> int:
    effective_argv = sys.argv[1:] if argv is None else argv
    if not effective_argv:
        write_stdout_json(classify_pull_request(json.load(sys.stdin)))
        return 0

    arguments = build_parser().parse_args(effective_argv)
    try:
        run_command(arguments)
    except json.JSONDecodeError:
        print("JSON 입력을 해석할 수 없습니다.", file=sys.stderr)
        return 2
    except (ReportValidationError, ValueError):
        print("입력 검증에 실패했습니다.", file=sys.stderr)
        return 3
    except OSError:
        print("파일 처리에 실패했습니다.", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
