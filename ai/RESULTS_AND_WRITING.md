# 結果閲覧・考察・論文執筆の引継ぎ

確認日: 2026-10-01。人向け閲覧整備はcommit `9a446ef`。研究仕様や結果採用の決定はこのメモで代替しない。

## 作業の範囲と入口

- ユーザー方針: `state/`・`artifacts/` の整理は優先しない。既存評価結果を削除せず、人が全体像・結果を読み、考察・論文執筆へ進める導線を整える。
- 人向け正本: [入口](../docs/research/README.md) → [評価結果の読み方](../docs/research/results_guide.md)、[考察メモ](../docs/research/discussion_notes.md)、[執筆作業表](../docs/research/manuscript_plan.md)。考察は観測・仮説・追加確認を分けてあり、最終論文ではない。
- 資料追加・変更: [result_catalog.json](../docs/research/result_catalog.json) の `items`（既存MD・表示列・定義文書）と `resources`（明示許可するmetadata）。22資料の確認時点はcatalogの `checked_on`。
- 閲覧実装: [research_browser.py](../support/research_browser.py) の `read_catalog` / `parse_tables` / `allowed_files` / `source_payload` / `check_catalog`、画面は [HTML](../assets/research_browser.html)。起動は [start_research_browser.command](../start_research_browser.command) または `python3 support/research_browser.py --open`、localhost:8522。
- 標準ライブラリだけで既存Markdown表を読む。検索・表示列・並べ替えは閲覧上の操作。CSVは既存ファイルをそのまま渡す。研究指標の再計算、モデルAPI、成果物への書き込みはない。
- Streamlit実験画面とは別の閲覧入口。`app/` や評価CLIはこの作業で変更していない。画面の日本語列名は原列名の表示上の別名であり、CSV契約を変えない。

## 保存済み結果を読む順序

- モデル比較: [比較条件監査](../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/comparison/comparability_audit.md) → [検査報告](../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/sanity_check/sanity_check_report.md) → catalogで必要な評価表だけ読む。元集計・査読対応別集計・snapshotを同じ結果集合とみなさない。
- 条件・凍結の出所: [Sol snapshot manifest](../results/final_evaluation_snapshot/gpt-5.6-sol/snapshot_manifest.json)、[Fable snapshot manifest](../results/final_evaluation_snapshot/claude-fable-5/snapshot_manifest.json)。hard linkを含むため独立コピーとは限らない。前回はsnapshotの全checksum再検証をしていない。
- 現行比較はindividual、Solで選定したK=10/h=2を参照。[従来の掲載条件](../docs/research/paper_parameters.md)のGemini・K=15/h=0を一律適用しない。評価7はvalidation、評価6はtest、FullとStrictは別トラック。
- 指標列・断片化の注意、Fableの評価7未確認、人手評価待ちの入口は [KNOWN_ISSUES](KNOWN_ISSUES.md#結果閲覧考察執筆の注意)。採用結果集合・主モデル・追加実験は[執筆作業表](../docs/research/manuscript_plan.md)で未決定のまま。

## 検証と継続

- 静的参照検査: `python3 support/research_browser.py --check`。実API・評価処理・出力生成なし。結果が未配置のcheckoutではmissingを報告する。
- 閲覧動作のテスト: `python3 -m unittest discover -s tests -p 'test_research_browser.py'`。[5テスト](../tests/test_research_browser.py)は精度・欠損/0保持、MD解析、未配置、経路制限、HTTP read-onlyを確認する。秘密情報・blind key・非登録ファイルは閲覧対象外。
- 前回確認済み: 22資料の参照/列名、5テスト、JS構文、起動shell構文、文書リンク、メモ検査。作業前後で `results/` 全22,794ファイルの内容ハッシュが一致し、削除・変更なし。これを将来の作業の検証済み証拠へ流用しない。
- 前回のlocalhostアクセスはブラウザ側で拒否され、実画面は未確認。サーバーは確認後に終了済み。アクセス拒否を別ブラウザや間接操作で迂回しない。
- 次は採用結果・集計方針の確定、run/seed別確認、代表例の検討、人手評価、論文用図表・本文。評価の追加実行や指標修正は別の依頼と研究条件の確認を必要とする。
