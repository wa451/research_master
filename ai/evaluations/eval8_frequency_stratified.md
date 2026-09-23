# 評価8: 頻度帯別ADL整合性（AI向け詳細）

**正本:** [docs/evaluations/evaluation_8_frequency_stratified_adl_consistency.md](../../docs/evaluations/evaluation_8_frequency_stratified_adl_consistency.md)
**CLI / 実装 / テスト:** `scripts/evaluate_8_frequency_stratified_adl_consistency.py`（集計本体を含む）→ `tests/test_evaluation8_frequency_stratified.py`

## 目的とscope

評価6の集合一致を置換しない後段分析である。パターンをstate seriesでの**正式な出現回数**により頻度帯へ分け、頻度とADL解釈整合性の関係を調べる。高頻度は有用性の十分条件ではない。

| scope | 入力 | 標準出力 |
|---|---|---|
| `comparison_14days` | 評価6のproposed/direct details + state series | `results/<model>/8_vs_llm_own_id_fixed/` |
| `comparison_30days` | 過去の30日details。互換用、正式標準ではない | 14日と別の明示出力先 |
| `proposed_154days` | 154日proposed JSON（通常5 run）、state series、labeled CASAS | `results/<model>/8_proposed_own_id_fixed/` |

この評価は新しいLLM呼出しをしない。評価6detailsや154日proposed JSONは**現在モデル**の`results/<model>/`から読み、照合state seriesはモデル非依存の`output/`に残す。

## 出現数の正式契約（変更注意）

旧detailsの`num_occurrences`は`num_occurrences_before_fix`として監査用に残すだけで、正式値は常にstate seriesから再検索する。各method/runで同じ`eval_pattern_id`の系列だけを使う。系列一致による別IDのfallbackは禁止、`fallback_used`は常に0。

time-bandレコードは`[start,end)`全体が対象帯に収まる出現だけを使い、横断出現を除外・記録する。レコード内では `(run, occurrence開始帯, start, end, state sequence)`で物理区間を一意化し、`pattern_id`はキーに含めない。同一物理区間を別IDが共有したら、method/run内で辞書順最小の`eval_pattern_id`をstable ownerとし、ownerだけが頻度・重みへ使う。これで物理区間の全ID合計重みは1になる。

`num_occurrences_corrected`は一意化・ownership後の件数、差分は`corrected - before_fix`、`duplicate_occurrences_removed=max(before_fix-corrected,0)`。共有・除去数、own-ID重複除去数もsummaryへ保存する。`occurrence_weight_validation.all_passed`がtrueでなければ正式結果として扱わない。これは **KI-10** の対策なのでrollback・fallback復活をしない。

## 頻度帯と採点

- `tertile`: method/runごとに`num_occurrences`昇順、同率はIDで安定ソートし、Low/Middle/Highへ可能な限り等数分割。同値を同じ帯へまとめない。3件未満はLowから作る。
- `fixed`: 154日proposedのみで使える。既定edge `0,1,10,100,1000,10000`から`0`, `1-9`, `10-99`, `100-999`, `1000-9999`, `10000+`。空帯も0件行を出す。
- `both`: 同じ入力評価からtertileとfixedを続け、指定出力下の`tertile/`と`fixed/`へ分離。Streamlitは常にboth。
- conditional/end-to-endの集合採点、`no_occurrence/no_adl_overlap/missing/unknown`の扱いは評価6と同じ。旧`mean_*`はend-to-end。頻度加重指標は正解未定義`no_adl_overlap`を除くend-to-end対象で、対象または正の重みが無い帯は0でなくN/A。
- 複数runでは各run内で帯を作ってからrun等重み平均。fixedの空帯はpattern数・総出現数の平均には0として含めるが、集合指標はpatternを持つrunだけで平均し`num_runs_with_patterns`を保存する。

154日scopeでは、state seriesの最初の00:00から`--days`（既定154）後exclusive endまでを、state/ADL両intervalでclipする。入力series全体を無条件に使わない。summaryにclip前後件数・開始・exclusive endを記録する。

## 入出力と実行例

主要成果物は`evaluation8_frequency_band_details.csv`、`evaluation8_by_frequency_band.csv`、comparison時の`evaluation8_by_frequency_band_by_method.csv`、`evaluation8_by_frequency_band_by_run.csv`、`evaluation8_occurrence_weighted_summary.csv`、`evaluation8_summary.json`である。154日fixedでは`evaluation8_frequency_distribution.png`と`evaluation8_frequency_band_metrics.png`も作る。detailsは修正前/後出現数、差分、fallback、重複監査、頻度帯を持つ。summaryは有効期間、ID/一意化/ownership/tie方針、run別値、重み総和検証を持つ。14日比較の典型は次のとおり。

```bash
uv run python scripts/evaluate_8_frequency_stratified_adl_consistency.py \
  --analysis-scope comparison_14days \
  --evaluation6-details results/<model>/6_adl_match/15_0_14days/evaluation6_pattern_set_details_by_method.csv \
  --state-series output/6_adl_evaluation_15_0_14days/state_series.csv \
  --output-dir results/<model>/8_vs_llm_own_id_fixed \
  --frequency-band-mode tertile
```

154日proposedでは`--runs 5 --days 154 --n-states 15 --hamming-threshold 0`と、抽出時と同じstate seriesを明示する。30日scopeは入力期間を自動検証しないため、input summary・パスで30日であることを確認し、14日出力を上書きしない。

154日固定帯の完全な呼出しは、`--analysis-scope proposed_154days`、`--patterns-proposed results/<model>/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json`、`--state-series output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv`、`--labeled-casas new_labeled_data/aruba.txt`、`--frequency-band-mode fixed --fixed-frequency-bin-edges 0,1,10,100,1000,10000`を指定する。図を不要にする場合だけ`--no-write-distribution-plots`を追加する。bothでは同じ出力先直下の`tertile/`と`fixed/`に分けられる。

## 解釈・変更時の注意

帯別CSVはpattern数、状態別数・率、coverage、境界横断、出現統計、pattern単位・出現重みの集合指標を持つ。Low/Middle/HighのPrecision等はその値で判断し、頻度だけから有用性を結論しない。eval6 detailsの列、own-ID取得、物理一意化、stable ownership、分母を変える変更は評価8の研究定義変更として扱い、テストと正本を更新する。
