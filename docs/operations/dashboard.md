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

## 共通設定

| 項目 | 説明 |
|---|---|
| Python実行方法 | READMEの既定に合わせて `uv run python` を既定にしています。 |
| run名 | ログディレクトリ名に使います。CLI引数には渡しません。 |
| チャタリング除去時間（秒） | 代表状態・状態遷移ネットワーク作成時の遅延OFF窓幅。既定は `5` 秒で、`0` は無効。評価4〜7と評価10の前段CLIへ渡す。 |
| dry-run | 実行せず、コマンドとログファイルだけを保存します。 |

評価4・5・6・8の代表状態数とハミング距離閾値は、評価7の選定結果に合わせて `K=15`、`hamming=0` を既定値にしています。評価7は感度分析のため、複数条件を指定する探索範囲を維持します。

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
   `scripts/evaluate_adl_labels.py` を `--state-series-preprocessing network-equivalent --smoothing-window-sec 5 --state-series-days 220 --state-series-only` で実行し、抽出側と同じ1秒粒度化、遅延OFF平滑化、固定代表状態写像、同一状態圧縮を適用した評価5専用の中間出力 `output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv` を作成します。K、ハミング距離、代表状態の構築日数を変えた場合は、それらを含む別ディレクトリを使います。

4. 評価5を実行  
   抽出時と同じ1秒粒度化・遅延OFF・代表状態写像・同一状態圧縮で評価用state seriesを作成し、`scripts/evaluate_adl_correspondence.py` を実行します。代表状態定義から算出するlow-information ratioは診断値であり、UsefulとContextlessには使用しません。主な出力は `evaluation5_summary_by_method.csv`, `evaluation5_summary_by_method_by_run.csv`, `evaluation5_pattern_details.csv`, `evaluation5_summary.json` です。

変更可能な主な引数は、run数、train/test split、grounded/useless閾値、assigned ADL閾値、FP-Growth設定、transition_probability設定、baseline cache設定、fragmentation閾値、Other状態・Other ADLの扱いです。low-information閾値はCLI互換のため受理されますが無視され、診断用ratioだけが保存されます。評価5画面の `runs` は既定で5です。`runs=5` にすると、`run_llm_extraction.py --runs 5` で提案手法JSONを5回分作成し、評価本体も `--runs 5` で `evaluation5_summary_by_method.csv` に平均と標準偏差、`evaluation5_summary_by_method_by_run.csv` にrun別summaryを出力します。frequency / rule / FP-Growth / transition_probability はrun非依存のため最初の評価runだけで評価し、2回目以降は提案手法だけを評価します。FP-Growth / transition_probability の生成済みパターンは、既定で `output/5_adl_correspondence_baselines_fixed/` に保存して再利用します。複数run用テンプレート欄では、評価に使うrun別LLM JSONの存在確認も表示します。

結果タブでは `evaluation5_summary_by_method.csv` を選ぶと、`useful_non_redundant_pattern_rate`, `fragmentation_rate`, `contextless_useless_rate` を手法別に表示・グラフ化できます。`evaluation5_summary_by_method_by_run.csv` ではrunごとの対象数、比較可能pair数、比較可能な子パターン数、Fragmentationのばらつきを確認できます。`evaluation5_pattern_details.csv` では各パターンの `run`, `is_adl_grounded`, `is_low_information`, `is_contextless_useless`, `is_fragmented`, `comparable_fragment_parent_ids`, `fragment_parent_ids`, `is_useful_non_redundant` を確認できます。

## 評価6のステップ

参照ドキュメント: `docs/evaluations/evaluation_6_adl_interpretation_set.md`

1. 14日版の代表状態・状態遷移ネットワークを作成
   `scripts/run_build_network_from_labeled_casas.py --days 14` を実行します。

2. 提案手法LLM出力を生成  
   `scripts/run_llm_extraction.py --days 14` を実行します。`--runs` で複数runを生成できます。

3. 評価6用 `state_series.csv` を作成  
   `scripts/evaluate_adl_labels.py` で、先頭14日から作成した代表状態定義を固定して全220日を写像した比較用の照合系列を `output/6_adl_evaluation_15_0_14days/state_series.csv` へ保存します。`14days` は抽出・LLM入力条件であり、照合期間は全220日です。

4. LLM単独ベースラインを生成  
   `scripts/run_direct_log_baseline.py --log-days 14 --extract-only` を実行します。

5. 評価6の手法間比較を実行  
   `scripts/evaluate_6_compare_adl_interpretation_set.py` を実行します。主な出力は `evaluation6_method_comparison.csv`, `evaluation6_method_comparison_by_run.csv`, `evaluation6_llm_usage_comparison.csv`, `evaluation6_pattern_set_details_by_method.csv`, `evaluation6_by_*_by_method.csv`, `evaluation6_comparison_summary.json` です。

評価6・7画面では旧sentinelラベルの選択欄を表示しない。`no_occurrence`, `no_adl_overlap`, `prediction missing`, `unknown` は評価ロジックで固定された別状態であり、conditional/end-to-end指標とcoverage/rateへ一貫して反映される。旧CLI引数は既存コマンドとの互換性のため受理されるが、アプリが新規生成するコマンドには付与しない。

アプリの標準条件は、評価7の選定結果に合わせて代表状態数 `K=15`、ハミング距離閾値 `0` です。中間出力には `output/6_adl_evaluation_15_0_14days/` を使い、Kやハミング距離を変えた場合も `output/6_adl_evaluation_{K}_{hamming}_{days}days/` を使います。

## 評価7のステップ

参照ドキュメント: `docs/evaluations/evaluation_7_parameter_sensitivity_adl_interpretation.md`

1. 条件別の代表状態・状態遷移ネットワークを作成  
   `scripts/run_build_network_from_labeled_casas.py` を条件ごとに実行します。`state/aruba_{K}_{hamming}_{days}days.txt` や `picture/aruba_{K}_{hamming}_{days}days/state_transition_all.json` がない場合に使います。

2. 条件別の提案手法LLM run 1を生成
   `scripts/run_llm_extraction.py` を条件ごとに実行します。`output/aruba_{K}_{hamming}_{days}days/llm_sequences_modes_{K}_{hamming}_{days}days_1.json` がない場合に使います。

3. 条件別の `state_series.csv` を作成  
   `scripts/evaluate_adl_labels.py --write-state-series` を条件ごとに実行します。`output/6_adl_evaluation_{K}_{hamming}_{days}days/state_series.csv` がない場合に使います。

4. 全条件をrun 1で評価
   `scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py` を実行し、上位条件を決めるための初回summaryを作成します。

5. 上位10条件を合計5回まで実行
   `scripts/run_evaluation7_top_condition_repeats.py` が初回summaryの上位10条件を選び、不足分のrun 2--5だけを生成します。run JSONごとに存在確認し、生成済みrunはスキップしてそのまま利用します。全40ファイルが存在する場合は、このステップ自体が一括実行対象から外れます。

6. 上位10条件の5回平均を評価
   `--conditions-file` と `--run-ids 1 2 3 4 5` を使い、選抜に使ったrun 1も含めて平均と標準偏差を計算します。最終評価後、`evaluation7_top10_5runs_conditions.csv` も `evaluation7_condition_summary.csv` と同じ指標列・5回平均値へ更新します。

主な出力は `evaluation7_condition_summary.csv`, `evaluation7_condition_summary_by_run.csv`, `evaluation7_pattern_set_details.csv`, `evaluation7_by_pred_label.csv`, `evaluation7_by_true_label.csv`, `evaluation7_by_time_band.csv`, `evaluation7_summary.json` です。

Streamlit画面では、`代表状態数 K` と `ハミング距離閾値` をカンマ区切りまたは空白区切りで指定できます。「二段階実行」は既定でON、上位条件数は10、合計実行回数は5です。一括実行の「不足ファイル生成 + 評価本体」では、初回summaryが既に存在すれば初回生成・評価をスキップし、上位10条件の不足分run 2--5と最終平均へ進みます。初回結果は `results/7_param_search/`、最終結果は `results/7_param_search/top10_5runs/` に分けて保存します。

## 評価8のステップ

参照ドキュメント: `docs/evaluations/evaluation_8_frequency_stratified_adl_consistency.md`

評価8ではラジオボタンで「154日: 提案手法のみ」（既定）または「14日: 提案手法 vs LLM単独ベースライン」を選択して実行する。代表状態数K（既定15）、ハミング距離閾値（既定0）、runs（既定5）を変更できる。頻度帯方式は選択式ではなく、三分位と固定回数帯を一度のコマンドで両方実行する。各pattern ID自身の出現だけを取得し、同じ物理区間を一意化した後の件数からrunごとに帯を再割当てする。比較scopeでも評価6詳細CSVの旧出現数をそのまま使わず、画面で指定した同条件のstate-series CSVからown-ID出現数を再構築する。入力評価は重複実行せず、同じ評価レコードから2方式を集計し、指定したoutput directoryの `tertile/` と `fixed/` に分けて保存する。固定帯の下限（既定`0,1,10,100,1000,10000`）は変更できる。154日・提案手法のみの`fixed/`には、帯別の平均パターン数分布とPrecision / Recall / F1図も保存できる。修正版の標準出力先は `results/8_proposed_own_id_fixed/` と `results/8_vs_llm_own_id_fixed/` で、run別CSV、修正前後件数、重複監査、重み総和検証を保存する。

## 評価10のステップ

参照ドキュメント: `docs/evaluations/evaluation_10_switchbot_holdout.md`

1. `events.csv` と `manifest.json` を検証し、前半trainだけで代表状態表、時間帯別network、frequencyパターンを生成する。
2. API許可時だけ、train側networkから既存提案手法のLLMパターンを抽出する。
3. 固定した状態表で後半testを採点し、再出現割合、日単位再現率、遷移被覆率を出力する。

一括実行でもLLM APIはチェックボックスを有効にした場合だけ呼ぶ。入力hashが準備時から変わっている場合、後段CLIは停止する。

## ログとコマンド履歴

ログは以下に保存されます。

```text
output/logs/evaluation_dashboard/
```

各ステップのログはrun名付きのサブディレクトリに保存されます。一括実行では `{run名}_batch` のログディレクトリに、実行したコマンドを番号付きログで保存します。コマンド履歴は `output/logs/evaluation_dashboard/command_history.jsonl` に追記されます。

## 結果表示と過去run比較

「結果比較」タブでは、既存の `results/` と、アプリの候補パターンに一致する一部の評価6中間 `output/` からCSV/JSONを検出します。標準条件の中間ディレクトリが候補に含まれない場合は、入力欄で直接指定します。

- CSVは `st.dataframe` で表示します。
- CSVは「表示するカラム」で、見たい列だけに絞り込めます。
- JSONは整形表示します。
- `method` と F1 / precision / recall / Jaccard などの列があるCSVは棒グラフ表示できます。
- 複数の summary CSV を選ぶと、source列付きで結合表示できます。
- 評価4、評価5、評価6、評価7、評価8の各READMEにある「結果の読み方」に合わせて、見るべきファイル順と読み方を結果タブ内に表示します。
- 表示ファイルのプルダウンは、READMEで推奨している確認順を優先して並べます。

## トラブルシューティング

| 症状 | 確認点 |
|---|---|
| `streamlit` が見つからない | `uv sync` 後に `uv run streamlit run app/streamlit_app.py` を使う。 |
| 入力ファイルがmissingになる | 前段ステップが未実行か、K / hamming / days の条件が入力ファイル名とずれていないか確認する。評価7では `skip-missing-conditions` で未生成条件をスキップできる。 |
| LLM抽出で失敗する | `.env` の `GEMINI_API_KEY` とネットワーク接続を確認する。ログにはAPIキー値を出さないよう簡易redactionしています。 |
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

[評価9の手順と指標](../evaluations/evaluation_9_hestia.md) を参照。`scripts/evaluate_9_hestia.py` で生成、前処理、頻度対照、LLM予算表示／抽出、採点を順に実行する。共通の平滑化設定は使わず、実験計画の設定を使う。API許可は既定OFF。評価9の一括実行は既存出力があっても各前段をCLIへ渡してhash検証・再利用する。結果は `results/9_hestia/<実験名>/evaluation9_summary.csv` と `.json`。

設定画面の **3住宅のつながり** では、compact / corridor / branched の部屋と接続を横並びで確認できる。線のラベルはHestiaが生成するドアセンサーIDと移動時間を表す。base / large variability は住宅構造を変えず、行動の揺らぎだけを変える。

## Hestia Studio

上部の **Hestia Studio** タブはStreamlit Components v2として同じページ内に直接描画される。Studio用サーバー、別ポート、iframe、起動・停止操作はない。Studio内の住宅タブで compact / corridor / branched の評価9 base住宅を切り替える。3住宅は初期データとして先読みされ、住宅ごとの未保存編集はページを開いている間保持される。ブラウザまたはStreamlitページを再読み込みする前にはYAML保存する。

部屋・デバイスのドラッグ、リサイズ、入力途中の更新はJavaScript側で処理する。Pythonへ同期するのは、少し間を置いた編集状態の保存と、検証・読込・保存・export・シミュレーション実行の明示操作だけである。これらの操作はHTTP APIを経由せず、Hestiaの共通`StudioService`から既存の`Scenario`、`load_scenario`、`SimulationEngine`を直接呼び出す。

Studio内では、部屋のドラッグ・リサイズ、接続の追加・削除と移動時間、センサー／デバイスの追加・削除・所属部屋・表示位置を編集できる。所属部屋や種類はシミュレーション設定、部屋内のアイコン座標は表示専用の `editor_layout` である。編集内容はStudio上部の **YAML保存** から `Hestia/scenarios/` に保存する。

間取り画面の **論文用SVG** / **論文用PNG** から、現在の住宅を白背景の図として保存できる。図には部屋、接続、移動時間、ドアセンサーID、センサー／デバイスID、凡例を含み、ホーム設定の表示名を図タイトルに使う。SVGは拡大可能なベクター、PNGは3200 × 2000 pxである。図は論文で住宅構造を説明するための可視化であり、評価9のground truthや検出器入力ではない。

Studio保存ファイルは通常のHestiaカスタムシナリオであり、評価9の `noise_free.yaml` やexperiment生成処理へ自動的には組み込まれない。評価9の研究条件・gold・train/test分離を意図せず変更しないための分離である。シミュレーション結果は従来どおり `Hestia/outputs/studio/<run-name>/` に保存し、同名出力を上書きしない。
