# 評価1: 代表状態数K・ハミング距離の感度分析

この評価では、代表状態数 `K` とハミング距離閾値を変更したときに、代表状態への割り当て、状態遷移ネットワーク、抽出される系列パターン、評価指標がどのように変化するかを確認する。

## 目的

- 代表状態数が少なすぎる、または多すぎる場合の影響を見る。
- ハミング距離閾値を緩めた場合に「その他」が減る一方で、異なる生活状態が同一代表状態に寄りすぎないかを確認する。
- 論文で採用する `K=15`, `hamming_threshold=1` の妥当性を説明できる材料を作る。

## 基準条件

現在の標準条件は `configs/default.yaml` から読み込まれる。実装上は、互換用の `experiment_config.py` がこのYAMLを読み、`src/behavior_pattern_mining/` 配下の実装へ定数として渡している。

| 項目 | 値 |
|---|---|
| データセット | `data/aruba.csv` |
| 分析期間 | 154日 |
| 代表状態数K | 15 |
| ハミング距離閾値 | 1 |
| サンプリング間隔 | 1秒 |
| 遅延OFF窓幅 | 180秒 |
| 時間帯分割 | Morning, Daytime, Night, Midnight |
| 可視化用遷移確率閾値 | 0.1 |
| ベースライン遷移確率閾値 | 0.2 |
| 系列長 | 2から4 |

## 比較条件の例

既存の生成物に合わせる場合、次の条件を比較対象にするとよい。

| 観点 | 条件 |
|---|---|
| Kの比較 | `K=3`, `10`, `15`, `20`, `30` |
| ハミング距離の比較 | `hamming_threshold=0`, `1`, `2`, `3` |
| 固定する値 | K比較ではハミング距離を1に固定。ハミング距離比較ではKを15に固定。 |

既存の出力例:

```text
state/aruba_15_1_154days.txt
picture/aruba_15_1_154days/
output/aruba_15_1_154days/
```

## 実行前の設定変更

`configs/default.yaml` の以下を変更する。

```yaml
state_extraction:
  representative_states_k: 15
  hamming_threshold: 1
```

変更後、各スクリプトは `experiment_config.py` 経由でこの設定を読む。現在は削除せず、互換レイヤーとして残す。

## 実行順序

### 1. 代表状態と状態遷移ネットワークを作成

```bash
uv run python scripts/run_build_network.py
```

主な出力:

```text
state/aruba_{K}_{hamming}_{DAYS}days.txt
picture/aruba_{K}_{hamming}_{DAYS}days/state_transition_all.json
picture/aruba_{K}_{hamming}_{DAYS}days/state_transition_Morning.json
picture/aruba_{K}_{hamming}_{DAYS}days/state_transition_Daytime.json
picture/aruba_{K}_{hamming}_{DAYS}days/state_transition_Night.json
picture/aruba_{K}_{hamming}_{DAYS}days/state_transition_Midnight.json
picture/aruba_{K}_{hamming}_{DAYS}days/*.png
```

### 2. ベースラインを作成

```bash
uv run python scripts/run_baselines.py
```

主な出力:

```text
output/aruba_{K}_{hamming}_{DAYS}days/prob_threshold_sequences_{K}_{hamming}_{DAYS}days.json
output/aruba_{K}_{hamming}_{DAYS}days/state_sequence_counts_{K}_{hamming}_{DAYS}days.json
```

### 3. 必要に応じてLLM抽出と評価を実行

Kやハミング距離の違いがLLM抽出結果に与える影響まで見る場合に実行する。

```bash
uv run python scripts/run_llm_eval_batch.py
```

主な出力:

```text
output/aruba_{K}_{hamming}_{DAYS}days/llm_sequences_modes_{K}_{hamming}_{DAYS}days_1.json
output/aruba_{K}_{hamming}_{DAYS}days/evaluation_report_{K}_{hamming}_{DAYS}days_1.txt
output/aruba_{K}_{hamming}_{DAYS}days/llm_eval_runs_{K}_{hamming}_{DAYS}days.xlsx
```

## 確認する指標

- 代表状態に割り当てられた状態数
- 「その他」に分類された割合
- 状態遷移ネットワークのノード数、エッジ数
- 遷移確率0.2以上の系列数
- 頻度ベースラインの上位系列
- LLM出力数
- ベースラインに対するPrecision, Recall, F1
- 可視化された状態遷移図の解釈しやすさ

## 結果のまとめ方

各条件について次を表にまとめる。

```text
K, hamming_threshold, num_states, num_other, num_edges,
num_prob_baseline_patterns, num_frequency_patterns,
prob_precision, prob_recall, prob_f1,
state_precision, state_recall, state_f1
```

既存の比較表がある場合は、`output/ハミング距離比較.xlsx` も確認する。

## 注意点

- 条件を変えるたびに同名の出力先へ再生成されるため、既存結果を残したい場合は事前に退避する。
- LLM実行は非決定性を含むため、Kやハミング距離の構造的な違いを見る場合は、まずネットワークとベースライン出力を比較する。
- LLMまで含めて比較する場合は、評価2と同じく5回実行の平均で比較する。
