# Streamlit Evaluation Dashboard

Python + Streamlitで評価4〜10とHestia Studioをローカル利用するWebアプリです。評価は既存の研究ロジックを変更せず、画面上で設定した値から既存CLIコマンドを組み立てて `subprocess` で実行します。Hestia Studioだけは同じプロセスのPythonサービスを直接呼び出します。

## 起動方法

初回は依存関係を同期します。

```bash
uv sync
```

評価画面とHestia Studioを同じStreamlitアプリとして起動します。

```bash
uv run streamlit run app/streamlit_app.py
```

macOSでは、リポジトリ直下の `start_dashboard.command` をダブルクリックして起動することもできます。Dockからワンクリックで起動するには、Finderで同じ階層の `master-research-dashboard.app` をDockへドラッグします。この `.app` はリポジトリ直下の `uv` 環境から直接ダッシュボードを起動するため、リポジトリ直下に置いたままにしてください。ダブルクリック時は、このリポジトリの既存ダッシュボードだけを停止して最新ソースで再起動し、既定のブラウザを開きます。ポート8501を別アプリが使っている場合は停止せず、エラーを表示します。

## 評価番号の選択

左サイドバーの「評価を選択」から以下を選びます。

| 評価 | 内容 |
|---|---|
| 評価4 | 1つのパターンJSONをADL区間と照合し、IoU、境界、interval hitを出す。 |
| 評価5 | frequency / rule-filtered / FP-Growth / transition_probability / proposedを、Useful non-redundant rateとFragmentation rateで比較する。 |
| 評価6 | proposedとdirect-log baselineのADL解釈ラベルset一致を比較する。 |
| 評価7 | proposedのみについて、Kとハミング距離を変えたADL解釈ラベル精度を比較する。 |
| 評価8 | 評価6詳細を出現頻度のLow / Middle / Highに分け、ADL整合性を後段比較する。 |
| 評価9 | Hestia合成ログの生成・提案手法抽出・系列回収とADL意味対応の採点。 |
| 評価10 | SwitchBot実宅ログを前半train/後半testに分け、生成系列の再出現を評価する。 |

サイドバーの `dry-run` が有効な場合、コマンドと履歴だけを保存し、実処理は実行しません。重いLLM処理を走らせる前にコマンド確認に使ってください。

「ステップ実行」タブには一括実行モードがあります。

| モード | 内容 |
|---|---|
| 不足ファイル生成のみ | 評価本体や比較本体を実行せず、前段ステップのうち期待出力が不足しているコマンドだけを上から順に実行する。 |
| 不足ファイル生成 + 評価本体 | 前段ステップは不足分だけ生成し、その後に評価本体または比較本体を実行する。通常はこのモードで最初から最後まで実行できる。 |
| 全ステップを再実行 | 表示中の全ステップを上から順に実行する。既存出力があっても再実行するため、LLM抽出や結果上書きに注意する。 |

評価本体だけを再実行したい場合は、各ステップの個別ボタンも引き続き使えます。

一括実行はバックグラウンドの独立プロセスで動作する。開始後も評価を切り替えて別の一括実行を開始でき、画面上部の「バックグラウンド一括実行」に実行済みステップ数・総ステップ数・現在実行中のステップを表示する。終了後も直近5件は成功／失敗、停止ステップ、失敗ログとともに表示するため、表示から消えたことを失敗と判断する必要はない。異なる出力先を使う評価は並行実行できるが、同じ出力先を更新する一括実行は成果物競合を防ぐため先行実行が完了するまで開始できない。各ステップの詳細な処理状況は、対応する実行ログで確認できる。

## 共通設定

| 項目 | 説明 |
|---|---|
| 評価・テストを選択 | 評価4〜10に加え、実APIを1回だけ呼ぶ独立した `APIテスト` を選べます。 |
| 実行LLMモデル | 評価4〜10のLLM生成・評価で使うモデルを選ぶ。既定は **Claude Fable 5**（`us.anthropic.claude-fable-5`）。前処理・baseline・state series・ログは `output/<model>/`、LLM JSON、checkpoint、metrics、評価結果は `results/<model>/` に分離する。 |
| Python実行方法 | READMEの既定に合わせて `uv run python` を既定にしています。`.app` / `start_dashboard.command` 起動時は `uv` の絶対パスを子プロセスにも引き継ぐため、テスト実行でも `uv` を見失いません。 |
| run名 | ログディレクトリ名に使います。CLI引数には渡しません。 |
| チャタリング除去時間（秒） | 代表状態・状態遷移ネットワーク作成時の遅延OFF窓幅。既定は `5` 秒で、`0` は無効。評価4〜7と評価10の前段CLIへ渡す。 |
| dry-run | 実行せず、コマンドとログファイルだけを保存します。 |

モデル選択は、画面が起動する子プロセスにだけ `LLM_PROVIDER` とモデルIDを渡します。リポジトリ直下の `.env` は変更しません。Bedrockモデルでは `.env` または通常のAWS認証チェーンに有効なAWS認証情報とリージョンを、Geminiでは `GEMINI_API_KEY` をあらかじめ設定してください。GPT-5.6 Sol/Terra/LunaおよびClaude Fable 5のBedrock Converse呼出しは任意の `temperature` を送らず、Bedrock既定値を使い、成果物メタデータでは `temperature: null` と記録します。Claude Fable 5の料金はこのリポジトリの固定価格表に未登録のため、公式価格を確認するまでコスト見積もりは停止します。画面上の入力JSON・中間出力・ログの既定値は `output/<model>/`、LLM出力と評価結果の既定値は `results/<model>/` へ切り替わります。

評価4・5・6・8の代表状態数とハミング距離閾値は、評価7の選定結果に合わせて `K=10`、`hamming=2` を既定値にしています。評価7は感度分析のため、複数条件を指定する探索範囲を維持します。

`seed` や `overwrite` は対象CLIに実在する引数がないため、UI項目として追加していません。

チャタリング除去時間を変更しても既存成果物のファイル名は変わらない。既存条件を別の秒数で作り直す場合は「全ステップを再実行」を使うか、入力・出力パスを条件別に分ける。評価8は既存の評価6詳細CSV、提案手法JSON、state seriesを読む後段分析なので、この値を再適用しない。評価8では入力成果物を生成したときの値と合わせる。

## 評価4のステップ

参照ドキュメント: `docs/evaluations/evaluation_4_labeled_casas_adl.md`

1. 代表状態・状態遷移ネットワークを作成  
   `scripts/run_build_network_from_labeled_casas.py` を実行します。入力は `--labeled-casas`, `--sensor-map`, `--days`, `--n-states`, `--hamming-threshold`, `--smoothing-window-sec` です。

2. 提案手法LLMパターンを抽出  
   `scripts/run_llm_extraction.py` を実行します。APIキーを使う重い処理です。

3. 評価4を実行  
   `scripts/evaluate_adl_labels.py` を実行します。主な出力は `pattern_occurrences.csv`, `pattern_adl_mapping.csv`, `filtered_predictions.csv`, `adl_metrics_iou_*.csv`, `boundary_metrics_iou_*.csv`, `adl_interval_hit_metrics.csv`, `evaluation_summary.json`, `state_series.csv` です。

## 評価5のステップ

参照ドキュメント: `docs/evaluations/evaluation_5_adl_correspondence.md`

1. 代表状態・状態遷移ネットワークを作成  
   `scripts/run_build_network_from_labeled_casas.py` を評価5条件で実行します。`state/aruba_{K}_{hamming}_{days}days.txt` と `picture/aruba_{K}_{hamming}_{days}days/state_transition_all.json` を作成します。

2. 提案手法LLM出力を生成  
   `scripts/run_llm_extraction.py` を実行し、評価5で使う proposed JSON を作成します。APIキーを使う重い処理です。

3. 評価5用 `state_series_220days.csv` を作成
   `scripts/evaluate_adl_labels.py` を `--state-series-preprocessing network-equivalent --smoothing-window-sec 5 --state-series-days 220 --state-series-only` で実行し、抽出側と同じ1秒粒度化、遅延OFF平滑化、固定代表状態写像、同一状態圧縮を適用した評価5専用の中間出力 `output/<model>/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv` を作成します。K、ハミング距離、代表状態の構築日数を変えた場合は、それらを含む別ディレクトリを使います。

4. 評価5を実行  
   抽出時と同じ1秒粒度化・遅延OFF・代表状態写像・同一状態圧縮で評価用state seriesを作成し、`scripts/evaluate_adl_correspondence.py` を実行します。代表状態定義から算出するlow-information ratioは診断値であり、UsefulとContextlessには使用しません。主な出力は `evaluation5_summary_by_method.csv`, `evaluation5_summary_by_method_by_run.csv`, `evaluation5_pattern_details.csv`, `evaluation5_summary.json` です。

変更可能な主な引数は、run数、train/test split、grounded/useless閾値、assigned ADL閾値、FP-Growth設定、transition_probability設定、baseline cache設定、fragmentation閾値、Other状態・Other ADLの扱いです。low-information閾値はCLI互換のため受理されますが無視され、診断用ratioだけが保存されます。評価5画面の `runs` は既定で5です。`runs=5` にすると、`run_llm_extraction.py --runs 5` で提案手法JSONを5回分作成し、評価本体も `--runs 5` で `evaluation5_summary_by_method.csv` に平均と標準偏差、`evaluation5_summary_by_method_by_run.csv` にrun別summaryを出力します。frequency / rule / FP-Growth / transition_probability はrun非依存のため最初の評価runだけで評価し、2回目以降は提案手法だけを評価します。FP-Growth / transition_probability の生成済みパターンは、既定で `output/<model>/5_adl_correspondence_baselines_fixed/` に保存して再利用します。複数run用テンプレート欄では、評価に使うrun別LLM JSONの存在確認も表示します。

結果タブでは `evaluation5_summary_by_method.csv` を選ぶと、`useful_non_redundant_pattern_rate`, `fragmentation_rate`, `contextless_useless_rate` を手法別に表示・グラフ化できます。`evaluation5_summary_by_method_by_run.csv` ではrunごとの対象数、比較可能pair数、比較可能な子パターン数、Fragmentationのばらつきを確認できます。`evaluation5_pattern_details.csv` では各パターンの `run`, `is_adl_grounded`, `is_low_information`, `is_contextless_useless`, `is_fragmented`, `comparable_fragment_parent_ids`, `fragment_parent_ids`, `is_useful_non_redundant` を確認できます。

## 評価6のステップ

参照ドキュメント: `docs/evaluations/evaluation_6_adl_interpretation_set.md`

1. 14日版の代表状態・状態遷移ネットワークを作成
   `scripts/run_build_network_from_labeled_casas.py --days 14` を実行します。

2. 提案手法LLM出力を生成  
   `scripts/run_llm_extraction.py --days 14` を実行します。`--runs` で複数runを生成できます。

3. 評価6用 `state_series.csv` を作成  
   `scripts/evaluate_adl_labels.py --state-series-preprocessing network-equivalent` で、先頭14日から作成した代表状態定義を固定し、network構築と同じ遅延OFF平滑化で全220日を写像した比較用の照合系列を `output/<model>/6_adl_evaluation_aruba_individual_10_2_14days/state_series.csv` へ保存します。`--state-series-days` は指定しません。`14days` は抽出・LLM入力条件であり、照合期間は全220日です。部屋統合を選んだ場合だけ既存互換の `aruba_` 名を使います。

4. LLM単独ベースラインを生成  
   既定では `scripts/run_direct_log_baseline.py --log-days 14 --llm-only-time-mode split --extract-only` を実行します。既存の Morning / Daytime / Night / Midnight ごとに代表状態系列を分け、各時間帯を独立してLLMへ入力します。画面の「LLM-only input」で `Split by time period (default)` またはIoT2026再現用の `Legacy unsplit` を選べます。

5. 評価6の手法間比較を実行  
   `scripts/evaluate_6_compare_adl_interpretation_set.py` をholdout（Day 155–220）で実行します。split選択時は両手法を `sequence × time_period` 単位で評価し、LLM-onlyの出現検索もpattern自身の時間帯だけに制限します。主な出力は `evaluation6_method_comparison.csv`, `evaluation6_method_comparison_by_run.csv`, `evaluation6_llm_usage_comparison.csv`, `evaluation6_pattern_set_details_by_method.csv`, `evaluation6_by_*_by_method.csv`, `evaluation6_comparison_summary.json` です。

Evaluation 7のbest-condition manifestを指定した場合、DashboardはK/h・sensor representation・期間境界の手入力がmanifestと一致することを確認し、比較・生成の成果物パスはmanifest条件のcanonical pathへ解決する。不一致のK/hや表現はコマンド実行前に停止する。Strict Ablationでは、選定済みGPT-5.6 Sol manifestをClaude Fable 5など別の生成モデルの条件ソースとして選べる。この場合も生成・state series・Strict結果は選択した生成モデルの名前空間に保存し、manifest出所をmetadataへ残す。Strictトラックの画面はstate table/STN確認、state series作成、LLM生成、holdout採点の順に表示する。「不足ファイル生成のみ」は指定した全runについて両手法の`run_<N>.json`を確認し、不足runを生成する。採点は「不足ファイル生成 + 評価本体」または個別ステップで実行する。

評価6・7画面では旧sentinelラベルの選択欄を表示しない。`no_occurrence`, `no_adl_overlap`, `prediction missing`, `unknown` は評価ロジックで固定された別状態であり、conditional/end-to-end指標とcoverage/rateへ一貫して反映される。旧CLI引数は既存コマンドとの互換性のため受理されるが、アプリが新規生成するコマンドには付与しない。

アプリの標準条件は、評価7の選定結果に合わせて代表状態数 `K=10`、ハミング距離閾値 `2` です。個別センサ既定の中間出力には `output/<model>/6_adl_evaluation_aruba_individual_10_2_14days/` を使い、Kやハミング距離を変えた場合も `output/<model>/6_adl_evaluation_aruba_individual_{K}_{hamming}_{days}days/` を使います。部屋統合を選んだ場合だけ既存互換の `aruba_` 名を使います。

## 評価7のステップ

参照ドキュメント: `docs/evaluations/evaluation_7_parameter_sensitivity_adl_interpretation.md`

1. 条件別の代表状態・状態遷移ネットワークを作成  
   `scripts/run_build_network_from_labeled_casas.py` を条件ごとに実行します。`state/aruba_{K}_{hamming}_{days}days.txt` や `picture/aruba_{K}_{hamming}_{days}days/state_transition_all.json` がない場合に使います。

2. 条件別の提案手法LLM run 1--5を生成
   `scripts/run_llm_extraction.py --runs 5` を条件ごとに実行します。正式条件は14日、K=`10,15,20,25,30,35,40`、hamming=`0,1,2,3` の全28条件です。

3. 条件別の `state_series.csv` を作成  
   `scripts/evaluate_adl_labels.py --write-state-series --state-series-preprocessing network-equivalent` を、network構築と同じ平滑化値で条件ごとに実行します。固定した14日版state tableを全220日に適用し、Day 15–154だけを評価7のK,h選択に使います。個別センサ既定では `output/<model>/6_adl_evaluation_aruba_individual_{K}_{hamming}_{days}days/state_series.csv` がない場合に使います。

4. 全28条件をrun 1--5で評価
   `scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py --days 14 --runs 5 --split-mode holdout` を実行し、Day 15–154の各条件の平均と標準偏差から最適条件を選びます。

主な出力は `evaluation7_condition_summary.csv`, `evaluation7_condition_summary_by_run.csv`, `evaluation7_pattern_set_details.csv`, `evaluation7_by_pred_label.csv`, `evaluation7_by_true_label.csv`, `evaluation7_by_time_band.csv`, `evaluation7_summary.json` です。

Streamlit画面は正式条件（14日・全28条件・各5 run）を固定で表示する。一括実行の「不足ファイル生成 + 評価本体」は、条件ごとの不足runだけを生成して全条件を5回平均する。個別センサ既定の新しい結果は `results/<model>/7_param_search_14d_5runs_individual_holdout/` に保存し、旧30日・二段階探索の成果物を上書きしない。

## APIテスト

サイドバーの「評価・テストを選択」で `APIテスト` を選ぶ。任意の正式K/h条件・1時間帯（既定: `K=10, hamming=2, Morning`）を選び、明示許可後に**実APIを1回だけ**呼び出せます。通常抽出と同じプロンプトとLLM adapterを使うが、retryやcheckpoint再利用は行わず、JSON配列・4必須キー・許可ADLラベル・系列長の厳密な契約を検証します。結果は `results/<model>/api_smoke_tests/` に分離され、評価4〜10の入力・checkpoint・集計には使いません。

## 評価8のステップ

参照ドキュメント: `docs/evaluations/evaluation_8_frequency_stratified_adl_consistency.md`

評価8ではラジオボタンで「154日: 提案手法のみ」（既定）または「14日: 提案手法 vs LLM単独ベースライン」を選択して実行する。代表状態数K（既定10）、ハミング距離閾値（既定2）、runs（既定5）を変更できる。14日比較をK=10、h=2、14日で選ぶと、個別センサの正式Full-pipeline評価6詳細CSV `results/<model>/6_adl_match_individual_holdout_test_direct_time_split/evaluation6_pattern_set_details_by_method.csv` と対応する `output/<model>/6_adl_evaluation_aruba_individual_10_2_14days/state_series.csv` を既定として入力する。他条件では誤った成果物を選ばないよう入力欄を空にし、対応する評価6詳細CSVとstate-seriesを明示指定する。頻度帯方式は選択式ではなく、三分位と固定回数帯を一度のコマンドで両方実行する。各pattern ID自身の出現だけを取得し、同じ物理区間を一意化した後の件数からrunごとに帯を再割当てする。比較scopeでも評価6詳細CSVの旧出現数をそのまま使わず、画面で指定した同条件のstate-series CSVからown-ID出現数を再構築する。入力評価は重複実行せず、同じ評価レコードから2方式を集計し、指定したoutput directoryの `tertile/` と `fixed/` に分けて保存する。固定帯の下限（既定`0,1,10,100,1000,10000`）は変更できる。154日・提案手法のみの`fixed/`には、帯別の平均パターン数分布とPrecision / Recall / F1図も保存できる。修正版の標準出力先は `results/<model>/8_proposed_own_id_fixed/` と `results/<model>/8_vs_llm_own_id_fixed/` で、run別CSV、修正前後件数、重複監査、重み総和検証を保存する。

## 評価10のステップ

参照ドキュメント: `docs/evaluations/evaluation_10_switchbot_holdout.md`

1. `events.csv` と `manifest.json` を検証し、前半trainだけで代表状態表、時間帯別network、frequencyパターンを生成する。
2. API許可時だけ、train側networkから既存提案手法のLLMパターンを抽出する。
3. 固定した状態表で後半testを採点し、再出現割合、日単位再現率、遷移被覆率を出力する。

一括実行でもLLM APIはチェックボックスを有効にした場合だけ呼ぶ。正式K/hの根拠は、実行モデルにかかわらず確定済みの`results/gpt-5.6-sol/7_param_search_14d_5runs_individual_holdout/evaluation7_best_condition_manifest.json`である。前処理の期待出力が揃っている場合、「不足ファイル生成 + 評価本体」はステップ1を再実行せず、LLM抽出から再開する。入力hashまたはこのmanifestのhashが準備時から変わっている場合、後段CLIは停止する。

Claude Fable 5では、評価9の「本実験」と「期間感度評価」を選んだとき、画面はそれぞれ現在のhash付き中間成果物・集計先を初期表示する。評価10も現在のSwitchBot snapshotの正式namespaceを初期表示する。これらは再開用の既存成果物であり、別のモデル・snapshot・実験条件へ切り替える場合は対応する別ディレクトリを明示する。

## ログとコマンド履歴

ログは以下に保存されます。

```text
output/logs/evaluation_dashboard/
```

各ステップのログはrun名付きのサブディレクトリに保存されます。一括実行では `{run名}_batch` のログディレクトリに、実行したコマンドを番号付きログで保存します。同じディレクトリの `batch_plan.json` は開始時点で固定したコマンド・入力・出力先、`batch_status.json` は実行中ステップと完了数を記録する一時的な管理ファイルです。コマンド履歴は `output/<model>/logs/evaluation_dashboard/command_history.jsonl` に追記されます。

## 結果表示と過去run比較

「結果比較」タブでは、既存の `results/<model>/` と、アプリの候補パターンに一致する一部の評価6中間 `output/<model>/` からCSV/JSONを検出します。標準条件の中間ディレクトリが候補に含まれない場合は、入力欄で直接指定します。

- CSVは `st.dataframe` で表示します。
- CSVは「表示するカラム」で、見たい列だけに絞り込めます。
- JSONは整形表示します。
- `method` と F1 / precision / recall / Jaccard などの列があるCSVは棒グラフ表示できます。
- 複数の summary CSV を選ぶと、source列付きで結合表示できます。
- 評価4、評価5、評価6、評価7、評価8の各READMEにある「結果の読み方」に合わせて、見るべきファイル順と読み方を結果タブ内に表示します。
- 表示ファイルのプルダウンは、READMEで推奨している確認順を優先して並べます。
- `results/gpt-5.6-sol/reviewer_response/<run>/` に査読対応版の統合summaryがある場合は、結果比較の先頭に現在選択中の評価だけの表、生成済み図、数値に紐づく箇条書き考察を表示する。ここは既存成果物の読み取り専用であり、LLM APIやパターン生成は実行しない。

## トラブルシューティング

| 症状 | 確認点 |
|---|---|
| `streamlit` が見つからない | `uv sync` 後に `uv run streamlit run app/streamlit_app.py` を使う。 |
| 入力ファイルがmissingになる | 前段ステップが未実行か、K / hamming / days の条件が入力ファイル名とずれていないか確認する。評価7では `skip-missing-conditions` で未生成条件をスキップできる。 |
| LLM抽出で失敗する | 選択したモデルに必要な認証を確認する。Geminiは `.env` の `GEMINI_API_KEY`、BedrockはAWS認証チェーン・リージョン・model accessが必要。Claude Fable 5は、US推論プロファイルの全宛先リージョン（`us-east-1`、`us-east-2`、`us-west-2`）でBedrockデータ保持モードを `aws_review` に設定する。設定反映中のFable 5だけは保持モード拒否を最大6回再試行し、ほかの一時的なBedrockエラーは最大3回まで再試行する。既に完了したモードのcheckpointは次回実行で再利用する。ログには秘密値を出さないよう簡易redactionしています。 |
| 評価5/6でrunが足りない | `--runs` と実在するJSON数を揃えるか、`skip-missing-runs` を有効化する。 |
| CLIでは動くが画面では動かない | コマンドプレビューをコピーし、同じworking directoryで実行して差分を見る。 |

## 既存CLIとの関係

評価4〜10は既存CLIを呼び出します。従来通り以下のようなコマンド実行も可能です。

```bash
uv run python scripts/evaluate_adl_labels.py --help
uv run python scripts/evaluate_adl_correspondence.py --help
uv run python scripts/evaluate_6_compare_adl_interpretation_set.py --help
uv run python scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py --help
uv run python scripts/evaluate_8_frequency_stratified_adl_consistency.py --help
```

## 評価9のステップ

[評価9の手順と指標](../evaluations/evaluation_9_hestia.md) を参照。`scripts/evaluate_9_hestia.py` で生成、前処理、頻度対照、LLM予算表示／抽出、採点を順に実行する。共通の平滑化設定は使わず、実験計画の設定を使う。API許可は既定OFF。評価9の一括実行は既存出力があっても各前段をCLIへ渡してhash検証・再利用する。結果は `results/<model>/9_hestia/<実験名>/evaluation9_summary.csv` と `.json`。

設定画面の **3住宅のつながり** では、compact / corridor / branched の部屋と接続を横並びで確認できる。線のラベルはHestiaが生成するドアセンサーIDと移動時間を表す。base / large variability は住宅構造を変えず、行動の揺らぎだけを変える。

評価9の **実験プリセット** はPilot、本実験・小規模確認、本実験、期間感度評価を選べる。既存planを直接読み、seed一覧とLLM run数だけをGUIで上書きする。本実験は6条件・train 14日/test 7日で、Aruba正式評価と同じ14日間の履歴から系列を生成する。小規模確認は`noise_free.yaml`の6条件・14日/7日・その他全設定を維持し、seed=[11]、LLM 1反復、専用の`full_smoke`出力を既定とするため、fresh推定は24 API callsである。期間感度は同一35日rawログから3/7/14/28日trainと共通7日testを派生し、14日をbaselineとしてpaired差分を出す。raw生成18 run、LLM対象72 window、fresh推定864 callsである。期間感度を選ぶと **期間ごとの並列数**（既定4）が表示され、raw生成と最終集計は直列、prepare・頻度対照・LLM抽出は期間ごとに並列で実行する。API利用時は同時リクエスト数も増えるため、利用枠に応じて並列数を下げられる。確定した全項目は`output/<model>/logs/evaluation_dashboard/evaluation9_plans/`へ内容hash付きeffective planとして保存され、生成ステップはsource planではなくこのファイルを使う。画面にはHestia生成run数と、4時間帯・期間数を掛けたfresh API呼び出し推定、parse retry込み上限を表示する。API許可は従来どおり既定OFFである。

既存`experiment.json`とeffective plan、または既存`prepared.json`と現在の研究コード／設定の指紋が一致しない場合は実行前に停止する。新しい出力先にはeffective plan hashに加えて現在の研究コード指紋も付与するため、同じplanでコード更新後に前回失敗した出力先を再選択しない。明示確認後に既存の生成・集計ディレクトリを`output/<model>/logs/evaluation_dashboard/evaluation9_backups/`へ退避して同じパスを再利用することもできる。後者もhash検証は回避せず、元パスを空にしてから再生成する。

## Hestia Studio

上部の **Hestia Studio** タブはStreamlit Components v2として同じページ内に直接描画される。Studio用サーバー、別ポート、iframe、起動・停止操作はない。Studio内の住宅タブで compact / corridor / branched の評価9 base住宅を切り替える。3住宅は初期データとして先読みされ、住宅ごとの未保存編集はページを開いている間保持される。ブラウザまたはStreamlitページを再読み込みする前にはYAML保存する。

部屋・デバイスのドラッグ、リサイズ、入力途中の更新はJavaScript側で処理する。Pythonへ同期するのは、少し間を置いた編集状態の保存と、検証・読込・保存・export・シミュレーション実行の明示操作だけである。これらの操作はHTTP APIを経由せず、Hestiaの共通`StudioService`から既存の`Scenario`、`load_scenario`、`SimulationEngine`を直接呼び出す。

Studio内では、部屋のドラッグ・リサイズ、接続の追加・削除と移動時間、センサー／デバイスの追加・削除・所属部屋・表示位置を編集できる。所属部屋や種類はシミュレーション設定、部屋内のアイコン座標は表示専用の `editor_layout` である。編集内容はStudio上部の **YAML保存** から `Hestia/scenarios/` に保存する。

間取り画面の **論文用SVG** / **論文用PNG** から、現在の住宅を白背景の図として保存できる。図には部屋、接続、移動時間、ドアセンサーID、センサー／デバイスID、凡例を含み、ホーム設定の表示名を図タイトルに使う。SVGは拡大可能なベクター、PNGは3200 × 2000 pxである。図は論文で住宅構造を説明するための可視化であり、評価9のground truthや検出器入力ではない。

論文用図の部屋名は表示名だけとし、内部ID（例: `Bedroom`に対する`bedroom`）を重複表示しない。機器は種類を18 px、ログ照合用IDを14 pxの二段で示す。プリセットのID接頭辞は `M_`＝人感センサー、`D_`＝ドアセンサー、`L_`＝照明で、図と画面に説明を付ける。種類は接頭辞から推測せずScenarioのdevice typeを使うため、独自IDでも正しい種類を表示する。内部IDや配置・シミュレーション設定自体は変更しない。

Studio保存ファイルは通常のHestiaカスタムシナリオであり、評価9の `noise_free.yaml` やexperiment生成処理へ自動的には組み込まれない。評価9の研究条件・gold・train/test分離を意図せず変更しないための分離である。シミュレーション結果は従来どおり `Hestia/outputs/studio/<run-name>/` に保存し、同名出力を上書きしない。
