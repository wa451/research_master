# 評価2: 提案手法の5回実行評価

この評価では、提案手法である「センサログを代表状態系列に変換し、状態遷移ネットワークを構築してからLLMに入力する方法」を5回実行し、抽出結果と評価指標の安定性を確認する。

## 目的

- LLM出力のばらつきを5回実行で確認する。
- 遷移確率ベースライン、頻度ベースラインに対するPrecision, Recall, F1を集計する。
- 論文・発表で使う提案手法の主結果を再現する。

## 使用条件

| 項目 | 値 |
|---|---|
| データセット | `data/aruba.csv` |
| 代表状態数K | 15 |
| ハミング距離閾値 | 1 |
| 分析期間 | 154日 |
| LLMモデル | `gemini-2.5-pro` |
| Temperature | 0.2 |
| 実行回数 | 5 |
| 入力形式 | 時間帯別状態遷移ネットワークJSON |
| 系列長 | 2から4 |

詳細なパラメータは `docs/paper_parameters.md` を参照する。

## 入力

```text
data/aruba.csv
configs/default.yaml
prompts/pattern_extraction_prompt.md
.env
```

`.env` には次を設定する。

```text
GEMINI_API_KEY=...
```

## 実行順序

### 1. 状態遷移ネットワークを作成

```bash
uv run python scripts/run_build_network.py
```

出力:

```text
state/aruba_15_1_154days.txt
picture/aruba_15_1_154days/state_transition_all.json
picture/aruba_15_1_154days/state_transition_Morning.json
picture/aruba_15_1_154days/state_transition_Daytime.json
picture/aruba_15_1_154days/state_transition_Night.json
picture/aruba_15_1_154days/state_transition_Midnight.json
```

### 2. ベースラインを作成

```bash
uv run python scripts/run_baselines.py
```

出力:

```text
output/aruba_15_1_154days/prob_threshold_sequences_15_1_154days.json
output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json
```

### 3. 提案手法のLLM抽出と評価を5回実行

```bash
uv run python scripts/run_llm_eval_batch.py
```

`scripts/run_llm_eval_batch.py` は内部で次を行う。

1. `src/behavior_pattern_mining/llm/pattern_extractor.py` を5回呼び出す。
2. 各回のLLM出力をJSONとして保存する。
3. `src/behavior_pattern_mining/evaluation/compare_patterns.py` でベースラインと比較する。
4. 5回分の評価指標をExcelにまとめる。

### まとめて実行する場合

```bash
uv run python scripts/run_all.py
```

`scripts/run_all.py` は以下の順番で実行する。

```text
run_build_network
run_baselines
run_llm_eval_batch
```

## 出力

```text
output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json
output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_2.json
output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_3.json
output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_4.json
output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_5.json
output/aruba_15_1_154days/evaluation_report_15_1_154days_1.txt
output/aruba_15_1_154days/evaluation_report_15_1_154days_2.txt
output/aruba_15_1_154days/evaluation_report_15_1_154days_3.txt
output/aruba_15_1_154days/evaluation_report_15_1_154days_4.txt
output/aruba_15_1_154days/evaluation_report_15_1_154days_5.txt
output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx
```

## 評価方法

`src/behavior_pattern_mining/evaluation/compare_patterns.py` で、LLMが出力した状態系列を以下の2種類のベースラインと比較する。

| 比較対象 | 内容 |
|---|---|
| 遷移確率ベースライン | 遷移確率0.2以上のエッジをたどる系列 |
| 頻度ベースライン | 代表状態系列上で頻出する状態系列 |

指標:

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 * Precision * Recall / (Precision + Recall)
```

現在の評価では完全一致のみをTPとする。

## 確認する点

- 5回の出力パターン数に大きな差がないか。
- 5回平均のPrecision, Recall, F1。
- 遷移確率ベースラインと頻度ベースラインのどちらに近い傾向か。
- 低確率エッジや存在しないエッジを含む系列が混入していないか。

## 注意点

- LLM APIを使うためネットワーク接続とAPIキーが必要。
- 既に同じRun番号のJSONがある場合、スクリプト側でスキップされることがある。再実行結果を完全に作り直す場合は、既存出力を別名で退避してから実行する。
- 評価2の結果は評価3、評価4の入力にも使える。
