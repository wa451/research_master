# Smart Home Behavior Pattern Mining

スマートホームのセンサログから代表状態と状態遷移ネットワークを構築し、LLMによる生活行動系列の抽出、ベースライン比較、ADLラベルを用いた評価を行う研究コードです。

文書の分類は [docs/README.md](docs/README.md) を入口にしてください。処理の全体像は [docs/architecture/pipeline.md](docs/architecture/pipeline.md)、実装の責務は [docs/architecture/code_inventory.md](docs/architecture/code_inventory.md)、再現手順は [docs/operations/experiment_reproduction.md](docs/operations/experiment_reproduction.md) を参照してください。研究判断が未確定の挙動は [docs/research/known_issues.md](docs/research/known_issues.md) に分離しています。

## セットアップ

Python 3.9以上と `uv` を使用します。

```bash
uv sync
```

Gemini APIを使う処理では、リポジトリ直下の `.env` にキーを設定します。

```text
GEMINI_API_KEY=...
```

`.env`、APIキー、`data/` と `new_labeled_data/` の生データはGitへ追加しないでください。既存の `output/`、`picture/`、`results/`、`state/` も、再実行前に上書き範囲を確認してください。

## 入力データ

主要パイプラインは既定で `data/aruba.csv` を読みます。ADL評価は、ラベル付きCASASデータ `new_labeled_data/aruba.txt` とセンサー対応表 `configs/aruba_sensor_map.json` を使用します。データ形式と評価固有の前提は、対応する評価文書で確認してください。

## ディレクトリ

| パス | 役割 |
|---|---|
| `configs/` | 共通設定、センサー対応、ADL最小時間設定 |
| `docs/` | パイプライン、再現手順、評価仕様、既知の不一致 |
| `prompts/` | 実行時に読むLLMプロンプト |
| `scripts/` | 実験・評価の実行入口 |
| `src/behavior_pattern_mining/` | 前処理、抽出、LLM処理、評価の実装 |
| `tests/` | `unittest` ベースの回帰テスト |
| `state/` | 代表状態テーブル |
| `picture/` | 状態遷移JSON、遷移図、timeline図 |
| `output/` | LLM出力、ベースライン、中間生成物 |
| `results/` | 後段評価の集計結果 |

Pythonファイル単位の台帳は [docs/architecture/python_file_inventory.md](docs/architecture/python_file_inventory.md)、成果物の扱いは [docs/operations/artifact_policy.md](docs/operations/artifact_policy.md) にあります。

## 現在の共通既定値

次は `configs/default.yaml` の値です。

| 項目 | 既定値 |
|---|---:|
| データセット | `aruba` |
| 代表状態数 K | `15` |
| ハミング距離閾値 h | `1` |
| 分析期間 | `154`日 |
| サンプリング間隔 | `1s` |
| 遅延OFF窓幅 | `5`秒 |
| LLMモデル | `gemini-2.5-pro` |
| Temperature | `0.2` |

論文採用条件では `K=15, h=0` を使う評価があります。共通既定値と論文採用条件を混同せず、[docs/research/paper_parameters.md](docs/research/paper_parameters.md) と各評価文書の明示引数を確認してください。この差は [KI-01](docs/research/known_issues.md#ki-01) として判断保留です。

## 基本的な実行

ネットワーク構築と通常ベースラインはGemini APIを使いません。

```bash
uv run python scripts/run_build_network.py
uv run python scripts/run_baselines.py
```

提案手法のLLM抽出はAPIを呼び出します。保存済み出力を再利用できるか確認してから実行してください。

```bash
uv run python scripts/run_llm_extraction.py
```

現在の共通設定による主要処理をまとめて起動する入口は次です。LLM APIを含み、論文採用条件を自動選択する入口ではありません。

```bash
uv run python scripts/run_all.py
```

評価ごとの入力生成、明示引数、出力先はREADMEへ重複掲載せず、次の文書を正本とします。

## 評価文書

| 評価 | 内容 | 文書 |
|---:|---|---|
| 1 | K・ハミング距離の感度分析（旧評価と評価7への案内） | [evaluation_1_parameter_sensitivity.md](docs/evaluations/evaluation_1_parameter_sensitivity.md) |
| 2 | 提案手法の複数run評価 | [evaluation_2_proposed_method_5runs.md](docs/evaluations/evaluation_2_proposed_method_5runs.md) |
| 3 | direct-log LLM baselineとの比較 | [evaluation_3_direct_log_baseline_comparison.md](docs/evaluations/evaluation_3_direct_log_baseline_comparison.md) |
| 4 | ラベル付きCASASによる単一手法ADL評価 | [evaluation_4_labeled_casas_adl.md](docs/evaluations/evaluation_4_labeled_casas_adl.md) |
| 5 | パターン単位のADL-grounded/Useless評価 | [evaluation_5_adl_correspondence.md](docs/evaluations/evaluation_5_adl_correspondence.md) |
| 6 | LLM解釈ラベルとADL重なりラベルのset比較 | [evaluation_6_adl_interpretation_set.md](docs/evaluations/evaluation_6_adl_interpretation_set.md) |
| 7 | 全条件探索と上位条件の複数run感度評価 | [evaluation_7_parameter_sensitivity_adl_interpretation.md](docs/evaluations/evaluation_7_parameter_sensitivity_adl_interpretation.md) |
| 8 | 頻度帯別ADL整合性評価 | [evaluation_8_frequency_stratified_adl_consistency.md](docs/evaluations/evaluation_8_frequency_stratified_adl_consistency.md) |
| 9 | Hestia合成ログによる系列回収・ADL意味対応 | [evaluation_9_hestia.md](docs/evaluations/evaluation_9_hestia.md) |
| 10 | SwitchBot実宅ログの時間ホールドアウト評価 | [evaluation_10_switchbot_holdout.md](docs/evaluations/evaluation_10_switchbot_holdout.md) |

評価4〜10はStreamlitの薄いCLIラッパーからも実行できます。使い方は [docs/operations/dashboard.md](docs/operations/dashboard.md) を参照してください。

```bash
uv run streamlit run app/streamlit_app.py
```

## テスト

```bash
uv run python -m unittest discover -s tests
```

変更時は対象CLIの `argparse` 定義を先に確認し、対応している入口だけで `--help` を実行してください。LLM APIを使う評価は、保存済み応答、モック、dry-run、またはAPI呼び出し直前までの検証を優先します。

## 注意事項

- 文書と実装が異なる場合、実装は現在の挙動を示す証拠ですが、研究上の意図を自動的に確定しません。
- 評価指標、閾値、分母、split、seed、run欠損処理、LLM設定、CSV/JSON契約を別作業のついでに変更しないでください。
- 未解決事項を修正する場合は、[docs/research/known_issues.md](docs/research/known_issues.md) の影響範囲と過去結果の再評価要否を先に確認してください。

## 評価9: Hestia合成ログ

Hestiaは `master-research/Hestia/` に配置する。Webアプリの「評価9」または `uv run python scripts/evaluate_9_hestia.py` でログ生成から採点まで実行できる（既定はAPIなし）。配置・入力契約・指標・実行方法は [評価9のガイド](docs/evaluations/evaluation_9_hestia.md) を参照。

## 評価10: SwitchBot実宅ログ

`data/switchbot/<取得期間>/events.csv` と `manifest.json` を一組で指定し、train期間だけでパターンを生成して後半test期間の再出現を評価します。既定runはAPIなしのfrequency評価で、LLM抽出は `--allow-api` が必要です。詳細は [評価10のガイド](docs/evaluations/evaluation_10_switchbot_holdout.md) を参照してください。
