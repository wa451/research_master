# 評価1: 代表状態数K・ハミング距離の感度分析

## 評価の要約

代表状態数 `K` とハミング距離閾値を変更し、代表状態への割り当て、状態遷移ネットワーク、ベースライン系列、LLM抽出結果、評価指標がどう変化するかを確認する。この文書は互換用設定と旧指標に基づく評価1を記録する。現在の論文で用いる28条件・上位10条件合計5試行の感度評価と採用値 `K=15`, `hamming_threshold=0` は、`docs/evaluations/evaluation_7_parameter_sensitivity_adl_interpretation.md` を正式手順とする。

## RQ

| RQ | 内容 |
|---|---|
| RQ1-1 | `K` を変えると、代表状態と状態遷移ネットワークの解釈しやすさはどう変わるか。 |
| RQ1-2 | ハミング距離閾値を変えると、`その他` 状態や状態の混ざり方はどう変わるか。 |
| RQ1-3 | 互換用設定 `K=15`, `hamming_threshold=1` は、旧系列抽出・評価指標の観点で極端な条件になっていないか。 |

## 評価指標

| 指標 | 確認すること |
|---|---|
| 代表状態数・`その他` 割合 | 状態が粗すぎる、または細かすぎる条件を確認する。 |
| ネットワークのノード数・エッジ数 | 状態遷移ネットワークが疎すぎる、または複雑すぎる条件を確認する。 |
| 遷移確率ベースライン系列数 | 閾値以上の遷移系列がどの程度得られるかを見る。 |
| 頻度ベースライン上位系列 | 上位系列が生活行動として解釈できるかを見る。 |
| LLM出力数・系列内容 | `遷移のパターン` が安定し、解釈可能かを見る。 |
| Precision / Recall / F1 | LLM出力とベースライン系列の一致度を見る。 |
| 可視化の解釈しやすさ | 図として説明可能な状態数・遷移数かを見る。 |

## 入力と出力

### 入力

| 入力 | 例 | 役割 |
|---|---|---|
| センサログ | `data/aruba.csv` | 前処理・代表状態抽出の入力。 |
| 設定 | `configs/default.yaml` | `K`, ハミング距離、分析期間などを指定する。 |
| 互換設定レイヤー | `experiment_config.py` | YAML設定を既存モジュール向け定数として公開する。 |
| LLMプロンプト | `prompts/pattern_extraction_prompt.md` | LLM抽出まで比較する場合に使う。 |

### 出力

| 出力 | 内容 |
|---|---|
| `state/aruba_{K}_{hamming}_{DAYS}days.txt` | 代表状態テーブル。 |
| `picture/aruba_{K}_{hamming}_{DAYS}days/state_transition_all.json` | 全期間の状態遷移ネットワーク。 |
| `picture/aruba_{K}_{hamming}_{DAYS}days/state_transition_{mode}.json` | 時間帯別ネットワーク。 |
| `picture/aruba_{K}_{hamming}_{DAYS}days/*.png` | 状態遷移図・タイムライン。 |
| `output/aruba_{K}_{hamming}_{DAYS}days/prob_threshold_sequences_{K}_{hamming}_{DAYS}days.json` | 遷移確率ベースライン系列。 |
| `output/aruba_{K}_{hamming}_{DAYS}days/state_sequence_counts_{K}_{hamming}_{DAYS}days.json` | 頻度ベースライン系列。 |
| `output/aruba_{K}_{hamming}_{DAYS}days/llm_sequences_modes_{K}_{hamming}_{DAYS}days_*.json` | LLM抽出系列。 |
| `output/aruba_{K}_{hamming}_{DAYS}days/llm_modes_metrics_{K}_{hamming}_{DAYS}days_run{run}.csv` | run・時間帯ごとのbackend、処理時間、token使用量。 |
| `output/aruba_{K}_{hamming}_{DAYS}days/llm_modes_metrics_avg_{K}_{hamming}_{DAYS}days.csv` | 時間帯ごとの処理時間・token使用量の平均。 |
| `output/aruba_{K}_{hamming}_{DAYS}days/evaluation_report_{K}_{hamming}_{DAYS}days_*.txt` | LLM出力とベースラインの比較レポート。 |
| `output/aruba_{K}_{hamming}_{DAYS}days/llm_eval_runs_{K}_{hamming}_{DAYS}days.xlsx` | 複数run評価の集計。 |

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `output/aruba_{K}_{hamming}_{DAYS}days/llm_eval_runs_{K}_{hamming}_{DAYS}days.xlsx` | LLMまで実行した場合のsummaryとして、run別と平均のPrecision / Recall / F1を見る。標準偏差と出力パターン数は現在のExcelには含まれない（[KI-03](../research/known_issues.md)）。 |
| 2 | `state/aruba_{K}_{hamming}_{DAYS}days.txt`, `picture/.../state_transition_*.json`, `output/.../state_sequence_counts_*.json` | detailsとして、状態の意味、遷移の複雑さ、頻出系列の内容を見る。 |
| 3 | `configs/default.yaml`, `docs/research/paper_parameters.md` | 再現条件として、`K`, ハミング距離、日数、閾値を確認する。 |

## 実行手順

### 1. 🟥 **必須** 比較条件を設定する

条件ごとに `configs/default.yaml` の `state_extraction.representative_states_k` と `state_extraction.hamming_threshold` を変更する。

このStepは設定ファイル編集であり、専用の実行コマンドはない。

### 2. 🟥 **必須** 状態遷移ネットワークを作成する

各 `K`, `hamming_threshold`, `DAYS` 条件で必ず実行する。同じ条件の `picture/aruba_{K}_{hamming}_{DAYS}days/state_transition_{mode}.json` と `state/aruba_{K}_{hamming}_{DAYS}days.txt` が既にある場合は、再利用してよい。

```bash
uv run python scripts/run_build_network.py
```

### 3. 🟨 **条件付き** ベースラインを作成する

`output/aruba_{K}_{hamming}_{DAYS}days/prob_threshold_sequences_*.json` や `state_sequence_counts_*.json` がなければ実行する。

```bash
uv run python scripts/run_baselines.py
```

### 4. 🟨 **条件付き** LLM抽出と評価を実行する

LLM出力やF1まで比較する場合だけ実行する。既に同条件のLLM出力、評価レポート、評価Excelがある場合は再実行しなくてよい。`llm_modes_metrics_*.csv` は評価指標ではなく、LLMの処理時間・token使用量を記録する。

```bash
uv run python scripts/run_llm_eval_batch.py
```

### 5. 🟩 **スキップ可** 全工程をまとめて実行する

個別Stepではなく、ネットワーク構築から評価までまとめて再実行したい場合だけ使う。

```bash
uv run python scripts/run_all.py
```

## 比較対象

| 観点 | 条件 |
|---|---|
| `K` の比較 | `K=3`, `10`, `15`, `20`, `30` |
| ハミング距離の比較 | `hamming_threshold=0`, `1`, `2`, `3` |
| 固定する値 | `K` 比較ではハミング距離を `1` に固定。ハミング距離比較では `K=15` に固定。 |
| 互換用config既定 | `K=15`, `hamming_threshold=1`, `DAYS=154` |
| 現論文の採用条件 | `K=15`, `hamming_threshold=0`（評価7で選定） |

## 処理手順の内部仕様

1. `configs/default.yaml` を `experiment_config.py` が読み込む。
2. `scripts/run_build_network.py` が前処理、代表状態抽出、状態マッピング、遷移ネットワーク構築、可視化を行う。
3. `scripts/run_baselines.py` が遷移確率ベースラインと頻度ベースラインを生成する。
4. `scripts/run_llm_eval_batch.py` がLLM抽出を複数回実行し、`compare_patterns.py` でベースラインと比較する。
5. 出力先は `{K}_{hamming}_{DAYS}days` を含むディレクトリ名で分かれる。

## パラメータ

| パラメータ | 標準値 | 定義場所 |
|---|---:|---|
| データセット | `data/aruba.csv` | `configs/default.yaml` |
| 分析期間 | `154`日 | `configs/default.yaml` |
| 代表状態数 `K` | `15` | `configs/default.yaml` |
| ハミング距離閾値 | `1`（互換用config既定） | `configs/default.yaml` |
| サンプリング間隔 | `1`秒 | `configs/default.yaml` |
| 遅延OFF窓幅 | `5`秒 | `configs/default.yaml` |
| 時間帯分割 | Morning / Daytime / Night / Midnight | `configs/default.yaml` |
| 可視化用遷移確率閾値 | `0.1` | `configs/default.yaml` |
| ベースライン遷移確率閾値 | `0.2` | `configs/default.yaml` |
| 系列長 | `2` から `4` | `configs/default.yaml` |

## 注意点

- 同じ `K`, `hamming_threshold`, `DAYS` 条件を再実行すると、同じ出力先の成果物を再利用または上書きする可能性がある。既存結果を残したい場合は出力を退避してから実行する。異なる条件は通常、条件suffixを含む別ディレクトリへ保存される。
- LLM出力は非決定性を含むため、構造的な違いを見る場合はまず `state/`, `picture/`, `output/*baseline*` を比較する。
- LLMまで含めて比較する場合は、評価2と同じく複数runの平均で比較する。
- `experiment_config.py` は互換レイヤーとして使われているため、削除しない。
- 無引数実行の `h=1` と現論文採用条件 `h=0` の関係は未解決である（[KI-01](../research/known_issues.md)）。
- 複数runのcheckpoint独立性と集計項目は未解決である（[KI-02](../research/known_issues.md), [KI-03](../research/known_issues.md)）。
- `configs/default.yaml` の一部のパス設定を参照せず固定パスを使う入口がある（[KI-14](../research/known_issues.md)）。
