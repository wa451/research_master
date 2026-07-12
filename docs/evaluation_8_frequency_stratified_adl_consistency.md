# 評価8: 頻度帯別ADL整合性評価

## 目的

評価8は評価6のADL解釈ラベルset一致指標を置き換えない後段分析である。抽出済みパターンを代表状態系列上の出現回数でLow / Middle / Highに分け、高頻度パターンほどADLラベル整合性が安定するかを確認する。頻度が高いこと自体は有用性の十分条件として扱わない。

## 実行条件と入力

評価8は次の2条件を別々に実行・保存する。両者を同じCSVや出力ディレクトリへ混在させない。

| 条件 | scope | 入力 | 出力先 |
|---|---|---|---|
| 30日・手法比較 | `comparison_30days` | 評価6のproposed / direct-log詳細CSV | `results/e8_30_c_{K}_{hamming}/` |
| 154日・提案手法のみ | `proposed_154days` | 154日提案手法JSON 5 run、154日state series、ADL正解データ | `results/e8_154_p_{K}_{hamming}/` |

### 30日・手法比較

更新後の評価6詳細CSVを使う。

| 入力 | 役割 |
|---|---|
| `evaluation6_pattern_set_details_by_method.csv` | proposed / direct-log baselineを比較する詳細CSV。 |
| `evaluation6_pattern_set_details.csv` | 単一手法の詳細CSVとしても利用可能。 |

詳細CSVの `num_occurrences` は、その評価レコードの状態系列パターンが代表状態系列に出現した回数である。提案手法のtime-band awareレコードは `sequence × time_band` で数え、同一sequenceでも別の時間帯の出現を混ぜない。更新後の評価6詳細CSVにはこの列が含まれる。過去の評価6詳細CSVに列がない場合は、同じディレクトリの `evaluation6_comparison_summary.json` から `state_series`、`match_mode`、skip条件を読み、同じ状態系列上で自動再計算する。summaryがない場合だけ `--state-series` を明示指定する。

### 154日・提案手法のみ

`--analysis-scope proposed_154days` では、評価6と同じADLラベルset一致処理を提案手法だけに5 run実行し、各runで独立に頻度三分位を割り当てた後、帯別指標をrun平均する。LLM単独ベースラインは入力にも出力にも含めない。標準入力は次の通り。

| 入力 | 既定例 |
|---|---|
| 提案手法JSON | `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json` |
| 154日state series | `output/5_adl_evaluation/state_series.csv` |
| ADL正解データ | `new_labeled_data/aruba.txt` |

## 頻度帯の定義

既定の `tertile` は次の手順である。

1. methodごとに評価レコードを分ける。
2. `num_occurrences` 昇順、続いて `eval_pattern_id` などの識別子で安定ソートする。
3. できるだけ同数になるようLow、Middle、Highへ割り当てる。

同値を閾値で一括扱いしないため、各レコードは必ず1つの帯に属する。3件未満では、Lowから順に可能な帯だけが作られる。

## 出力

| ファイル | 内容 |
|---|---|
| `evaluation8_frequency_band_details.csv` | 評価6の詳細に `num_occurrences` と `frequency_band` を加えたレコード単位出力。 |
| `evaluation8_by_frequency_band.csv` | methodをまとめた頻度帯別集計。 |
| `evaluation8_by_frequency_band_by_method.csv` | 30日・手法比較だけで出力するmethod × frequency band別集計。提案手法のみでは重複するため出力しない。 |
| `evaluation8_occurrence_weighted_summary.csv` | methodごとの全体occurrence-weighted指標。 |
| `evaluation8_summary.json` | 入力、モード、method一覧、各集計を記録する再現用summary。 |

各頻度帯では、pattern単位平均のExact Set Match / Jaccard / multi-label Precision / Recall / F1と、出現回数で重み付けしたJaccard / Precision / Recall / F1を出力する。

複数runでは、`num_runs` を出力し、各runで独立に計算した帯別値の平均を保存する。`num_patterns` と `total_occurrences` もrun平均である。

## 実行方法

### 30日・手法比較

```bash
uv run python scripts/evaluate_8_frequency_stratified_adl_consistency.py \
  --analysis-scope comparison_30days \
  --evaluation6-details results/6_adl_match/15_1_30days/evaluation6_pattern_set_details_by_method.csv \
  --output-dir results/e8_30_c_30_2 \
  --frequency-band-mode tertile
```

### 154日・提案手法のみ

先に154日提案手法の `_1.json` から `_5.json` を生成する。

```bash
uv run python scripts/run_llm_extraction.py --days 154 --runs 5
```

```bash
uv run python scripts/evaluate_8_frequency_stratified_adl_consistency.py \
  --analysis-scope proposed_154days \
  --patterns-proposed output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --state-series output/5_adl_evaluation/state_series.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --n-states 30 \
  --hamming-threshold 2 \
  --days 154 \
  --runs 5 \
  --output-dir results/e8_154_p_30_2 \
  --frequency-band-mode tertile
```

30日比較の結果は `evaluation8_by_frequency_band_by_method.csv`、154日提案手法のみの結果は `evaluation8_by_frequency_band.csv` でLow / Middle / Highの`mean_multilabel_precision`、`mean_multilabel_recall`、`mean_multilabel_f1`を比較する。高頻度帯のPrecisionが高いかは、その値を確認して判断し、頻度のみから有用性を結論付けない。
