# 評価4: ラベル付きCASASのADL区間評価（AI向け詳細）

**正本:** [docs/evaluations/evaluation_4_labeled_casas_adl.md](../../docs/evaluations/evaluation_4_labeled_casas_adl.md)
**CLI / 実装 / テスト:** `scripts/evaluate_adl_labels.py` → `src/behavior_pattern_mining/evaluation/adl.py` → `tests/test_adl_evaluation.py`

## 何を答える評価か

1つの系列パターンJSON（主に提案手法のLLM出力）を、ラベル付きCASAS ArubaのADL区間へ対応付ける後段評価である。各パターンの出現から予測ADL区間を作り、ADL別検出、時間区間の重なり、開始・終了境界、ADL区間内hitを調べる。複数手法のパターン品質比較は評価5であり、評価4の責務ではない。

評価対象のRQは「どのADLに対応するか」「Sleep/Wake-up/Meal/Outing/Relax等を検出できるか」「境界が一致するか」「近接マージと短時間除外で過剰な短出現を抑えられるか」である。

## 正解・予測・採点

- 正解は `new_labeled_data/aruba.txt` のactivity `begin/end` を区間化した `start_time, end_time, raw_label, adl_category`。ラベルなし `data/aruba.csv` は使用禁止。
- パターンは代表状態系列上を `exact`（標準）または互換用 `skip-other` で検索する。各出現についてADL区間との総重なりが最大のカテゴリを `assigned_adl` とする。
- 同一ADLの予測を `--merge-gap-minutes`（既定5分）以内でマージし、ADL別最小継続時間未満を除外してから採点する。推奨設定ファイルは `configs/adl_min_duration.json`（例: Sleep 600秒、Relax 180秒、Meal 120秒、Wake-up 30秒）。
- 指標はADL別Precision/Recall/F1（IoU 0.3・0.5）、Temporal IoU=`overlap/union`、TPペアの開始・終了境界誤差（分）、正解区間内に同ADL予測がある割合、予測が正解ADL区間へ重なる割合、pattern-to-ADL confidence（パターン出現時間に占める割当ADL重なり）である。

## 入力契約と状態系列

| 入力 | 正式な役割 |
|---|---|
| `new_labeled_data/aruba.txt` | ADL正解と代表状態系列再構築の入力 |
| `state/aruba_15_1_154days.txt` | 代表状態表の例。パターン抽出条件と一致させる |
| `configs/aruba_sensor_map.json` | CASASセンサーIDを状態表の列へ対応付ける |
| LLM pattern JSON | CLI既定は旧 `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json`。現在モデルのJSONを使う場合は `results/<model>/...` を `--patterns` で明示する |
| 既存 `state_series.csv` | `--state-series` 指定時だけ再構築を省略できる。ただし前処理・期間・K/hが一致する場合に限る |

`event-driven` はラベル付きCASASの全イベントから状態を再構築するCLI既定である。`network-equivalent` は抽出側の代表状態処理へ合わせる選択肢で、`--state-series-days` と `--smoothing-window-sec`（既定5秒）が使える。どちらを正式条件にするかは **KI-06** 未解決であるため、変更で勝手に統一しない。

splitなしは同じ期間でパターン→ADL対応付けと評価を行うdescriptive evaluationである。`--split-date` または `--train-ratio` を使うと対応付けを前期間、評価を後期間へ分けるが、正式なsplit位置付けは **KI-07** 未解決である。

## 標準の処理順

1. 条件に一致する代表状態表・ネットワークをラベル付きCASASだけから作る。
2. 同じK/h/days条件でLLMパターンJSONを作る（APIを使う）。
3. 評価CLIが状態系列を再構築または読み込み、パターン出現、ADL対応付け、マージ、最小継続時間除外、各種採点を行う。
4. 必要なら `--write-state-series` のCSVを評価5〜8の条件一致する下流入力として再利用する。

互換再現例（パターンJSONは現モデルのものを明示指定）:

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --state-table state/aruba_15_1_154days.txt \
  --sensor-map configs/aruba_sensor_map.json \
  --patterns results/<model>/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/4_adl_detect \
  --iou-thresholds 0.3 0.5 --wake-window-minutes 30 \
  --match-mode exact --max-skip-duration-minutes 1 --hamming-threshold 1 \
  --state-series-preprocessing event-driven --merge-gap-minutes 5 \
  --min-duration-config configs/adl_min_duration.json --hit-tolerance-minutes 10 \
  --write-state-series output/4_adl_detect/state_series.csv
```

## 成果物と読む順序

`pattern_occurrences.csv`（出現）、`pattern_adl_mapping.csv`（対応）、`merged_predictions.csv`、`filtered_predictions.csv`、IoU別の`adl_metrics_*`と`boundary_metrics_*`、`adl_interval_hit_metrics.csv`/details、`evaluation_summary.json`を出す。まずsummary・IoU 0.3・hit metricsで集計を確認し、次にdetailsでmissの理由を追い、最後にsummary内の入力・閾値・後処理条件を再現条件として確認する。

## 変更時に守ること

- 既存の前処理、代表状態抽出、LLM抽出をこの評価の都合で変えない。
- K/h、平滑化、前処理、日数をパターン生成とstate seriesで混在させない。h=0とh=1の正式条件不一致は **KI-01**。
- `Bathroom` / `Personal_Hygiene` / `Bathing` を時間帯非依存でWake-upとする規則は正式仕様未確定（**KI-07**）。変更・正当化しない。
- 評価4 CLIの`--output-dir`既定は共有の`results/4_adl_detect`で、評価5〜10のようなモデル別自動分離は実装されていない。複数モデルを実行する場合は、上書きを避ける出力先を明示し、その運用を研究条件として記録する。
- マージ幅・最小継続時間は指標を変えるため、変更時はsummaryと文書・テストを更新する。
