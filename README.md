# Smart Home Behavior Pattern Mining

スマートホームのセンサログから代表状態を抽出し、状態遷移ネットワーク、LLMによる生活行動パターン抽出、ベースライン比較、評価、可視化を行う研究コードです。

## 処理パイプライン

1. `data/aruba.csv` を読み込む。
2. 1秒サンプリング、遅延OFFスムージング、連続同一状態の圧縮を行う。
3. 出現頻度上位K個の代表状態を抽出し、ハミング距離で状態をマッピングする。
4. 状態遷移確率を計算し、全期間/時間帯別ネットワークを `picture/` に出力する。
5. 遷移確率ベースライン、頻度ベースライン、LLM抽出を実行する。
6. Precision/Recall/F1、Groundedness、条件ベース評価を計算する。

詳細は `docs/pipeline.md` と `docs/code_inventory.md` を参照してください。生成物の管理方針は `docs/artifact_policy.md` にまとめています。
Pythonファイルごとの役割は `docs/python_file_inventory.md` にまとめています。

## フォルダ構成

```text
configs/    主要設定値の集約候補
data/       入力データ（Git管理外）
docs/       コード台帳、再現手順、リファクタリング計画
output/     現行の評価・LLM・ベースライン出力
outputs/    将来の統合出力先
picture/    現行の図・状態遷移JSON出力
prompts/    LLMプロンプトの外部化コピー
scripts/    実験・評価のCLI入口
src/        実装本体のPythonパッケージ
state/      代表状態テーブル
support/    補助スクリプト
tests/      最低限の回帰テスト
```

実装本体は `src/behavior_pattern_mining/` に移動済みです。実験の実行入口は `scripts/` 配下に集約しています。

## 環境構築

```bash
uv sync
```

Gemini APIを使う場合は、リポジトリ直下に `.env` を置きます。

```text
GEMINI_API_KEY=...
```

`.env` と `data/` は `.gitignore` で除外されています。

## データ配置

既定では以下を使います。

```text
data/aruba.csv
```

主な設定は `configs/default.yaml` にあります。`experiment_config.py` は、既存コードとの互換性を保つためにYAMLを読み込んで定数として公開する薄いレイヤーです。

```python
DATASET_NAME = "aruba"
N_STATES = 15
HAMMING_THRESHOLD = 1
DAYS = 154
```

現時点では `src/behavior_pattern_mining/` 配下の複数モジュールも `experiment_config.py` を参照しているため、削除しないでください。

## 実験の実行

個別実行:

```bash
uv run python scripts/run_build_network.py
uv run python scripts/run_baselines.py
uv run python scripts/run_llm_eval_batch.py
uv run python scripts/run_groundedness.py
uv run python scripts/evaluate_condition_metrics.py
```

まとめて実行:

```bash
uv run python scripts/run_all.py
```

LLMを使わない範囲のネットワーク構築とベースラインは、Gemini APIキーなしでも実行できます。

ADLラベル付きCASASデータで後段評価を行う場合:

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

## 主要スクリプト

- `scripts/run_build_network.py`: 前処理、代表状態抽出、遷移ネットワーク構築、可視化、JSON出力。
- `scripts/run_baselines.py`: 遷移確率ベースラインと頻度ベースラインを生成。
- `scripts/run_llm_extraction.py`: モード別遷移JSONからLLMで行動パターンを抽出。
- `scripts/run_llm_eval_batch.py`: LLM抽出と評価を5回実行しExcelに集計。
- `scripts/run_evaluation.py`: LLM出力とベースラインをPrecision/Recall/F1で比較。
- `scripts/run_groundedness.py`: LLM系列がグラフ上で根拠を持つか検証。
- `scripts/evaluate_condition_metrics.py`: support/confidence/時間間隔条件でLLM系列を評価。
- `scripts/evaluate_adl_labels.py`: ラベル付きCASASデータのADL区間とLLM系列パターンを照合し、ADLカテゴリ別Precision/Recall/F1と境界誤差を評価。

新しい実行では `scripts/` 側を使ってください。

## 主要設定値

- 代表状態数 K: `15`
- ハミング距離閾値: `1`
- 分析期間: `154`日
- サンプリング間隔: `1s`
- 遅延OFF窓幅: `180`秒
- 可視化の最小遷移確率: `0.1`
- ベースライン遷移確率閾値: `0.2`
- パターン長: `2-4`
- LLMモデル: `gemini-2.5-pro`
- Temperature: `0.2`
- 時間帯: Morning `06:00-10:00`, Daytime `10:00-18:00`, Night `18:00-24:00`, Midnight `00:00-06:00`

## 出力ファイル

- `state/aruba_15_1_154days.txt`: 代表状態テーブル。
- `picture/aruba_15_1_154days/state_transition_all.json`: 全期間の状態遷移ネットワーク。
- `picture/aruba_15_1_154days/state_transition_{mode}.json`: 時間帯別ネットワーク。
- `picture/aruba_15_1_154days/*.png`, `*.eps`: 遷移図とタイムライン。
- `output/aruba_15_1_154days/prob_threshold_sequences_15_1_154days.json`: 遷移確率ベースライン。
- `output/aruba_15_1_154days/state_sequence_counts_15_1_154days.json`: 頻度ベースライン。
- `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_*.json`: LLM抽出結果。
- `output/aruba_15_1_154days/evaluation_report_15_1_154days_*.txt`: 評価レポート。
- `results/adl_evaluation/*.csv`, `evaluation_summary.json`: ADLラベル付き評価の出力。

## 再現実験

論文・発表用の再現手順は `docs/experiment_reproduction.md` にまとめています。論文記載用パラメータは `docs/paper_parameters.md` も参照してください。

評価ごとの詳細:

- `docs/evaluation_1_parameter_sensitivity.md`: 代表状態数K・ハミング距離の感度分析。
- `docs/evaluation_2_proposed_method_5runs.md`: 提案手法の5回実行評価。
- `docs/evaluation_3_direct_log_baseline_comparison.md`: 提案手法とLLM単独ベースラインの比較。
- `docs/evaluation_4_labeled_casas_adl.md`: ラベル付きCASASデータによるADL評価。

## テスト

最低限のロジック確認は標準ライブラリの `unittest` で実行できます。

```bash
uv run python -m unittest discover -s tests
```

## 注意点

- 既存の `output/`, `picture/`, `state/` には生成済み結果が含まれ、一部はGit追跡されています。再実行すると差分が大きく出る可能性があります。
- `scripts/run_llm_eval_batch.py` は評価対象と同じ `llm_sequences_modes_{K}_{hamming}_{days}days_{run}.json` を生成するように揃えています。
