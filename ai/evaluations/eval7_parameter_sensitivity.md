# 評価7: K/h感度分析と上位条件反復（AI向け詳細）

**正本:** [docs/evaluations/evaluation_7_parameter_sensitivity_adl_interpretation.md](../../docs/evaluations/evaluation_7_parameter_sensitivity_adl_interpretation.md)
**CLI / 実装 / テスト:** `scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py`, `scripts/run_evaluation7_top_condition_repeats.py` → `src/behavior_pattern_mining/evaluation/evaluation7_staged.py` と評価6集合指標 → `tests/test_evaluation7_parameter_sensitivity.py`, `tests/test_evaluation7_staged_workflow.py`

## 目的と指標

提案手法**のみ**について、代表状態数Kとハミング距離hの組を変え、ADL解釈ラベル集合の正確さを比較して最適条件を選ぶ。LLM単独baselineとの比較は評価6の責務である。

set評価、許可10語彙、`missing`/`unknown`、time-bandの半開区間・境界横断除外、conditional/end-to-endの分母は評価6と同一である。Exact Set Match、Jaccard、multi-label Precision/Recall/F1、coverage、各状態率を条件ごとに出す。旧`mean_*`はend-to-endの別名。

既定の選択指標は`mean_multilabel_f1`（end-to-end F1）。同点ならend-to-end Jaccard、Accuracy、K、hの順に安定順位付けする。conditionalは表示するが、既定の選択には使わない。`rank=1`とsummary JSONの`best_condition`が選択結果である。

## 入力条件と前段

各(K,h,days)について、提案LLM JSONと、同じ状態定義を固定して全220日へ写像したstate seriesが必要である。`--days 30`はネットワーク構築・LLM入力の先頭30日を表し、ADL集合照合は220日で行う。

| 区分 | 条件 |
|---|---|
| CLI単一既定 | K=15, h=1, days=30, run 1。state seriesはlegacy `output/6_adl_evaluation_30/state_series.csv` |
| 正式screening | 指定したK×h直積、days=30、run 1、条件別state series |
| 正式top条件 | screening上位10だけ、run 1〜5、`top10_5runs/`へ分離 |

異なる条件のstate seriesを再利用しない。前段`evaluate_adl_labels.py --write-state-series`は現行ではevent-driven既定であり、抽出側との差は **KI-06**。評価5/6とのh=0/h=1不一致は **KI-01**。未生成条件は既定ではエラーで、探索だけ先に確認する時だけ`--skip-missing-conditions`を明示する。

LLM JSON/checkpointは`results/<model>/aruba_{K}_{h}_{days}days/`、screening・manifest・run集計は`results/<model>/7_param_search/`に保存する。state series/networkはモデル非依存で`output/`/`picture/`に残る。モデルをまたいでstaged repeatの完了JSONを探索してはならない。

## 標準の二段階ワークフロー

1. 全K/h条件の状態表・network、run 1のproposed JSON、条件別state seriesを用意する。
2. `evaluate_7_parameter_sensitivity_adl_interpretation.py`をrun 1で実行し、`evaluation7_condition_summary.csv`を作る。
3. `run_evaluation7_top_condition_repeats.py`が順位上位10をmanifestへ固定し、存在しないrun 2〜5だけ生成する。既存runを再生成しない。
4. `--conditions-file`でmanifestの条件ペアだけを、`--run-ids 1 2 3 4 5`で最終評価し、5回平均・標本標準偏差で再順位付けする。

典型のscreeningは `--n-states-list 10,15,20,25,30,35,40 --hamming-thresholds 0,1,2,3 --days 30 --runs 1 --min-overlap-ratio-for-true-label 0.10 --selection-metric mean_multilabel_f1`。最終出力先をscreeningと同じにせず`results/<model>/7_param_search/top10_5runs/`へ分ける。

反復生成と最終評価の完全な呼出し形は次のとおり。manifestにある条件以外を最終評価へ混ぜない。

```bash
uv run python scripts/run_evaluation7_top_condition_repeats.py \
  --screening-summary results/<model>/7_param_search/evaluation7_condition_summary.csv \
  --manifest results/<model>/7_param_search/evaluation7_top10_5runs_conditions.csv \
  --top-n 10 --total-runs 5 --days 30

uv run python scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py \
  --conditions-file results/<model>/7_param_search/evaluation7_top10_5runs_conditions.csv \
  --condition-summary-copy results/<model>/7_param_search/evaluation7_top10_5runs_conditions.csv \
  --run-ids 1 2 3 4 5 --days 30 \
  --labeled-casas new_labeled_data/aruba.txt \
  --output-dir results/<model>/7_param_search/top10_5runs \
  --selection-metric mean_multilabel_f1
```

## 成果物とWeb

出力は条件summary、run別summary、pattern detail、予測/真値/time-band別集計、`evaluation7_summary.json`。manifestはrun 2〜5生成直後はscreening指標を保持し、最終評価後はtop10_5runsの5回平均・標準偏差・順位へ更新する。

全ファイル名は`evaluation7_condition_summary.csv`、`evaluation7_condition_summary_by_run.csv`、`evaluation7_pattern_set_details.csv`、`evaluation7_by_pred_label.csv`、`evaluation7_by_true_label.csv`、`evaluation7_by_time_band.csv`、`evaluation7_summary.json`である。summary JSONには閾値、skip条件、最適条件、出力一覧を保存する。

Streamlitの評価7は既存CLIを順に呼ぶ薄い画面で、既定の二段階実行は「ネットワーク→全条件run1→state series→screening→top10の不足run→最終5run集計」。初回summaryがあれば前4段をスキップし、個別ボタンではファイル存在を確認する。アプリへ集合評価を重複実装しない。

## 守る契約

- 後半の評価結果でK/hを選び直して未使用性能とは呼ばない（感度分析の選択であることを維持）。
- custom `patterns-template`は従来の一括run評価用。staged repeatは標準のモデル別命名を使う。
- 予測語彙外をOtherへ変換せずunknownとして0点、time-band境界横断を含めず、欠損run・条件の扱いをsummaryに残す。
