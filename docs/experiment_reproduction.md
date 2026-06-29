# Experiment Reproduction

この手順は、現在のコードで論文・発表に使った結果を再現するための入口です。評価ごとの詳しい手順、実行順序、出力ファイルは以下の個別ドキュメントに分けています。設定値の詳細は `docs/paper_parameters.md` も参照してください。

## 評価ドキュメント

| 評価 | 内容 | 詳細 |
|---|---|---|
| 評価1 | 代表状態数K・ハミング距離の感度分析 | `docs/evaluation_1_parameter_sensitivity.md` |
| 評価2 | 提案手法の5回実行評価 | `docs/evaluation_2_proposed_method_5runs.md` |
| 評価3 | 提案手法とLLM単独ベースラインの比較 | `docs/evaluation_3_direct_log_baseline_comparison.md` |
| 評価4 | ラベル付きCASASデータによるADL評価 | `docs/evaluation_4_labeled_casas_adl.md` |

## 最短の実行順序

提案手法の主結果を再現する場合:

```bash
uv sync
uv run python scripts/run_all.py
```

ラベル付きCASASによるADL評価まで実行する場合:

```bash
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --event-log data/aruba.csv \
  --state-table state/aruba_15_1_154days.txt \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/adl_evaluation \
  --iou-thresholds 0.3 0.5 \
  --wake-window-minutes 30 \
  --match-mode exact
```

以下は全体の共通設定と補足です。

## 使用データセット

- 既定データセット: `aruba`
- 配置: `data/aruba.csv`
- 形式: ヘッダなし4列イベントログ `date,time,sensor,value`
- Git管理: `data/` は `.gitignore` で除外済み

## 前処理条件

- 期間: 最初の154日
- サンプリング: 1秒
- 状態生成: Sample-and-Hold
- スムージング: 遅延OFF窓幅180秒
- 圧縮: 連続する同一状態ベクトルを1つに圧縮
- ON値: `ON`, `OPEN`, `PRESENT`, `1`, `1`
- OFF値: `OFF`, `CLOSE`, `ABSENT`, `0`, `0`

## 代表状態とマッピング

- 代表状態数 K: 15
- 抽出方法: 圧縮済み状態ベクトルの出現頻度上位K件
- ハミング距離閾値: 1
- マッピング条件: 代表状態に完全一致する場合はその状態。完全一致しない場合、最近傍代表状態とのハミング距離が1以下ならその代表状態、超える場合は「その他」。
- 出力: `state/aruba_15_1_154days.txt`

## 時間帯分割

| mode | range |
|---|---|
| Morning | 06:00-10:00 |
| Daytime | 10:00-18:00 |
| Night | 18:00-24:00 |
| Midnight | 00:00-06:00 |

## 遷移ネットワーク

- 自己連続遷移: 圧縮して除外
- 遷移確率: 各from状態の遷移回数で正規化
- 可視化閾値: 0.1
- LLM/ベースライン用JSON: `picture/aruba_15_1_154days/state_transition_*.json`

## LLMに入力するJSON形式

```json
{
  "nodes": [
    {
      "state_id": "状態1",
      "active_sensors": ["Kitchen"],
      "avg_duration_minutes_per_day": 12.345
    }
  ],
  "edges": [
    {
      "from": "状態1",
      "to": "状態2",
      "probability": 0.234
    }
  ]
}
```

## LLMプロンプト

- モード別ネットワーク入力: `src/behavior_pattern_mining/llm/pattern_extractor.py` の `PROMPT_TEMPLATE`
- 外部化コピー: `prompts/pattern_extraction_prompt.md`
- 直接ログ入力: `src/behavior_pattern_mining/llm/direct_log_extractor.py` の `PROMPT_TEMPLATE`
- 外部化コピー: `prompts/direct_log_pattern_extraction_prompt.md`
- モデル: `gemini-2.5-pro`
- Temperature: `0.2`
- APIキー: `.env` の `GEMINI_API_KEY`
- 出力制約: JSON配列、各要素は `パターン名`, `解釈の根拠`, `遷移のシーケンス` を持つ。系列長は2-4。

## ベースライン手法

### 遷移確率ベースライン

- 実装: `src/behavior_pattern_mining/baselines/transition_probability.py`
- 入力: モード別 `state_transition_{mode}.json`
- 閾値: 遷移確率0.2以上
- 系列長: 2-4
- 除外状態: `その他`
- 同一状態の再訪: 不許可
- 出力: `output/aruba_15_1_154days/prob_threshold_sequences_15_1_154days.json`

### 頻度ベースライン

- 実装: `src/behavior_pattern_mining/baselines/frequency.py`
- 入力: `data/aruba.csv`, `state/aruba_15_1_154days.txt`
- 系列長: 2-4
- ハミング距離による代表状態寄せ: 有効
- 出力上限: TOP 50
- 出力: `output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json`

## 評価指標

- 実装: `src/behavior_pattern_mining/evaluation/compare_patterns.py`
- 指標: Precision, Recall, F1
- TP: LLM系列がベースライン系列と一致
- FP: LLM系列にあるがベースラインにない
- FN: ベースラインにあるがLLM系列にない
- 部分一致: 現在は不許可
- 比較対象:
  - LLM vs 遷移確率ベースライン
  - LLM vs 頻度ベースライン

## Groundednessの計算方法

- 実装: `src/behavior_pattern_mining/evaluation/groundedness_check.py`
- 入力グラフ: `picture/aruba_15_1_154days/state_transition_all.json`
- LLM出力: 既定では `output/llm_direct_{DAYS}/*.json`
- 条件:
  - 系列長が2-4
  - 自己ループ `A -> A` がない
  - すべての隣接ペアがMarkov graphに存在する
  - 各エッジ確率が0.2以上
- Groundedness: 条件を満たしたパターン数 / 全パターン数

## 図表の生成方法

- 状態遷移図: `scripts/run_build_network.py`
- タイムライン図: `scripts/run_build_network.py`
- LLM評価Excel: `scripts/run_llm_eval_batch.py`
- direct log評価Excel: `scripts/run_direct_log_baseline.py`
- condition評価JSON/TXT: `scripts/evaluate_condition_metrics.py`

## 実行コマンド例

```bash
uv sync

# 1. 状態遷移ネットワークと代表状態テーブル
uv run python scripts/run_build_network.py

# 2. ベースライン
uv run python scripts/run_baselines.py

# 3. LLM抽出と評価を5回実行
uv run python scripts/run_llm_eval_batch.py

# 4. Groundedness
uv run python scripts/run_groundedness.py

# 5. 条件ベース評価
uv run python scripts/evaluate_condition_metrics.py

# 6. ラベル付きCASAS ADL評価
uv run python scripts/evaluate_adl_labels.py \
  --labeled-casas new_labeled_data/aruba.txt \
  --event-log data/aruba.csv \
  --state-table state/aruba_15_1_154days.txt \
  --patterns output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_1.json \
  --output-dir results/adl_evaluation
```

まとめて実行する場合:

```bash
uv run python scripts/run_all.py
```

## 注意点

- LLM実行にはネットワーク接続と `GEMINI_API_KEY` が必要。
- `scripts/run_llm_eval_batch.py` はLLM抽出モジュールに明示的な出力先を渡し、評価対象と同じ `llm_sequences_modes_{K}_{hamming}_{days}days_{run}.json` を生成する。
- 既存の `output/` と `picture/` はGit追跡されている生成物を含む。再生成すると大きな差分が出る。
