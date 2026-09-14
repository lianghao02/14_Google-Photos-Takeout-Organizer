# Project rules

- Takeout sources are read-only inputs.
- Export is copy-only and manifest-driven.

---

## 共用 Skill 引用與動態解析 (Discovery Rule)
- 本專案遵循 LiangHao 全生態系標準規範 Skill：`lianghao-development`（Canonical Source 位於 `Dev-Control-Center/skills/lianghao-development`，v1.0.0）。
- Agent 開始工作時：
  1. 優先使用目前環境可自動發現的 `lianghao-development` Skill
  2. 若平台未自動載入，使用既有動態解析順序：環境變數 `LIANGHAO_SKILL_HOME` ➜ `%USERPROFILE%\.lianghao\config.json` ➜ 鄰近工作區探索 `..\00_Dev-Control-Center\skills\lianghao-development` 或呼叫其 `skill-resolver.ps1`
  3. 先讀 Shared Skill
  4. 再讀本專案 `AGENTS.md`
  5. 再讀目前 `HANDOFF.md` / `IMPLEMENTATION_PLAN.md`
  6. 專案、Git、測試與建置實際狀態優先於文件歷史
- 跨 Agent HANDOFF 一律使用 `lianghao-development` 標準範本，以 `Repository Full Name`、`Branch`、`Commit SHA`、`Task Type` 為主要識別，嚴禁複製 Skill 到本專案。
