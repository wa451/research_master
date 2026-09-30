# 評価結果の読み方

[結果閲覧の入口](README.md)に戻る。以下は2026-10-01に確認した保存済みモデル比較表の案内です。表は[比較ディレクトリ](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/)にまとまっています。

## 評価と研究上の問い

| 評価 | 確認する問い | 最初に読む結果 | 併せて確認する情報 |
|---|---|---|---|
| 5: パターン品質 | 抽出した系列はADLに対応し、冗長性を抑えられるか | [手法別品質表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval5.md) | 出力数、有用系列の絶対数、評価可能数、断片化の比較可能ペア数。定義は[評価5](../evaluations/evaluation_5_adl_correspondence.md) |
| 6 Full: 全工程比較 | 実際の二つの処理系でADL集合の整合性がどう違うか | [Full比較表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval6_full.md) | end-to-endとconditional、出現被覆率、予測欠損・未知ラベル。定義は[評価6](../evaluations/evaluation_6_adl_interpretation_set.md) |
| 6 Strict: 入力表現の比較 | prompt・schema等を揃えたときSTN入力の差は残るか | [Strict比較表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval6_strict.md)、[paired ΔF1](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval6_strict_delta_f1.md) | 両手法完了runの積集合、固定契約、[run別表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval6_strict_by_run.md) |
| 7: 条件感度 | K/hへの依存と選定理由は何か | [条件別表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval7.md) | 全28条件、5 run、Day 15–154 validation、[best manifest](../../results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json)。定義は[評価7](../evaluations/evaluation_7_parameter_sensitivity_adl_interpretation.md) |
| 8: 頻度層別 | 出現頻度別にADL整合性がどう変わるか | [頻度帯別表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval8.md) | `mode=fixed` と `tertile`、帯ごとの件数、出現なし、重み付き値。定義は[評価8](../evaluations/evaluation_8_frequency_stratified_adl_consistency.md) |
| 9: Hestia | 家屋条件・期間による性能変化はどうか | [条件×期間表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval9.md)、[seed/run別表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval9_runs.md) | experiment、train/test日数、condition、seed、完了行数、F1・episode被覆率・断片化。定義は[評価9](../evaluations/evaluation_9_hestia.md) |
| 10: 実宅 | 過去に抽出した同時間帯系列が未来にも出るか | [実宅比較表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval10.md)、[run別表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval10_by_run.md) | 抽出数、未来に出た数、FRR、日単位再現率、時間帯・長さ別。定義は[評価10](../evaluations/evaluation_10_switchbot_holdout.md) |

評価1〜4は[既存の評価文書一覧](../../README.md#評価文書)から確認できます。今回の比較表の中心は評価5〜10であり、旧評価の結果を削除したり、採用不可と判断したりしたものではありません。

## 数値を取り違えやすい箇所

1. **評価7のF1はvalidation。** 選定に使った値を独立test性能として書かない。評価6のtestと表を分けます。
2. **FullとStrictは別の比較。** Fullには処理系全体の差が入り、Strictは共通prompt/schemaなどを固定しています。StrictのF1がFullより高いことだけで、Strictへの変更効果は推定できません。
3. **conditionalとend-to-endは分母が違う。** 出現なしを含むかを確認します。正解ADLが未定義のレコードは別扱いです。missing/unknown predictionを都合よく除外しないでください。
4. **評価8の空の帯は性能0と同じではない。** `num_runs_with_patterns` と分母を読みます。モデル間比較は共通の固定binを先に確認し、tertileは分位別の補足として扱います。
5. **評価9は条件を揃えて比較。** `train_days=14` 等を明示し、日数が空欄のfull行とduration行を一つの平均へまとめないでください。seedとLLM runを区別します。
6. **評価10のFRRと日単位再現率は別。** 主指標FRRは `test_supported_pattern_fraction_mean`。`mean_test_day_recurrence_mean` は補助指標です。既存overviewの `FRR_mean` 列は後者の値になっているため、本文・図には評価10の専用表と列名を使います。
7. **標準偏差は有意差の検定結果ではない。** 5 runのばらつきとして報告し、paired ΔF1の正の平均だけで「有意に改善」と書かないでください。

## 元集計・査読対応集計・凍結結果

| 結果集合 | 用途 | 注意 |
|---|---|---|
| モデル比較 | Sol/Fableの既存結果を横に並べる | [比較条件監査](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/comparison/comparability_audit.md)と[検査報告](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/sanity_check/sanity_check_report.md)を読む。監査の範囲は結果報告に書かれた検査に限る |
| 査読対応版 | 指摘に対応したSolの集計・人手評価セット | [rerun3 summary](../../results/gpt-5.6-sol/reviewer_response/20260929_final_rerun3/reviewer_response_evaluation_summary.md)。[別集計の方針](../evaluations/reviewer_response_final_pipeline.md)では断片化ペアなしをN/Aにする。元集計の0と混在させない |
| 凍結snapshot | 掲載表の出所とSHA-256を追う | [Sol checksum](../../results/final_evaluation_snapshot/gpt-5.6-sol/checksum_manifest.json)、[Fable checksum](../../results/final_evaluation_snapshot/claude-fable-5/checksum_manifest.json)。hard linkで作られたファイルもあるため、コピーが常に独立しているとは限らない |

比較表は既存ファイルを読むための派生資料です。今回の閲覧整理で各指標を再計算したり、全snapshotのchecksumを検証したりはしていません。
