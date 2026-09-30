# 評価6: ADL解釈ラベル集合一致とLLM使用量（AI向け詳細）

**正本:** [docs/evaluations/evaluation_6_adl_interpretation_set.md](../../docs/evaluations/evaluation_6_adl_interpretation_set.md)
**CLI / 実装 / テスト:** `scripts/evaluate_6_compare_adl_interpretation_set.py` → `src/behavior_pattern_mining/evaluation/adl_interpretation_set.py`, `llm_usage.py` → `tests/test_evaluation6_adl_interpretation_set.py`, `tests/test_evaluation6_default_days.py`

## 目的と比較の単位

提案手法のLLMが付けた`ADL系列ラベル`集合と、パターン出現区間がCASAS正解ADL区間へ重なることで得た集合を比較する。ラベル順序、パターン名、自然言語根拠の文章自体は採点しない。ただしパターン名・ADL集合・根拠は同一の解釈出力なので、本評価はその解釈の主要な定量代理評価である。

提案手法と、同じ14日間の前処理済み代表状態系列を直接LLMへ渡す`direct_log_baseline`を比較する。両手法の抽出・LLM入力は先頭14日であり、固定した状態定義を全220日へ写像したstate seriesを共用する。ただし正式holdoutでは出現検索とADL照合をDay 155–220だけに制限する。Day 15–154は評価7のK,h選択専用であり、評価6には混ぜない。

これはFull-pipelineトラックの説明である。Strictは共通prompt/schema等を固定し、両手法完了runの積集合でpaired評価する別トラック。入口は [run_evaluation6_strict_ablation.py](../../scripts/run_evaluation6_strict_ablation.py)、[evaluate_6_strict_ablation.py](../../scripts/evaluate_6_strict_ablation.py)、テストは [test_evaluation6_strict_ablation.py](../../tests/test_evaluation6_strict_ablation.py)。保存済み比較の読み方は [結果引継ぎ](../RESULTS_AND_WRITING.md) を参照。

提案手法は時間帯別状態遷移ネットワーク、LLM-onlyは同じ Morning / Daytime / Night / Midnight ごとの代表状態系列をLLMへ渡す。split方式では、Hamming写像後の連続同一代表状態を各時間帯内だけで圧縮し、両手法とも`sequence × time_period`を評価単位とする。`[start,end)`全体が当該時間帯に収まるexact出現だけを採る（境界横断は除外して監査）。LLM-onlyの旧1入力方式は`--llm-only-time-mode legacy`で再現できる。

## 集合、状態、分母

許可予測語彙は `Sleep, Wake-up, Meal, Relax, Outing, Hygiene, Toileting, Housework, Work, Other` の10カテゴリだけ。大文字小文字・Wake-upのハイフン等のみ正規化する。CASAS生ラベルを別名として受理しない。欠落は`missing`、語彙外を1つでも含む予測は`unknown`であり、`Other`へ変換せずrawラベルを保存し0点にする。

| 状態 | conditional | end-to-end |
|---|---:|---:|
| matched + true set defined | 採点 | 採点 |
| `no_occurrence` | 除外 | 0点で含める |
| `no_adl_overlap` | 除外 | 除外（正解集合が未定義） |
| `prediction_status=missing/unknown` | 0点で含める | 0点で含める |

両スコープでExact Set Match、Jaccard、multi-label Precision/Recall/F1を出す。旧`mean_*`はend-to-endの別名。coverage、状態別件数・率、時間帯境界横断件数/率も必ず出す。`truth_coverage`と`no_adl_overlap_rate`の分母は出現あり、それ以外の状態率の分母は全レコード。

真の集合は各出現のADLカテゴリ重なりを合計し、`category_overlap / total_overlap >= 0.10`のカテゴリで作る。raw multi-labelの例: `Bed_to_Toilet→Wake-up+Toileting`、`Bathroom/Personal_Hygiene→Wake-up+Hygiene`、`Wash_Dishes→Meal+Housework`。

## 正式条件と実行順序

正式holdoutのK/hは固定値ではなくEvaluation 7のbest-condition manifestを正本とする。manifestからK/h、sensor representation、generation日数、期間境界とcanonical成果物パスを同時に解決し、不一致の手動指定は停止する。次を順に作る。

1. ラベル付きCASASから14日条件の状態表・ネットワークを作る。
2. 現モデルの提案LLM JSONを1回（または5回）生成する。
3. その状態表を固定した全220日照合state seriesを `output/<model>/` のmanifestに対応する条件別パスへ作る。正式workflowは`network-equivalent`、network構築と同じ5秒の遅延OFF平滑化を明示し、`--state-series-days`は指定しない（KI-06採用済み仕様）。
4. 同じ14日代表状態系列を4時間帯に分け、direct-log baselineを1回（または5回）生成する。direct-logも提案手法と同じ `map_vector_to_state` のHamming写像を使う（KI-04採用済み仕様）。
5. 比較CLIへbest-condition manifestとlabeled CASASを渡す。正式holdoutでは成果物パス・K/h・期間値を個別指定しない。

前段のnetwork・提案抽出・direct抽出のK/h・センサ表現は、選定manifestと揃える。K=15/h=0を現行結果へ一律適用しない。具体的な前段CLIは正本の実行手順を参照し、manifestの出所モデルとLLM実行モデルを区別する。比較は次の形である。

```bash
uv run python scripts/evaluate_6_compare_adl_interpretation_set.py \
  --best-condition-manifest results/<model>/7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json \
  --labeled-casas new_labeled_data/aruba.txt \
  --llm-only-time-mode split \
  --min-overlap-ratio-for-true-label 0.10
```

5 runには`--runs 5`を追加する。metrics templateやdirect metricsを明示する場合も、manifestに対応するセンサ表現・K/h・日数・現在モデルのcanonicalパスを使い、旧15/0固定パスへ戻さない。

新規のstate series・ADL intervalは`output/<model>/`、proposed/direct JSON、checkpoint、usage、比較結果は`results/<model>/`である。ルート直下の旧`output/*`/`results/*`はGemini移行元。KI-08はmanifestによる正式holdout条件解決として採用済みであり、比較CLIへ条件やパスを重複指定しない。manifestなしのholdoutはK/h明示が必要。共通既定値のKI-01と区別する。

## 出力・run集計・使用量

- `evaluation6_method_comparison.csv`は主比較、`..._by_run.csv`はrunごとの元データ、`...pattern_set_details_by_method.csv`は状態とrawラベルを含む根拠である。
- label別`evaluation6_by_pred_label_by_method.csv`、true label別`evaluation6_by_true_label_by_method.csv`、time band別`evaluation6_by_time_band_by_method.csv`、`evaluation6_comparison_summary.json`も保存する。評価8はdetails CSVを入力として使うため、列・分母・`num_occurrences`を軽率に変更しない。
- `--runs 5`では提案手法とdirect-logをそれぞれ独立に平均する。欠損JSON/runを許すなら`--skip-missing-runs`。共通runへ自動制限しない点、run等重みかdetail poolかの正式集計は **KI-09**。
- usage CSVは1 runの抽出全体を比較する。split方式では提案手法・directともに4時間帯の成功API呼出し合計を使い、directの時間帯別prompt/completion/API total tokensとrun合計を保存する。完全な記録を持つrunだけで平均し、欠損を0補完しない。Geminiの`totalTokenCount`はprompt+thoughts+candidatesであり、可視入力+出力の単純和ではない。

## 変更してはいけないこと

- `no_adl_overlap`を0点へ変えない。これはモデル免責でなく、正解未定義を誤りに偽装しない契約である。
- 既定主評価の`match_mode=exact`を`skip-other`へ置換しない。後者は感度確認用。
- prediction欠落・語彙外を分母から除外しない。時間帯横断出現を採点へ混ぜない。
