# Pipeline

## 1. Raw sensor log loading

- 入力: `data/{DATASET_NAME}.csv`
- 出力: `timestamp`, `sensor_id`, `value`, `binary_value` を持つイベントDataFrame
- 対応ファイル: `src/behavior_pattern_mining/visualization/state_transition_visualizer.py`, `src/behavior_pattern_mining/baselines/frequency.py`, `src/behavior_pattern_mining/llm/direct_log_extractor.py`
- 役割: 4列イベントログまたはセンサー列CSVを読み、時刻順のセンサーイベントへ正規化する。

## 2. Preprocessing

- 入力: イベントDataFrame
- 出力: 1秒粒度の状態ベクトルDataFrame、連続同一状態を圧縮した状態ベクトル
- 対応ファイル: `src/behavior_pattern_mining/visualization/state_transition_visualizer.py`
- 役割: Sample-and-Holdで各センサーのON/OFF状態を生成し、遅延OFF窓幅180秒でスムージングし、連続する同一状態を圧縮する。

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
- 対応ファイル: `src/behavior_pattern_mining/evaluation/compare_patterns.py`, `src/behavior_pattern_mining/evaluation/direct_log.py`, `src/behavior_pattern_mining/evaluation/groundedness_check.py`, `src/behavior_pattern_mining/evaluation/condition_metrics.py`, `scripts/evaluate_adl_labels.py`, `src/behavior_pattern_mining/evaluation/metrics.py`
- 役割: Precision/Recall/F1、Groundedness、support/confidence/interval条件、ラベル付きCASAS ADL区間に基づく評価を行う。

## 7.1 ADL label evaluation

- 入力: `new_labeled_data/aruba.txt`, `data/aruba.csv` または `--state-series`, `state/*.txt`, LLMパターンJSON
- 出力: `results/adl_evaluation/pattern_occurrences.csv`, `pattern_adl_mapping.csv`, `adl_metrics_iou_*.csv`, `boundary_metrics_iou_*.csv`, `evaluation_summary.json`
- 対応ファイル: `scripts/evaluate_adl_labels.py`, `src/behavior_pattern_mining/evaluation/adl.py`
- 役割: LLM抽出系列を代表状態系列上で検索し、ADLラベル区間との重なりからpattern->ADL対応、カテゴリ別Precision/Recall/F1、開始/終了境界誤差を評価する。

## 8. Visualization

- 入力: 遷移確率行列、状態滞在時間、代表状態列
- 出力: `picture/*/state_transition_*.png`, `.eps`, `timeline_*.png`, `.eps`
- 対応ファイル: `src/behavior_pattern_mining/visualization/state_transition_visualizer.py`
- 役割: NetworkXで状態遷移グラフを描画し、代表状態タイムラインをヒートマップとして保存する。
