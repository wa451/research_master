# Python File Inventory

この文書は、現在のフォルダ構成において「どこに、何というPythonファイルがあり、それぞれ何を担当しているか」をまとめた台帳です。

実装本体は原則として `src/behavior_pattern_mining/` 配下にあります。新しく実行する場合は `scripts/` 配下の入口を使ってください。

## 1. ルート直下

### 設定互換レイヤー

| ファイル | 役割 |
|---|---|
| `experiment_config.py` | `configs/default.yaml` を読み込み、既存コード互換の定数 `DATASET_NAME`, `N_STATES`, `HAMMING_THRESHOLD`, `DAYS` などを公開する。現時点では多数の `src/` モジュールから参照されているため削除不可。 |

## 2. scripts/

`scripts/` は現在の推奨実行入口です。中身は薄いCLIで、実装本体を `src/behavior_pattern_mining/` から呼び出します。

| ファイル | 役割 |
|---|---|
| `scripts/run_all.py` | 提案手法の主要パイプラインを一括実行する。`run_build_network -> run_baselines -> run_llm_eval_batch` の順に呼ぶ。 |
| `scripts/run_build_network.py` | センサログの前処理、代表状態抽出、状態遷移ネットワーク構築、図・JSON・状態テーブル出力を実行する。 |
| `scripts/run_build_network_from_labeled_casas.py` | ラベル付きCASAS txtからセンサーイベントを抽出し、センサーIDを代表状態テーブル用の部屋名へ変換して、状態遷移ネットワークと代表状態テーブルを生成する。評価6では `--days 14` で14日版成果物を生成し、条件変更時は `--n-states`、`--hamming-threshold`、`--smoothing-window-sec` を指定する。 |
| `scripts/run_baselines.py` | 遷移確率ベースラインと頻度ベースラインをまとめて実行する。 |
| `scripts/run_llm_extraction.py` | 提案手法のLLMパターン抽出のみを実行する。`--days`, `--n-states`, `--hamming-threshold` で評価6用の条件別ネットワークを入力にでき、`--runs` で複数回分、`--run-ids` で特定runだけを生成できる。 |
| `scripts/run_evaluation7_top_condition_repeats.py` | 評価7の初回summaryから上位N条件を選び、初回を含む合計run数まで不足分だけを生成して選抜条件manifestを保存する。 |
| `scripts/run_llm_eval_batch.py` | 提案手法のLLM抽出とベースライン比較評価を複数回実行し、Excelへ集計する。 |
| `scripts/run_direct_log_baseline.py` | ラベル付きCASAS txtからactivity labelを除き、抽出側と同じ前処理・代表状態写像で得た系列をネットワーク化せず直接LLMへ入力するベースラインを実行・評価する。評価6では `--log-days 14 --extract-only` で14日分のみ抽出し、`--n-states`, `--hamming-threshold`, `--runs` で条件別・複数回分を生成できる。 |
| `scripts/run_evaluation.py` | 既存のLLM出力JSONを、遷移確率ベースライン・頻度ベースラインと比較評価する。 |
| `scripts/run_groundedness.py` | LLM出力系列が状態遷移グラフ上の根拠を持つかを評価する。 |
| `scripts/evaluate_condition_metrics.py` | support, confidence, 時間間隔条件を用いた系列評価を実行する。 |
| `scripts/evaluate_adl_labels.py` | ラベル付きCASASデータを使い、抽出パターンとADL区間の対応付け、ADLカテゴリ別Precision/Recall/F1、境界誤差を評価する。 |
| `scripts/evaluate_adl_correspondence.py` | frequency, rule-filtered frequency, FP-Growth系baseline, transition_probability baseline, proposed method のパターンを共通形式に正規化し、評価5の3指標を手法別に比較する。low-information ratioは診断値に限定し、time-band限定照合、同一run・時間帯内のfragmentation判定、比較可能pair数を出力する。pair=0でもfragmented/evaluableを0として出力する。 |
| `scripts/evaluate_6_compare_adl_interpretation_set.py` | 評価6について、先頭14日を入力とする提案手法とLLM単独ベースラインを、14日条件の代表状態定義で写像した同じ全220日状態系列・ADL正解区間で比較する。`--runs` で複数run平均も出力する。 |
| `scripts/evaluate_8_frequency_stratified_adl_consistency.py` | 評価6詳細CSVまたは提案手法JSONを入力に、pattern ID固有の物理出現を一意化し、修正後出現数からrunごとにLow / Middle / Highを再割当てしてADL解釈ラベル整合性を集計する。修正前後件数、run別値、頻度加重の重み監査も保存する。 |

## 3. src/behavior_pattern_mining/

研究ロジックの実装本体です。

### パッケージ直下

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/__init__.py` | Pythonパッケージ初期化ファイル。 |
| `src/behavior_pattern_mining/config.py` | YAML風の設定ファイルを読み込む軽量設定ローダー。`experiment_config.py` から利用される。 |

### baselines/

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/baselines/__init__.py` | ベースライン手法パッケージの初期化ファイル。 |
| `src/behavior_pattern_mining/baselines/transition_probability.py` | モード別状態遷移JSONから、遷移確率閾値以上のパスをDFSで列挙する遷移確率ベースライン。 |
| `src/behavior_pattern_mining/baselines/frequency.py` | 代表状態系列上の連続部分列をカウントする頻度ベースライン。 |

### states/

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/states/__init__.py` | 状態処理パッケージの初期化ファイル。 |
| `src/behavior_pattern_mining/states/state_mapping.py` | イベントログ読み込み、状態定義TSV読み込み、期間切り出し、ハミング距離、代表状態へのマッピングなどの共通処理。 |

### visualization/

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/visualization/__init__.py` | 可視化パッケージの初期化ファイル。 |
| `src/behavior_pattern_mining/visualization/state_transition_visualizer.py` | センサログ前処理、代表状態抽出、状態遷移ネットワーク構築、状態遷移図・タイムライン図・JSON・状態テーブル出力を担当する中核モジュール。現状では複数責務を持つ大きなファイル。 |

### llm/

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/llm/__init__.py` | LLM関連パッケージの初期化ファイル。 |
| `src/behavior_pattern_mining/llm/client.py` | `.env` 読み込み、Gemini API呼び出し、LLM応答JSONパース、token使用量抽出を行う共通クライアント。 |
| `src/behavior_pattern_mining/llm/pattern_extractor.py` | 時間帯別状態遷移ネットワークJSONをLLMへ渡し、生活行動パターンを抽出・統合する提案手法のLLM抽出モジュール。 |
| `src/behavior_pattern_mining/llm/direct_log_extractor.py` | ラベル付きCASAS txtからセンサーイベントだけを抽出し、代表状態系列を直接LLMへ渡すLLM単独ベースライン用の抽出モジュール。 |

### evaluation/

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/evaluation/__init__.py` | 評価パッケージの初期化ファイル。 |
| `src/behavior_pattern_mining/evaluation/metrics.py` | パターン読み込み、完全一致・部分一致判定、Precision/Recall/F1計算、評価レポート生成の共通処理。 |
| `src/behavior_pattern_mining/evaluation/compare_patterns.py` | 提案手法LLM出力を、遷移確率ベースライン・頻度ベースラインと比較する評価モジュール。 |
| `src/behavior_pattern_mining/evaluation/direct_log.py` | 前処理済み代表状態系列を直接入力するLLM単独ベースライン出力を比較し、レポート・Excelを生成する。 |
| `src/behavior_pattern_mining/evaluation/groundedness.py` | Markov graphの読み込み、LLM系列のエッジ存在・確率閾値・系列長・自己ループ条件の判定を行う純粋ロジック。 |
| `src/behavior_pattern_mining/evaluation/groundedness_check.py` | Groundedness評価を実行し、CSV出力する実行寄りモジュール。 |
| `src/behavior_pattern_mining/evaluation/condition_metrics.py` | support, confidence, 最大時間間隔などの条件グリッドでLLM系列を評価するモジュール。 |
| `src/behavior_pattern_mining/evaluation/adl.py` | ラベル付きCASASデータを区間化し、抽出パターンとの時間重なり、ADL割当、同一ADL予測のマージ、短時間予測除外、Temporal IoU、区間内hit、境界誤差を計算するADL評価ロジック。 |
| `src/behavior_pattern_mining/evaluation/adl_correspondence.py` | 複数手法の系列パターンCSV/JSON読み込み、FP-Growth系baseline/transition_probability baseline生成、評価5のUseful non-redundant pattern rate、Fragmentation rate、Contextless useless rateを計算する後段評価ロジック。 |
| `src/behavior_pattern_mining/evaluation/adl_interpretation_set.py` | LLM解釈ラベル集合とADL重なりラベル集合を比較し、Exact Set Match, Jaccard, multi-label Precision/Recall/F1を計算する評価6ロジック。 |

### pipelines/

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/pipelines/__init__.py` | パイプラインパッケージの初期化ファイル。 |
| `src/behavior_pattern_mining/pipelines/run_all.py` | 提案手法の主要処理を順番に実行するパイプライン本体。 |
| `src/behavior_pattern_mining/pipelines/llm_eval_batch.py` | LLM抽出と評価を複数回実行し、評価指標をExcelにまとめるバッチ処理。 |

### io/

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/io/__init__.py` | I/Oパッケージの初期化ファイル。 |
| `src/behavior_pattern_mining/io/csv_io.py` | CSV書き込みの共通ヘルパ。 |

### data/

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/data/__init__.py` | データ読み込み・前処理用パッケージの初期化ファイル。現時点では実処理は主に `visualization/state_transition_visualizer.py` と `states/state_mapping.py` に残っている。 |

### network/

| ファイル | 役割 |
|---|---|
| `src/behavior_pattern_mining/network/__init__.py` | 状態遷移ネットワーク処理用パッケージの初期化ファイル。現時点では実処理は主に `visualization/state_transition_visualizer.py` に残っている。 |

## 4. support/

主パイプライン外の補助・調査用スクリプトです。

| ファイル | 役割 |
|---|---|
| `support/analyze_dataset.py` | OpenSHS系データセットの行数、活動ラベル、日付範囲などを確認する探索用スクリプト。 |
| `support/check_models.py` | `.env` のAPIキーを使い、Gemini APIで利用可能なモデルを確認する補助スクリプト。 |

## 5. tests/

標準ライブラリ `unittest` による最低限の回帰テストです。

| ファイル | 役割 |
|---|---|
| `tests/test_core_logic.py` | 設定読み込み、センサログ読み込み、前処理、代表状態マッピング、遷移確率、パターン長、Groundedness、Precision/Recall/F1などの基本ロジックを検証する。 |
| `tests/test_adl_evaluation.py` | ラベル付きCASAS ADL評価について、ラベル区間化、パターン出現検出、予測マージ、短時間除外、区間内hit、overlap/IoU、TP/FP/FN、重複マッチ防止などを検証する。 |
| `tests/test_adl_correspondence.py` | ADL対応比較評価について、複数形式の系列パース、手法別パターン読み込み、時系列train/test split、multi-label ADL、ADL-grounded/Useless判定を検証する。 |

## 6. 削除・整理候補

すぐ削除してはいけないものと、後で削除できるものを分ける。

### まだ削除しない

| ファイル | 理由 |
|---|---|
| `experiment_config.py` | `src/` 内の複数モジュールとテストが参照しているため、現時点では必要。 |
### 後で削除可能

| ファイル/ディレクトリ | 条件 |
|---|---|
| `__pycache__/`, `*.pyc`, `.DS_Store` | 生成物なので削除可能。 |
| `sequence_association_mining.py` | 主実験に不要なら削除可能。残す場合は `src/behavior_pattern_mining/baselines/association_mining.py` へ移す。 |
