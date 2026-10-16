from __future__ import annotations
import html
from pathlib import Path


DATE_SOURCE_LABELS: dict[str, str] = {
    "EXIF": "相機 EXIF",
    "GOOGLE_JSON": "Google JSON",
    "FILENAME": "檔名日期",
    "FOLDER": "相簿目錄",
    "FILESYSTEM": "檔案修改時間 (保底)",
    "CONFLICT": "日期衝突",
    "UNKNOWN": "未判定",
}

MEDIA_TYPE_LABELS: dict[str, str] = {
    "photo": "照片",
    "video": "影片",
    "unsupported": "非媒體/不支援",
}

PAIR_ROLE_LABELS: dict[str, str] = {
    "PRIMARY_PHOTO": "成對主照",
    "LIVE_PHOTO_VIDEO": "Live 動態短片",
    "RAW_PAIR": "RAW 原檔",
}

WARNING_LABELS: dict[str, str] = {
    "MEDIA_WITHOUT_JSON": "無對應 JSON",
    "JSON_ORPHAN": "孤兒 JSON",
    "AMBIGUOUS_SIDECAR": "多個候選 JSON",
    "DATE_CONFLICT": "日期來源衝突",
    "INVALID_JSON": "JSON 格式損毀",
    "CORRUPT_MEDIA": "媒體檔案損壞",
    "UNSUPPORTED_FORMAT": "非支援媒體格式",
    "NO_DATE": "無法判定日期",
    "UNKNOWN_DATE": "無法判定日期",
    "ZIP_PATH_TRAVERSAL": "不安全路徑已攔截",
    "ZIP_BOMB": "疑似壓縮炸彈已略過",
    "INVALID_ZIP": "壓縮檔損毀",
    "OUTPUT_COLLISION": "同名自動改名",
    "COPY_FAILED": "複製失敗",
    "HASH_MISMATCH": "雜湊驗證不符",
}


def _render_warning_badges(warnings: list[str]) -> str:
    if not warnings:
        return '<span class="badge badge-ok">✓ 正常</span>'
    parts = []
    for w in warnings:
        code = w.split(":", 1)[0]
        label = WARNING_LABELS.get(code, code)
        cls = "badge-warn" if code in ("DATE_CONFLICT", "AMBIGUOUS_SIDECAR", "INVALID_JSON", "HASH_MISMATCH") else "badge-muted"
        parts.append(f'<span class="badge {cls}" title="{html.escape(w)}">{html.escape(label)}</span>')
    return " ".join(parts)


def write_report(manifest: dict, path: Path) -> None:
    summary = manifest.get("summary", {})
    records = manifest.get("media_records", [])
    dup_groups = manifest.get("duplicate_groups", [])

    total_media = summary.get("total_media", len(records))
    photos = summary.get("photos", 0)
    videos = summary.get("videos", 0)
    json_matched = summary.get("json_matched", 0)
    dup_files = summary.get("duplicate_files", 0)
    paired_groups = summary.get("paired_groups", 0)
    review_count = sum(
        1 for r in records
        if (r.get("planned_output_path") or "").startswith(("Review/", "待人工確認/"))
    )

    rows = []
    for item in records:
        warnings_list = item.get("warnings", [])
        flags = " ".join(warnings_list)
        m_type = item.get("media_type", "unknown")
        m_label = MEDIA_TYPE_LABELS.get(m_type, m_type)
        pair_role = item.get("pair_role")
        pair_badge = f' <span class="badge badge-info">{html.escape(PAIR_ROLE_LABELS.get(pair_role, pair_role))}</span>' if pair_role else ""

        dup_status = item.get("duplicate_status", "UNIQUE")
        dup_badge = (
            '<span class="badge badge-dup">重複副本</span>'
            if dup_status == "DUPLICATE"
            else '<span class="badge badge-primary">主檔案 (有重複)</span>'
            if dup_status == "PRIMARY"
            else '<span class="text-muted">唯一</span>'
        )

        date_val = item.get("resolved_date") or "未判定"
        date_src = item.get("date_source", "UNKNOWN")
        date_src_label = DATE_SOURCE_LABELS.get(date_src, date_src)

        planned_out = item.get("planned_output_path") or ""
        is_review = planned_out.startswith(("Review/", "待人工確認/"))
        is_paired = bool(item.get("pair_group_id"))

        filter_tags = [m_type, dup_status, item.get("json_status", ""), flags]
        if is_review:
            filter_tags.append("REVIEW_ITEM")
        if is_paired:
            filter_tags.append("PAIRED_ITEM")
        if not item.get("resolved_date"):
            filter_tags.append("Unknown")

        rows.append(
            f'<tr data-type="{html.escape(m_type)}" data-tags="{html.escape(" ".join(filter_tags))}">'
            f'<td class="col-name"><strong>{html.escape(item.get("original_filename", ""))}</strong>{pair_badge}'
            f'<div class="sub-path">{html.escape(item.get("relative_path", ""))}</div></td>'
            f'<td>{html.escape(m_label)}</td>'
            f'<td class="mono">{html.escape(date_val)}</td>'
            f'<td><span class="badge badge-neutral">{html.escape(date_src_label)}</span></td>'
            f'<td>{dup_badge}</td>'
            f'<td class="mono col-plan">{html.escape(planned_out)}</td>'
            f'<td>{_render_warning_badges(warnings_list)}</td>'
            f'</tr>'
        )

    group_rows = []
    for g in dup_groups:
        albums_str = "、".join(g.get("album_names", [])) or "無特定相簿"
        group_rows.append(
            f'<li><strong>群組 {html.escape(g.get("group_id", ""))}</strong> '
            f'（共 {len(g.get("members", []))} 個相同檔案 · SHA-256 指紋：<code>{html.escape(g.get("sha256", "")[:16])}…</code> · '
            f'相簿：{html.escape(albums_str)}）</li>'
        )
    dup_section = (
        f'<div class="card dup-card"><h2>重複檔案指紋群組（共 {len(dup_groups)} 組）</h2>'
        f'<ul class="dup-list">{"".join(group_rows)}</ul></div>'
        if group_rows
        else ""
    )

    html_doc = f"""<!doctype html>
<html lang="zh-Hant-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Google 相簿 Takeout 整理與驗證報告</title>
<style>
  :root {{
    --bg: #F8FAFC;
    --surface: #FFFFFF;
    --border: #E2E8F0;
    --text: #0F172A;
    --text-sec: #475569;
    --text-muted: #94A3B8;
    --primary: #2563EB;
    --primary-bg: #EFF6FF;
    --ok-text: #166534;
    --ok-bg: #F0FDF4;
    --ok-border: #BBF7D0;
    --warn-text: #92400E;
    --warn-bg: #FFFBEB;
    --warn-border: #FDE68A;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 32px 24px;
    font-family: "Microsoft JhengHei UI", "Segoe UI", system-ui, sans-serif;
    background-color: var(--bg);
    color: var(--text);
    line-height: 1.5;
  }}
  .container {{ max-width: 1280px; margin: 0 auto; }}
  header {{ margin-bottom: 24px; }}
  h1 {{ margin: 0 0 6px 0; font-size: 22px; font-weight: 700; color: var(--text); }}
  .subtitle {{ margin: 0; font-size: 13px; color: var(--text-sec); }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }}
  .kpi-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
  }}
  .kpi-label {{ font-size: 12px; color: var(--text-sec); font-weight: 600; margin-bottom: 4px; }}
  .kpi-value {{ font-size: 22px; font-weight: 700; color: var(--text); }}
  .kpi-sub {{ font-size: 11px; color: var(--text-muted); margin-top: 2px; }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 20px;
  }}
  .toolbar {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }}
  .filter-group {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  button.filter-btn {{
    background: var(--surface);
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-sec);
    cursor: pointer;
    transition: all 0.15s ease;
  }}
  button.filter-btn:hover {{ background: #F1F5F9; color: var(--text); }}
  button.filter-btn.active {{
    background: var(--primary);
    border-color: var(--primary);
    color: #FFFFFF;
  }}
  .search-box {{
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  input.search-input {{
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    min-width: 240px;
    color: var(--text);
  }}
  input.search-input:focus {{ outline: none; border-color: var(--primary); }}
  .count-label {{ font-size: 12px; color: var(--text-sec); font-weight: 600; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th {{
    background: #F8FAFC;
    color: var(--text-sec);
    font-weight: 600;
    text-align: left;
    padding: 10px 12px;
    border-bottom: 2px solid var(--border);
    white-space: nowrap;
  }}
  td {{
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  tbody tr:hover {{ background-color: #F8FAFC; }}
  .sub-path {{ font-size: 11px; color: var(--text-muted); margin-top: 2px; word-break: break-all; }}
  .mono {{ font-family: Consolas, "SFMono-Regular", monospace; font-size: 12px; }}
  .col-plan {{ color: #1E40AF; word-break: break-all; }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }}
  .badge-ok {{ background: var(--ok-bg); color: var(--ok-text); border: 1px solid var(--ok-border); }}
  .badge-warn {{ background: var(--warn-bg); color: var(--warn-text); border: 1px solid var(--warn-border); }}
  .badge-info {{ background: var(--primary-bg); color: var(--primary); border: 1px solid #BFDBFE; }}
  .badge-dup {{ background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }}
  .badge-primary {{ background: #F0FDF4; color: #166534; border: 1px solid #BBF7D0; }}
  .badge-neutral {{ background: #F1F5F9; color: #334155; border: 1px solid #E2E8F0; }}
  .badge-muted {{ background: #F8FAFC; color: #64748B; border: 1px solid #E2E8F0; }}
  .text-muted {{ color: var(--text-muted); font-size: 12px; }}
  h2 {{ font-size: 16px; margin: 0 0 12px 0; }}
  .dup-list {{ margin: 0; padding-left: 20px; font-size: 13px; color: var(--text-sec); }}
  .dup-list li {{ margin-bottom: 6px; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Google 相簿 Takeout 整理與驗證報告</h1>
    <p class="subtitle">本報告由 Google 相簿 Takeout 整理工具 (v{html.escape(str(manifest.get("app_version", "1.3.0")))}) 自動產出 · 原始檔案維持唯讀無修改</p>
  </header>

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">總媒體檔案</div>
      <div class="kpi-value">{total_media:,}</div>
      <div class="kpi-sub">照片 {photos:,} · 影片 {videos:,}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">中繼資料 (JSON) 配對</div>
      <div class="kpi-value">{json_matched:,}</div>
      <div class="kpi-sub">共掃描 {summary.get("json_total", 0):,} 個 JSON</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">重複檔案自動隔離</div>
      <div class="kpi-value">{dup_files:,}</div>
      <div class="kpi-sub">分屬 {len(dup_groups):,} 組相同 SHA-256 指紋</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">動態照片 / RAW 成對</div>
      <div class="kpi-value">{paired_groups:,} 組</div>
      <div class="kpi-sub">Live Photo 與 RAW 同步歸檔</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">待人工確認項目</div>
      <div class="kpi-value">{review_count:,}</div>
      <div class="kpi-sub">日期衝突或多重候選</div>
    </div>
  </div>

  <div class="card">
    <div class="toolbar">
      <div class="filter-group">
        <button class="filter-btn active" onclick="setFilter('', this)">全部 ({len(records)})</button>
        <button class="filter-btn" onclick="setFilter('photo', this)">照片 ({photos})</button>
        <button class="filter-btn" onclick="setFilter('video', this)">影片 ({videos})</button>
        <button class="filter-btn" onclick="setFilter('PAIRED_ITEM', this)">Live Photo / RAW 成對</button>
        <button class="filter-btn" onclick="setFilter('DUPLICATE', this)">重複副本 ({dup_files})</button>
        <button class="filter-btn" onclick="setFilter('REVIEW_ITEM', this)">待人工確認 ({review_count})</button>
        <button class="filter-btn" onclick="setFilter('MEDIA_WITHOUT_JSON', this)">無對應 JSON ({summary.get("no_json", 0)})</button>
      </div>
      <div class="search-box">
        <input type="search" id="searchInput" class="search-input" placeholder="搜尋檔名、日期或輸出路徑…" oninput="applyFilters()">
        <span id="rowCount" class="count-label">顯示 {len(records)} 筆</span>
      </div>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>原始檔名 / 來源路徑</th>
            <th>類型</th>
            <th>判定日期</th>
            <th>日期依據</th>
            <th>重複狀態</th>
            <th>規劃輸出位置</th>
            <th>狀態與提示</th>
          </tr>
        </thead>
        <tbody id="reportBody">
          {"".join(rows)}
        </tbody>
      </table>
    </div>
  </div>

  {dup_section}
</div>

<script>
let currentTag = '';
function setFilter(tag, btn) {{
  currentTag = tag;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  applyFilters();
}}
function applyFilters() {{
  const q = (document.getElementById('searchInput').value || '').toLowerCase().trim();
  const rows = document.querySelectorAll('#reportBody tr');
  let visible = 0;
  for (const r of rows) {{
    const tags = r.dataset.tags || '';
    const text = r.innerText.toLowerCase();
    const matchTag = !currentTag || tags.includes(currentTag) || r.dataset.type === currentTag;
    const matchSearch = !q || text.includes(q);
    const show = matchTag && matchSearch;
    r.hidden = !show;
    if (show) visible++;
  }}
  document.getElementById('rowCount').textContent = '顯示 ' + visible + ' / ' + rows.length + ' 筆';
}}
</script>
</body>
</html>"""
    path.write_text(html_doc, encoding="utf-8")
