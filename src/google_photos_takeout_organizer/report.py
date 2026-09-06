from __future__ import annotations
import html, json
from pathlib import Path

def write_report(manifest: dict, path: Path) -> None:
    rows = []
    for item in manifest["media_records"]:
        flags = " ".join(item["warnings"])
        rows.append(f'<tr data-type="{item["media_type"]}" data-flags="{html.escape(flags)}"><td>{html.escape(item["original_filename"])}</td><td>{html.escape(item["relative_path"])}</td><td>{item["media_type"]}</td><td>{item["resolved_date"] or "Unknown"}</td><td>{item["date_source"]}</td><td>{item["json_status"]}</td><td>{item["duplicate_status"]}</td><td>{html.escape(item["planned_output_path"] or "")}</td><td>{html.escape(flags)}</td></tr>')
    group_rows = "".join(f'<li><b>{g["group_id"]}</b>: SHA-256 {g["sha256"]}; primary {g["primary"]}; members {len(g["members"])}; albums {html.escape(", ".join(g["album_names"]))}</li>' for g in manifest["duplicate_groups"])
    data = json.dumps(manifest["summary"])
    path.write_text(f'''<!doctype html><meta charset="utf-8"><title>Takeout Review</title><style>body{{font:14px Segoe UI,sans-serif;margin:2rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.4rem;text-align:left}}button{{margin:.2rem}}</style><h1>Google Photos Takeout Review</h1><pre>{html.escape(data)}</pre><p><button onclick="filter('')">All</button><button onclick="filter('photo')">Photos</button><button onclick="filter('video')">Videos</button><button onclick="filter('Unknown')">Unknown Date</button><button onclick="filter('DATE_CONFLICT')">Date Conflict</button><button onclick="filter('MEDIA_WITHOUT_JSON')">No JSON</button><button onclick="filter('DUPLICATE')">Duplicates</button></p><table><thead><tr><th>Name</th><th>Source</th><th>Type</th><th>Date</th><th>Source</th><th>JSON</th><th>Duplicate</th><th>Plan</th><th>Warnings</th></tr></thead><tbody>{''.join(rows)}</tbody></table><h2>Exact Duplicate Groups</h2><ul>{group_rows}</ul><script>function filter(x){{for(const r of document.querySelectorAll('tbody tr'))r.hidden=x&&!r.innerText.includes(x)&&!r.dataset.type.includes(x)}}</script>''', encoding="utf-8")
