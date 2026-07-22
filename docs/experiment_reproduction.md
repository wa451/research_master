# Experiment Reproduction

この文書は、現在のコードで実験を再実行するときの共通前提と評価間の依存順序を示す。評価固有のCLI引数・入力・出力・指標は各評価文書、論文採用値は [paper_parameters.md](paper_parameters.md) を正本とする。

現在の `configs/default.yaml` は `K=15, h=1`、論文採用条件は `K=15, h=0` である。引数を受けない `scripts/run_all.py` は現在の共通既定値で動き、論文採用条件を自動的に再現する入口ではない。正規の再現方法を確定するまでは [KI-01](known_issues.md) として扱う。

## 1. 事前準備

1. 依存関係を同期する。

   ```bash
   uv sync
   ```

2. 入力を配置する。

   - 通常ログ: `data/aruba.csv`
   - ラベル付きCASAS: `new_labeled_data/aruba.txt`
   - センサー対応: `configs/aruba_sensor_map.json`

3. LLM処理を行う場合だけ、リポジトリ直下の `.env` に `GEMINI_API_KEY` を設定する。APIキーと生データはGitへ追加しない。

4. 再実行前に、同じ条件名の `state/`, `picture/`, `output/`, `results/` が存在しないか確認する。既存成果物を消したり上書きしたりせず、必要なら別の出力先を使う。

## 2. 共通の処理順序

```text
sensor log
  -> 1秒Sample-and-Hold / 5秒遅延OFF / 連続状態圧縮
  -> 代表状態K件の抽出と代表状態への写像
  -> 状態遷移ネットワーク
  -> 通常baseline / LLM抽出
  -> 評価1〜3
  -> ラベル付きCASASを使う評価4〜8
```

前処理・写像・遷移構築の詳細は [pipeline.md](pipeline.md) を参照する。direct-log写像、ADL照合用状態系列など、経路間で条件が一致しない可能性は [known_issues.md](known_issues.md) に記録している。

## 3. 現在の共通既定値による主要パイプライン

次は `configs/default.yaml` の `K=15, h=1, 154日` を使う。LLMを含むため、保存済み出力を利用できる場合は再実行しない。

1. 状態遷移ネットワークを構築する。

   ```bash
   uv run python scripts/run_build_network.py
   ```

2. 遷移確率・頻度baselineを生成する。

   ```bash
   uv run python scripts/run_baselines.py
   ```

3. 提案手法のLLM抽出を実行する。

   ```bash
   uv run python scripts/run_llm_extraction.py
   ```

一括入口は次のとおりだが、LLM APIを呼び、現在の共通既定値を使う。

```bash
uv run python scripts/run_all.py
```

## 4. 評価の依存関係

| 評価 | 主な前提成果物 | 実行文書 |
|---:|---|---|
| 1 | 条件別network、baseline、提案手法JSON | [evaluation_1_parameter_sensitivity.md](evaluation_1_parameter_sensitivity.md) |
| 2 | 共通network・baseline、複数runの提案手法JSON | [evaluation_2_proposed_method_5runs.md](evaluation_2_proposed_method_5runs.md) |
| 3 | 提案手法出力とdirect-log出力 | [evaluation_3_direct_log_baseline_comparison.md](evaluation_3_direct_log_baseline_comparison.md) |
| 4 | ラベル付きCASAS、代表状態表、提案手法JSON | [evaluation_4_labeled_casas_adl.md](evaluation_4_labeled_casas_adl.md) |
| 5 | 抽出時と対応する全期間state series、各手法のpattern | [evaluation_5_adl_correspondence.md](evaluation_5_adl_correspondence.md) |
| 6 | 14日条件の提案手法・direct-log JSON、比較用state series | [evaluation_6_adl_interpretation_set.md](evaluation_6_adl_interpretation_set.md) |
| 7 | 条件別提案手法JSON・state series、評価6と同じ正解データ | [evaluation_7_parameter_sensitivity_adl_interpretation.md](evaluation_7_parameter_sensitivity_adl_interpretation.md) |
| 8 | 評価6detailsまたは提案手法JSON、対応するstate series | [evaluation_8_frequency_stratified_adl_consistency.md](evaluation_8_frequency_stratified_adl_consistency.md) |

評価4〜8はStreamlitからも既存CLIを組み立てられる。先にdry-runでコマンドと条件別パスを確認する。詳細は [evaluation_streamlit_dashboard.md](evaluation_streamlit_dashboard.md) を参照する。

## 5. 共通研究条件

| 項目 | 論文採用値・処理 |
|---|---|
| 対象 | Aruba、先頭154日（評価6などは抽出入力14日） |
| 状態生成 | 1秒Sample-and-Hold |
| ノイズ処理 | 遅延OFF窓幅5秒 |
| 圧縮 | 連続する同一状態ベクトルを1状態へ圧縮 |
| 代表状態 | 頻度上位K、採用値K=15 |
| 採用h | 0。共通config既定は1なので区別する |
| 時間帯 | Morning 06:00–10:00、Daytime 10:00–18:00、Night 18:00–24:00、Midnight 00:00–06:00 |
| LLM | `gemini-2.5-pro`, temperature 0.2 |
| 通常系列長 | 2〜4 |

評価ごとの閾値、分母、split、missing-run処理は共通化せず、個別評価文書に従う。

## 6. LLM promptと出力

- 提案手法は `prompts/pattern_extraction_prompt.md`、direct-logは `prompts/direct_log_pattern_extraction_prompt.md` を実行時に読む。
- promptファイル欠落時には実装内fallbackが使われるが、許可ラベル集合に差があるため [KI-12](known_issues.md) として未解決である。
- 提案手法の各要素は少なくとも `パターン名`, `ADL系列ラベル`, `解釈の根拠`, `遷移のパターン` を扱う。
- prompt、モデル、temperature、API呼び出し条件を再現作業のついでに変更しない。

## 7. 成果物の対応

| 種類 | 現行パターン |
|---|---|
| 代表状態表 | `state/aruba_{K}_{h}_{days}days.txt` |
| network JSON | `picture/aruba_{K}_{h}_{days}days/state_transition_*.json` |
| 遷移図 | `picture/aruba_{K}_{h}_{days}days/state_transition_*.png`, `.eps` |
| timeline | `picture/aruba_{K}_{h}_{days}days/timeline_*.png` |
| 通常baseline | `output/aruba_{K}_{h}_{days}days/{prob_threshold_sequences,state_sequence_counts}_*.json` |
| 提案手法 | `output/aruba_{K}_{h}_{days}days/llm_sequences_modes_*_{run}.json` |
| direct-log | 明示条件時は `output/llm_direct_{K}_{h}_{days}days/{run}.json`、無引数の共通既定日数では互換形式 `output/llm_direct_{days}/{run}.json` |
| 後段評価 | `results/{evaluation-specific directory}/` |

成果物の保存方針は [artifact_policy.md](artifact_policy.md) を参照する。ファイル名やCSV/JSON schemaを文書整理のために変更しない。

## 8. 検証

1. LLMを呼ばない回帰テストを実行する。

   ```bash
   uv run python -m unittest discover -s tests
   ```

2. 対象CLIが `argparse` を使うことを確認してから `--help` と文書の引数を照合する。
3. 再生成した場合は、条件suffix、CSV列名・行数・主要集計値、JSONキー・型、run番号を既存成果物と比較する。
4. LLM処理は保存済み応答、checkpoint、モック、dry-runを優先し、APIを検証目的だけで大量実行しない。

## 9. 再現性上の未解決事項

run独立性、direct-logの写像、公平なK/h伝播、ADL状態系列の前処理、評価6のrun母集団、評価8の30日互換scopeなどは、意図した仕様が未確定である。詳細と判断事項は [known_issues.md](known_issues.md) を参照し、現在の挙動を正当化する説明へ置き換えない。
