# 評価3: 提案手法とLLM単独ベースラインの比較

この評価では、提案手法と、センサログまたは代表状態系列を直接LLMに渡すベースラインを比較する。提案手法は状態遷移ネットワークを構造化してLLMに渡すのに対し、LLM単独ベースラインは遷移ネットワーク化を介さず、時系列ログに近い入力からパターンを抽出する。

## 目的

- 状態遷移ネットワークをLLM入力にする効果を確認する。
- 直接ログ入力だけで抽出した場合と、構造化ネットワーク入力で抽出した場合のPrecision, Recall, F1を比較する。
- LLM単独では長いログや局所的な揺らぎに引っ張られやすいかを確認する。

## 比較する手法

| 手法 | 入力 | 主なスクリプト | 出力 |
|---|---|---|---|
| 提案手法 | 時間帯別状態遷移ネットワークJSON | `scripts/run_llm_eval_batch.py` | `output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx` |
| LLM単独ベースライン | 代表状態系列を直接プロンプト化したログ | `scripts/run_direct_log_baseline.py` | `output/llm_direct_{DAYS}/evaluate_direct_log_metrics_{DAYS}days.xlsx` |

## 前提

評価2の提案手法5回実行が完了していること。

```bash
uv run python scripts/run_all.py
```

少なくとも以下が存在することを確認する。

```text
output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx
state/aruba_15_1_154days.txt
```

## LLM単独ベースラインの実行順序

### 1. 状態系列を準備

直接ログベースラインも代表状態テーブルを参照するため、未生成の場合は先に実行する。

```bash
uv run python scripts/run_build_network.py
```

### 2. 直接ログ入力でLLM抽出と評価

```bash
uv run python scripts/run_direct_log_baseline.py
```

入力:

```text
data/aruba.csv
state/aruba_15_1_154days.txt
prompts/direct_log_pattern_extraction_prompt.md
.env
```

出力:

```text
output/llm_direct_154/1.json
output/llm_direct_154/llm_direct_metrics_154days.csv
output/llm_direct_154/evaluate_direct_log_report.txt
output/llm_direct_154/evaluate_direct_log_metrics_154days.xlsx
```

`configs/default.yaml` の `llm.runs_default` が1の場合、直接ログベースラインは1回実行になる。提案手法と同じく5回で比較したい場合は、`llm.runs_default: 5` に変更してから実行する。

## 比較方法

次の2つのExcelを比較する。

```text
output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx
output/llm_direct_154/evaluate_direct_log_metrics_154days.xlsx
```

比較する指標:

- 遷移確率ベースラインに対するPrecision, Recall, F1
- 頻度ベースラインに対するPrecision, Recall, F1
- 実行ごとのばらつき
- 5回平均
- 出力パターン数
- 不正な系列、存在しない遷移、長すぎる系列の有無

## Groundednessを確認する場合

LLM出力が状態遷移グラフに根拠を持つかを確認する場合は、次を実行する。

```bash
uv run python scripts/run_groundedness.py
```

確認内容:

- 系列長が2から4に収まるか。
- 自己ループを含まないか。
- 隣接状態ペアがMarkov graph上に存在するか。
- 各エッジの遷移確率が0.2以上か。

`src/behavior_pattern_mining/evaluation/groundedness_check.py` は入力先の既定値が直接ログ出力向けになっている場合がある。提案手法の出力にも適用する場合は、スクリプト内または設定の入力パスを確認する。

## 結果のまとめ方

表の例:

```text
method, run, num_patterns,
prob_precision, prob_recall, prob_f1,
state_precision, state_recall, state_f1,
groundedness
```

論文・発表では、少なくとも次を記述する。

- 提案手法は状態遷移ネットワークJSONを入力にしたこと。
- LLM単独ベースラインはログに近い系列入力を使ったこと。
- 両手法で同じベースライン、同じ評価指標を使ったこと。
- 直接ログベースラインの実行回数が1回か5回か。

## 注意点

- 直接ログベースラインの出力先は `output/llm_direct_{DAYS}/` で、提案手法の出力先とは異なる。
- `llm.runs_default` を変更した場合、他のLLM実行にも影響する可能性があるため、実験後は設定値を記録する。
- 比較時は同じ `K`, ハミング距離、分析期間を使う。
