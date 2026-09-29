# 評価10: SwitchBot実宅ログの将来再現性評価

評価10は、正解ADLラベルを持たない実宅SwitchBotログに対し、過去期間から得た状態遷移パターンが未来期間に同じ条件で再出現するかを測る評価である。これはADL分類精度、住人識別、行動解釈の正しさを主張する評価ではない。

旧来の `output/<model>/10_switchbot/` と `results/<model>/10_switchbot/` はパイロット成果物として保持する。正式版は必ず次へ新規保存する。

```text
output/<model>/10_real_home_temporal_generalization/<期間>/
results/<model>/10_real_home_temporal_generalization/<期間>/
```

既存成果物がある出力先への準備、抽出、評価は停止する。過去の実行を消去・上書きしてはならない。

## 入力と固定条件

入力snapshotは `data/switchbot/YYYY-MM-DD_YYYY-MM-DD/` の `events.csv` と `manifest.json` である。CSVはヘッダーなしの `date,time,sensor,value` 4列、manifestはSwitchBot Logger schema version 1でなければならない。source期間、出力行数、タイムゾーン、入力SHA-256を検証する。

正式版のK/hは次のEvaluation 7 manifestのみから読む。CLIの `--n-states` または `--hamming-threshold` がこの値と異なれば即時に失敗する。

```text
results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout/
  evaluation7_best_condition_manifest.json
```

現在の正式条件は個別センサ表現、`K=10`、`h=2` である。LLM抽出は固定で5 runであり、run数を変更する正式実行は受け付けない。

## 時間分割と漏洩防止

snapshotの完全な現地カレンダー日を時系列順に並べ、先頭70%（端数切捨て）をtrain、残り30%をtestにする。最低1日ずつを確保し、境界は現地時刻の00:00である。`--split-at` はこの境界を明示する場合だけ使用する。

- sensor列、sample-and-hold、因果的な遅延OFF平滑化、代表状態上位K、hamming写像、状態表、STN、候補系列はtrainイベントだけから構築する。
- testベクトルはtrain状態表だけに写像する。test専用センサは表現次元や代表状態を変えず、無視件数をmanifestに記録する。
- sample-and-holdの状態は時系列順に進めるため、train最終状態をtest開始時に持ち越すが、testイベントをtrain側の代表状態・STN・LLM入力に使わない。
- testを見てK/h、閾値、候補数、プロンプトを選び直してはならない。準備後に入力snapshotまたはEval7 manifestのhashが変われば後段は停止する。
- 系列・遷移は日境界・時間帯境界をまたがない。

## 生成と採点

train状態系列から、既存Proposedと同じ時間帯別STN JSONおよび `prompts/pattern_extraction_prompt.md` をGPT-5.6 Solへ渡す。LLM入力はtrain STNのみで、test状態系列やtest統計はプロンプトに渡さない。run 1--5 は同一fingerprint下に別JSON・checkpointとして保存される。

頻度法はAPI不要の診断用候補である。候補と採点の基本単位は **`(time_band, contiguous state sequence)`** である。同じ状態列が別時間帯に出ても統合しない。LLMが時間帯別の解釈を統合して返した場合も、採点時には時間帯ごとに展開する。

主指標 `test_supported_pattern_fraction`（FRR）は、生成した候補のうち対応時間帯のtestで1回以上完全一致した候補の割合である。補助指標はtest日単位再現率、test 1日当たり出現数、train/test出現率比、test遷移被覆率、および時間帯別・系列長別のpattern detailsである。LLMはrun別値と5 runの平均・標本標準偏差を保存し、欠損runを0として集計しない。

Ground Truth ADLは探索・参照・統合しない。将来に同じ状態系列が出たことは、ADL意味が正しいことの証明ではない。

## Dry-run

dry-runは実APIを呼ばず、成果物も作らない。split日数、train/test event数、trainセンサ数、代表状態数、STNノード/エッジ数、prompt token概算、5 run合計概算、API call数0、`test_prompted_to_llm=false` を表示する。

```bash
uv run python scripts/evaluate_10_switchbot.py \
  --snapshot data/switchbot/2026-08-19_2026-09-19 \
  --eval7-best-condition-manifest results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json \
  --dry-run
```

## 本番の段階実行

APIなしでまずtrain側の状態表とSTNを固定する。

```bash
uv run python scripts/evaluate_10_switchbot.py \
  --snapshot data/switchbot/2026-08-19_2026-09-19 \
  --eval7-best-condition-manifest results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json \
  --stage prepare
```

次だけがBedrock APIを呼ぶ。train STNに対する5 runである。

```bash
uv run python scripts/evaluate_10_switchbot.py \
  --snapshot data/switchbot/2026-08-19_2026-09-19 \
  --eval7-best-condition-manifest results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json \
  --stage extract --allow-api
```

最後にAPIなしでtest再現性を集計する。

```bash
uv run python scripts/evaluate_10_switchbot.py \
  --snapshot data/switchbot/2026-08-19_2026-09-19 \
  --eval7-best-condition-manifest results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json \
  --stage evaluate --method llm
```

## 出力

| パス | 内容 |
|---|---|
| `output/<model>/10_real_home_temporal_generalization/<期間>/preparation.json` | 入力・Eval7 manifest hash、時系列split、固定K/h、センサ表現、件数、STN規模。 |
| `output/.../state_table.tsv` | trainだけで決まる代表状態表。 |
| `output/.../network/` | trainだけで構築する時間帯別STN。 |
| `output/.../{train,test}_state_segments.json` | 同じtrain状態表で写像した日・時間帯別状態系列。 |
| `results/.../llm/<fingerprint>/..._1.json` -- `..._5.json` | run別のLLMパターンとcheckpoint。 |
| `results/.../evaluation10_pattern_details.csv` | run・時間帯・系列長ごとの出現と再現。 |
| `results/.../evaluation10_summary_by_run.csv` | runごとのFRR・補助指標。 |
| `results/.../evaluation10_summary.csv` | 5 run平均・標本標準偏差。 |
| `results/.../evaluation10_by_time_band.csv` | run・時間帯ごとの候補数、再出現数、FRR、平均test support。 |
| `results/.../evaluation10_by_pattern_length.csv` | run・系列長ごとの候補数、再出現数、FRR、平均test support。 |
| `results/.../evaluation10_manifest.json` | モデル、prompt hash/設定、K/h根拠、split、センサ写像、指標定義。 |
| `results/.../evaluation10_summary.json` | 再現条件と全出力パス。 |

実宅イベント、device識別子、派生成果物はGitへコミットしない。
