# Pipeline

## 1. Raw sensor log loading

- 入力: `data/{DATASET_NAME}.csv`
- 出力: `timestamp`, `sensor_id`, `value`, `binary_value` を持つイベントDataFrame
- 対応ファイル: `src/behavior_pattern_mining/visualization/state_transition_visualizer.py`, `src/behavior_pattern_mining/baselines/frequency.py`, `src/behavior_pattern_mining/llm/direct_log_extractor.py`
- 役割: 4列イベントログまたはセンサー列CSVを読み、時刻順のセンサーイベントへ正規化する。

評価4でラベル付きArubaだけを使う場合は、`scripts/run_build_network_from_labeled_casas.py` が `new_labeled_data/aruba.txt` からセンサーイベントを抽出し、`configs/aruba_sensor_map.json` でセンサーIDを代表状態テーブルの列名へ変換して同じ後続処理へ渡す。

## 2. Preprocessing

- 入力: イベントDataFrame
- 出力: 1秒粒度の状態ベクトルDataFrame、連続同一状態を圧縮した状態ベクトル
- 対応ファイル: `src/behavior_pattern_mining/visualization/state_transition_visualizer.py`, `scripts/run_build_network_from_labeled_casas.py`
- 役割: Sample-and-Holdで各センサーのON/OFF状態を生成し、遅延OFF窓幅5秒でスムージングし、連続する同一状態を圧縮する。

## 3. Representative state extraction / mapping

- 入力: 圧縮済み状態ベクトル
- 出力: 代表状態リスト、`state/*.txt`、代表状態ラベル列
- 対応ファイル: `src/behavior_pattern_mining/visualization/state_transition_visualizer.py`, `src/behavior_pattern_mining/states/state_mapping.py`, `src/behavior_pattern_mining/baselines/frequency.py`, `src/behavior_pattern_mining/llm/direct_log_extractor.py`
- 役割: 出現頻度上位K個を代表状態にし、未知状態をハミング距離閾値以下なら最近傍代表状態へ、超過なら「その他」へ写像する。

## 4. Transition network construction

- 入力: 代表状態ラベル列
- 出力: 遷移確率行列、`picture/*/state_transition_all.json`, `picture/*/state_transition_{mode}.json`
- 対応ファイル: `src/behavior_pattern_mining/visualization/state_transition_visualizer.py`
- 役割: 自己連続遷移を圧縮し、状態ごとの遷移回数を確率化する。必要に応じてMorning/Daytime/Night/Midnightに分割する。

## 5. LLM-based pattern extraction

- 入力: モード別状態遷移JSON、または代表状態時系列、`.env` の `GEMINI_API_KEY`
- 出力: `output/*/llm_sequences_modes_*.json`, `output/llm_direct_*/*.json`, token metrics CSV
- 対応ファイル: `src/behavior_pattern_mining/llm/pattern_extractor.py`, `src/behavior_pattern_mining/llm/direct_log_extractor.py`, `src/behavior_pattern_mining/llm/client.py`
- 役割: Geminiへ状態遷移ネットワークまたは状態時系列を入力し、生活行動パターンのJSON配列を生成する。

## 6. Baseline methods

- 入力: モード別状態遷移JSON、状態定義TSV、元ログ
- 出力: `prob_threshold_sequences_*.json`, `state_sequence_counts_*.json`, association output CSV
- 対応ファイル: `src/behavior_pattern_mining/baselines/transition_probability.py`, `src/behavior_pattern_mining/baselines/frequency.py`
- 役割: 遷移確率0.2以上のパス列挙、状態列の頻度カウント、探索的なApriori/FP-Growth/n-gramを提供する。

## 7. Evaluation

- 入力: LLM出力JSON、ベースラインJSON、状態遷移JSON
- 出力: evaluation report TXT、Excel、groundedness CSV、condition summary JSON、ADL評価CSV/JSON
- 対応ファイル: `src/behavior_pattern_mining/evaluation/compare_patterns.py`, `src/behavior_pattern_mining/evaluation/direct_log.py`, `src/behavior_pattern_mining/evaluation/groundedness_check.py`, `src/behavior_pattern_mining/evaluation/condition_metrics.py`, `scripts/evaluate_adl_labels.py`, `scripts/evaluate_adl_correspondence.py`, `src/behavior_pattern_mining/evaluation/metrics.py`
- 役割: Precision/Recall/F1、Groundedness、support/confidence/interval条件、ラベル付きCASAS ADL区間に基づく評価を行う。

## 7.1 評価4: ADL label evaluation

- 入力: `new_labeled_data/aruba.txt`, `configs/aruba_sensor_map.json`, `--state-series` または `state/*.txt`, LLMパターンJSON
- 出力: `results/4_adl_detect/pattern_occurrences.csv`, `pattern_adl_mapping.csv`, `merged_predictions.csv`, `filtered_predictions.csv`, `adl_metrics_iou_*.csv`, `boundary_metrics_iou_*.csv`, `adl_interval_hit_metrics.csv`, `adl_interval_hit_details.csv`, `evaluation_summary.json`
- 対応ファイル: `scripts/evaluate_adl_labels.py`, `src/behavior_pattern_mining/evaluation/adl.py`
- 役割: LLM抽出系列を代表状態系列上で検索し、ADLラベル区間との重なりからpattern->ADL対応を行う。さらに同一ADLの近接予測マージ、短時間予測除外を適用し、カテゴリ別Precision/Recall/F1、開始/終了境界誤差、ADL区間内hitを評価する。

## 7.2 評価5: Useful non-redundant pattern / fragmentation evaluation

- 入力: `new_labeled_data/aruba.txt`, `--state-series`, frequency/rule/proposed のパターンCSVまたはJSON
- 出力: `results/5_pattern_quality/evaluation5_pattern_details.csv`, `evaluation5_summary_by_method.csv`, `evaluation5_summary.json`
- 対応ファイル: `scripts/evaluate_adl_correspondence.py`, `src/behavior_pattern_mining/evaluation/adl.py`, `src/behavior_pattern_mining/evaluation/adl_correspondence.py`
- 役割: train期間でpattern->ADL集合を決め、test期間で各出力パターンがADL-groundedか、生活文脈のない系列か、長い系列の断片かを評価する。比較対象はfrequency、rule-filtered frequency、FP-Growth系baseline、transition_probability baseline、提案手法。主指標は `useful_non_redundant_pattern_rate`, `fragmentation_rate`, `contextless_useless_rate` の3つ。`--runs` で提案手法の複数run平均も出せる。

## 7.3 評価6: LLM ADL interpretation set match

- 入力: `output/aruba_15_1_30days/llm_sequences_modes_15_1_30days_1.json`, `output/llm_direct_15_1_30days/1.json`, `output/6_adl_evaluation_30/state_series.csv`, `new_labeled_data/aruba.txt`
- 出力: `results/6_adl_match/15_1_30days/evaluation6_method_comparison.csv`, `evaluation6_method_comparison_by_run.csv`, `evaluation6_pattern_set_details_by_method.csv`, `evaluation6_by_time_band_by_method.csv`, `evaluation6_comparison_summary.json`
- 対応ファイル: `scripts/evaluate_6_compare_adl_interpretation_set.py`, `src/behavior_pattern_mining/evaluation/adl_interpretation_set.py`
- 役割: LLMが `ADL系列ラベル` として付けた解釈ラベル集合と、パターン出現区間がCASAS ADL区間と重なって得られる正解ADL集合を、順序を無視したset評価で比較する。提案手法は `sequence × time_band` 単位へ展開し、対象時間帯の出現だけで評価する。提案手法とLLM単独ベースラインの比較では、両手法を30日版に揃える。`--runs` で複数回実行結果の平均を出せる。

## 7.5 評価8: Frequency-stratified ADL consistency

- 入力: 30日手法比較では評価6の `evaluation6_pattern_set_details_by_method.csv`、154日提案手法単独では提案手法JSON・154日state series・ADL正解データ。
- 出力: `results/8_vs_llm/` と `results/8_proposed/` に保存する。後者は単一methodなので重複する `evaluation8_by_frequency_band_by_method.csv` を出力しない。
- 対応ファイル: `scripts/evaluate_8_frequency_stratified_adl_consistency.py`。
- 役割: 評価6のパターン単位set指標を、`num_occurrences` のmethod内三分位（Low / Middle / High）で後段集計する。time-band awareな提案手法レコードは `sequence × time_band` ごとの出現回数を使う。

## 8. Visualization

- 入力: 遷移確率行列、状態滞在時間、代表状態列
- 出力: `picture/*/state_transition_*.png`, `.eps`, `timeline_*.png`, `.eps`
- 対応ファイル: `src/behavior_pattern_mining/visualization/state_transition_visualizer.py`
- 役割: NetworkXで状態遷移グラフを描画し、代表状態タイムラインをヒートマップとして保存する。
