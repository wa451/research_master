# 評価4〜10: AI引継ぎ用の詳細仕様

このディレクトリは、Codex・ChatGPTなどへ評価の目的、研究上の境界、入出力契約、実行条件を渡すためのAI向け説明である。各ファイルは単独でも読めるように書かれている。

人間向けの研究仕様の正本は `docs/evaluations/` であり、本ディレクトリはそれを置換しない。指標、閾値、split、seed、baseline、出力CSV/JSONの列を変更する依頼では、対象の正本・実装・テストを必ず照合すること。未解決の研究上の不一致は [../KNOWN_ISSUES.md](../KNOWN_ISSUES.md) を参照する。

| 評価 | AI向け説明 | 対象 |
|---:|---|---|
| 4 | [eval4_adl_interval.md](eval4_adl_interval.md) | ラベル付きCASASに対する単一パターン集合のADL区間評価 |
| 5 | [eval5_pattern_quality.md](eval5_pattern_quality.md) | 手法別の有用性・断片化・無文脈性 |
| 6 | [eval6_adl_label_sets.md](eval6_adl_label_sets.md) | 提案手法とLLM単独のADLラベル集合一致 |
| 7 | [eval7_parameter_sensitivity.md](eval7_parameter_sensitivity.md) | 提案手法のK/h感度分析と上位条件反復 |
| 8 | [eval8_frequency_stratified.md](eval8_frequency_stratified.md) | 出現頻度帯別のADL集合整合性 |
| 9 | [eval9_hestia.md](eval9_hestia.md) | Hestia合成ログの系列回収・ADL意味対応 |
| 10 | [eval10_switchbot_holdout.md](eval10_switchbot_holdout.md) | SwitchBot実宅ログの時間ホールドアウト再出現 |

## 全評価に共通する作業規則

- 生データ、ラベル、`data/`、生成済み `output/`・`results/` は変更・コミットしない。実験を実行する前に、API呼出し、入力条件、出力先を確認する。
- 評価5〜10のLLM由来JSON、checkpoint、usage、評価結果は現在モデルごとに `results/<model>/` 配下へ分離する。状態系列、baseline、状態定義など明示的にモデル非依存とされた中間物は `output/`・`state/`・`picture/` に残る。評価4のCLI出力既定は現在も共有の `results/4_adl_detect/` であるため、モデル分離済みと仮定しない。古い `output/aruba_*` や `results/N_*` 表記はGemini移行元を示すことがある。
- Streamlitは既存CLIを呼ぶ薄い画面であり、評価ロジックをアプリへ複製しない。APIを伴う評価9・10では明示的なopt-inが必要である。
- 評価4〜8のCASAS関連評価は、ラベル付き入力 `new_labeled_data/aruba.txt` とラベルなし `data/aruba.csv` / `data/aruba.txt` を取り違えない。state seriesの前処理条件、K、ハミング距離、日数を前段と下流で混在させない。
- `mean_*` の後方互換列は評価6〜8では原則end-to-end値の別名である。conditionalとend-to-endの分母を混同しない。
