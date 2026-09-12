# 長期設計判断

確認日: 2026-09-09。採用済みの結論と理由だけを保持する。研究・互換性の基本制約は [AGENTS.md](../../AGENTS.md) を正本とし、ここへ複製しない。

- **段階的分離**: 前処理・写像・遷移集計は純粋関数へ分離し、`StateTransitionVisualizer` の出力統括は残す。JSON・図・状態表の契約を維持するため。一括再設計や成果物ディレクトリ統合は行っていない。詳細: [refactoring_plan.md](../refactoring_plan.md)。
- **互換設定層**: `experiment_config.py` の定数公開を残す理由は既存モジュール互換。YAMLが全CLI・パスを支配するとはみなさない。詳細: [code_inventory.md](../code_inventory.md#共通設定の注意)。
- **LLM抽出の保全**: `tests/test_llm_prompt_files_unchanged.py` はprompt 2件と抽出Python 2件のファイル全体をSHA-256で固定する。構造整理でも失敗し得るため、単なる期待ハッシュ更新で通さず変更目的・LLM条件への影響を確認する。過去にもこの制約を理由に抽出2ファイルを整理対象外にした（下記履歴、現行テストと照合済み）。
- **評価5のlow-information**: 比率は診断専用でUseful/Contextlessの判断に使わない。旧列は空欄、旧閾値引数は受理して無視する互換契約。Fragmentationの比較可能pairが0でも率は0とし、抑制効果の実証とは解釈しない。詳細: [評価5](../evaluation_5_adl_correspondence.md)。
- **メモの分担**: 安全・共通手順はAGENTS、場所はCODEBASE_MAP、評価の文書/CLI/実装/テスト対応は [EVALUATION_ROUTES](EVALUATION_ROUTES.md) の該当節、理由は本ファイル、研究上の問題の正本は既存docs。情報を二重管理しない。保守とサイズ目安は [codex-memory-maintenance](../../.agents/skills/codex-memory-maintenance/SKILL.md)。
- **読込方式**: 全メモ自動添付や全体探索は避け、番号が分かれば評価節へ直行する。skillsの名前・説明は発見用に短く、本文は対象作業時だけ読む。根拠: [公式AGENTS.mdガイド](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[公式skillsガイド](https://learn.chatgpt.com/docs/build-skills)。新skillはメモ保守に限定し、通常作業の入口は増やさない。

履歴の根拠（LLM保全の理由のみ）: provider `codex`; ctx session `ca2451ee-85d5-739e-bf5b-69eefcb4d8bd`; event `ddd43ce4-8b3a-76d9-a330-fb766eaf1f1e`; provider session `019f8834-a999-7053-9977-13e4b52e16c3`。通常は再検索不要。
