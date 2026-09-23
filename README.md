# Smart Home Behavior Pattern Mining

スマートホームのセンサログから代表状態と状態遷移ネットワークを構築し、LLMによる生活行動系列の抽出、ベースライン比較、ADLラベルを用いた評価を行う研究コードです。

初めて内容を読む方は、用語と研究の流れを説明した[研究の概要](docs/overview.md)から始めてください。人向け文書とAI向け内部索引の区分は[文書案内](docs/README.md)にあります。処理の全体像は [docs/architecture/pipeline.md](docs/architecture/pipeline.md)、実装の責務は [docs/architecture/code_inventory.md](docs/architecture/code_inventory.md)、再現手順は [docs/operations/experiment_reproduction.md](docs/operations/experiment_reproduction.md) を参照してください。研究判断が未確定の挙動は [docs/research/known_issues.md](docs/research/known_issues.md) に分離しています。

## セットアップ

Python 3.9以上と `uv` を使用します。

```bash
uv sync
```

LLM providerはリポジトリ直下の `.env` の `LLM_PROVIDER` で切り替えます。既定のGeminiを使う場合は、従来どおりAPIキーを設定します。

```text
LLM_PROVIDER=google_gemini
GEMINI_API_KEY=...
```

Amazon Bedrockを使う場合は、`boto3`（`uv sync` でも導入されます）とAWS CLIを準備し、AWS SDKの標準credential chainを設定します。

```bash
pip install boto3 awscli
aws configure
```

`.env` には秘密鍵ではなくprovider、リージョン、Bedrock model IDを設定します。`BEDROCK_MAX_TOKENS` は省略可能で、既定値は `8192` です。

```text
LLM_PROVIDER=bedrock
AWS_REGION=us-east-2
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
# BEDROCK_MAX_TOKENS=8192
# BEDROCK_ESTIMATED_OUTPUT_TOKENS=1000
```

Bedrock実行でもコマンドは共通です。LLM成果物、checkpoint、usage metrics、評価5〜10の結果は、`.env` のprovider/modelから自動的に `results/<model>/` へ保存されます。

```bash
uv run python scripts/run_llm_extraction.py
uv run python scripts/run_direct_log_baseline.py --extract-only
```

モデル別ディレクトリ名は一箇所の対応表で管理され、現在は次の構造です。

```text
output/                              # モデル非依存の入力・前処理・準備済みデータ
results/
├── gemini-2.5-pro/
├── claude-haiku-4.5/
├── claude-sonnet-4.6/
├── gpt-5.6-luna/
├── gpt-5.6-terra/
└── gpt-5.6-sol/
```

各モデル配下には、`aruba_<K>_<h>_<days>days/`（提案手法の統合JSON・mode checkpoint・usage）、`llm_direct_.../`、`5_pattern_quality_fixed/`、`6_adl_match/`、`7_param_search/`、`8_.../`、`9_hestia/`、`10_switchbot/` が従来の下位構造を保って作成されます。同じモデルではcheckpointを再利用し、別モデルは別ディレクトリになるため再利用しません。明示的な `--output-dir` を使う場合も `model_metadata.json` と実行モデルが一致しなければ停止します。

| provider model ID | result directory |
|---|---|
| `gemini-2.5-pro` | `gemini-2.5-pro` |
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | `claude-haiku-4.5` |
| `us.anthropic.claude-sonnet-4-6` | `claude-sonnet-4.6` |
| `us.openai.gpt-5.6-luna` | `gpt-5.6-luna` |
| `us.openai.gpt-5.6-terra` | `gpt-5.6-terra` |
| `us.openai.gpt-5.6-sol` | `gpt-5.6-sol` |

旧Gemini成果物の移行は次で再検証できます。既定ではコピーだけを行い、元成果物を残します。

```bash
uv run python scripts/migrate_gemini_results.py --dry-run
uv run python scripts/migrate_gemini_results.py
```

すべての移行先がSHA-256で一致することを確認した後に、旧モデル依存ファイルだけを削除する場合は明示的に次を使います。`output/` のstate series・network・baselineなどの共有入力は残ります。

```bash
uv run python scripts/migrate_gemini_results.py --cleanup-verified
```

API推論を実行せず、未生成runだけの入力token数と料金を事前確認できます。

```bash
uv run python scripts/run_llm_extraction.py \
    --run-ids 6 \
    --estimate-cost

uv run python scripts/run_direct_log_baseline.py \
    --extract-only \
    --estimate-cost
```

入力tokenはBedrock CountTokensで計測し、Inference Profileや権限等により利用できない場合は保守的なUTF-8 byte基準へfallbackして `approximate` と表示します。出力tokenは実行前には確定できないため、`BEDROCK_ESTIMATED_OUTPUT_TOKENS` を設定した場合の想定値と、`BEDROCK_MAX_TOKENS` を全件使った最大側見積もりを分けて表示します。表示料金は見積もりであり、実際のAWS請求額とは異なる可能性があります。

評価5〜10をGemini成果物のcheckpointに関係なく最初から再実行する場合は、専用のread-only見積もりを使います。Converseによる推論、checkpointの削除・更新、評価処理は行いません。

```bash
uv run python scripts/estimate_evaluation_costs.py \
    --run-ids 5 6 7 8 9 10 \
    --models \
      us.anthropic.claude-haiku-4-5-20251001-v1:0 \
      <MODEL_ID_2> \
      <MODEL_ID_3> \
    --evaluation9-experiment output/9_hestia/full \
    --evaluation9-duration-experiment output/9_hestia/duration \
    --evaluation10-output-dir output/10_switchbot/2026-09-01_2026-09-08
```

`--models` を省略すると `BEDROCK_MODEL_ID` の1モデルだけを計算します。複数指定時もinput tokenを共通値として使い回さず、各model IDでCountTokensを実行します。CountTokensを利用できないモデルは個別にfallbackへ切り替わります。一括見積もりでは想定出力料金も必須項目なので、`BEDROCK_ESTIMATED_OUTPUT_TOKENS` を設定してください。実行前に、評価7のtop-10 manifest、評価9の通常本実験とtrain期間感度実験のprepared Hestia experiment、評価10の`preparation.json`と`network/`が必要です。評価9・10が未準備なら、推論を許可せずに前処理まで実行します。

```bash
uv run python scripts/evaluate_9_hestia.py \
    --stage generate \
    --plan Hestia/examples/experiments/noise_free.yaml \
    --experiment output/9_hestia/full \
    --output-dir results/9_hestia/full
uv run python scripts/evaluate_9_hestia.py \
    --stage prepare \
    --experiment output/9_hestia/full \
    --output-dir results/9_hestia/full

uv run python scripts/evaluate_9_duration.py --stage generate
uv run python scripts/evaluate_9_duration.py --stage prepare

uv run python scripts/evaluate_10_switchbot.py \
    --snapshot data/switchbot/2026-09-01_2026-09-08 \
    --stage prepare
```

既定の保存先は、全モデル・全評価とモデル別TOTALを持つ `output/cost_estimates/evaluation_5_10_cost_estimate.csv`、同名のJSON、およびTOTALだけを比較する `output/cost_estimates/model_comparison_summary.csv` です。評価8は評価5の154日出力と評価6の14日出力を再利用する後段分析なので、5〜10を一連で実行するTOTALでは追加LLMリクエストを0件として重複課金を避けます。評価9は通常本実験216件に加え、`duration.json` に列挙されたtrain期間windowをそれぞれ独立に数えます。既定の3/7/14/28日では864件が追加され、評価9全体は1080件です。評価7のrun 2〜5は指定したtop-10 manifestを使う条件付き見積もりであり、Bedrockによるrun 1の順位が変われば対象条件とtoken数も変わり得ます。

モデル別単価は [`configs/llm_pricing.json`](configs/llm_pricing.json) の `bedrock` オブジェクトへmodel IDごとに登録します。現在のClaude Haiku 4.5の値は研究資料上の通常推論単価（入力 `$1.00` / 1M tokens、出力 `$5.00` / 1M tokens）です。AWSの料金や利用tierを実験前に確認し、変更があればこのファイルを更新してください。未登録model IDには別モデルの単価を流用しません。通常の単一run見積もりはエラーで停止し、複数モデル比較ではtoken数を記録しつつ料金をN/Aとして明示します。

AWS Access Key IDやSecret Access KeyをソースコードやREADMEへ記載せず、`aws configure`、`AWS_PROFILE`、IAMロール等を利用してください。保存済みのLLM成果物やcheckpointは同じmodel IDの実行だけで再利用されます。

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
| LLM provider | `google_gemini` |
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
