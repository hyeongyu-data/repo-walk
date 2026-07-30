import hashlib
from html import escape
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit


CLASSIFIER_VERSION = "1"


class ReportValidationError(ValueError):
    pass


def is_critical_path(path: str) -> bool:
    return (
        path.startswith((".github/workflows/", "github/workflows/"))
        or path in {".claude-plugin/plugin.json", "claude-plugin/plugin.json"}
        or path == "codex-plugin/plugin.json"
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


def require_string_list(mapping: dict, key: str) -> list[str]:
    value = mapping.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ReportValidationError(f"{key}는 비어 있지 않은 문자열의 배열이어야 합니다.")
    return value


def validate_pr(value) -> dict:
    pr = require_mapping(value, "pr")
    require_integer(pr, "number")
    for key in ("title", "url", "mergedAt"):
        require_string(pr, key)
    return pr


def validate_classification(value) -> dict:
    classification = require_mapping(value, "classification")
    for key in ("kind", "operationalImpact", "confidence"):
        require_string(classification, key)
    require_string_list(classification, "reasons")
    require_string_list(classification, "files")
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
body {{ margin: 0 auto; max-width: 920px; padding: 2rem 1rem 4rem; line-height: 1.65; }}
header, section {{ background: white; border: 1px solid #d0d7de; border-radius: 12px; margin: 1rem 0; padding: 1.25rem; }}
h1, h2, h3 {{ line-height: 1.25; }}
.meta, .location {{ color: #59636e; }}
.overview {{ display: grid; gap: .75rem; }}
.overview dt {{ font-weight: 700; }}
.overview dd {{ margin: 0; }}
.code pre {{ background: #161b22; color: #f0f6fc; overflow-x: auto; padding: 1rem; border-radius: 8px; }}
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
    }


def render_index_html(entries: list[dict]) -> str:
    cards = []
    for entry in entries:
        kind = entry["kind"]
        badge_class = "badge critical" if kind == "critical" else "badge"
        cards.append(
            '<article class="card">'
            f'<p><span class="{badge_class}">{escape(kind)}</span> '
            f"{escape(entry['operationalImpact'])} · {escape(entry['confidence'])}</p>"
            f'<h2><a href="prs/pr-{entry["number"]}.html">'
            f"PR #{entry['number']} · {escape(entry['title'])}</a></h2>"
            f"<p>{escape(entry['summary'])}</p>"
            f"<p class=\"meta\">{escape(entry['mergedAt'])} · {render_pr_url(entry['url'])}</p>"
            "</article>"
        )
    return """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>repo-walk PR 리포트</title>
<style>
:root { color-scheme: light; font-family: system-ui, sans-serif; color: #202124; background: #f6f8fa; }
body { margin: 0 auto; max-width: 920px; padding: 2rem 1rem 4rem; line-height: 1.6; }
.card { background: white; border: 1px solid #d0d7de; border-radius: 12px; margin: 1rem 0; padding: 1.25rem; }
.badge { background: #ddf4ff; border-radius: 999px; display: inline-block; padding: .15rem .55rem; }
.badge.critical { background: #ffebe9; color: #a40e26; }
.meta { color: #59636e; }
</style>
</head>
<body>
<header><h1>repo-walk PR 리포트</h1></header>
<main>""" + "".join(cards) + """</main>
</body>
</html>
"""


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: dict) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, content)


def rebuild_index(output_root: Path) -> Path:
    output_root = Path(output_root)
    reports_by_number = {}
    for data_path in sorted((output_root / "data").glob("pr-*.json")):
        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ReportValidationError(f"{data_path}을 읽을 수 없습니다.") from error
        validated = validate_report(payload)
        reports_by_number[validated["pr"]["number"]] = validated
    reports = sorted(
        reports_by_number.values(),
        key=lambda payload: (payload["pr"]["mergedAt"], payload["pr"]["number"]),
        reverse=True,
    )
    entries = [manifest_entry(payload) for payload in reports]
    atomic_write_json(
        output_root / "manifest.json",
        {"schemaVersion": 1, "reports": entries},
    )
    index_path = output_root / "index.html"
    atomic_write_text(index_path, render_index_html(entries))
    return index_path


def render_report(payload: dict, output_root: Path) -> Path:
    validated = validate_report(payload)
    output_root = Path(output_root)
    number = validated["pr"]["number"]
    atomic_write_json(output_root / f"data/pr-{number}.json", validated)
    unit_path = output_root / f"prs/pr-{number}.html"
    atomic_write_text(unit_path, render_unit_html(validated))
    rebuild_index(output_root)
    return unit_path


def main() -> None:
    payload = json.load(sys.stdin)
    json.dump(classify_pull_request(payload), sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
