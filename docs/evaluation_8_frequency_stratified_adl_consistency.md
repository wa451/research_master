# 評価8: 頻度帯別ADL整合性評価

## 目的

評価8は評価6のADL解釈ラベルset一致指標を置き換えない後段分析である。抽出済みパターンを代表状態系列上の出現回数でLow / Middle / Highに分け、高頻度パターンほどADLラベル整合性が安定するかを確認する。頻度が高いこと自体は有用性の十分条件として扱わない。

## 実行条件と入力

評価8は次の2条件を別々に実行・保存する。両者を同じCSVや出力ディレクトリへ混在させない。

| 条件 | scope | 入力 | 出力先 |
|---|---|---|---|
| 14日・手法比較 | `comparison_14days` | 評価6のproposed / direct-log詳細CSV | `results/8_vs_llm_own_id_fixed/` |
| 154日・提案手法のみ | `proposed_154days` | 154日提案手法JSON 5 run、抽出時と同じ前処理で生成したstate series、ADL正解データ | `results/8_proposed_own_id_fixed/` |

### 14日・手法比較

更新後の評価6詳細CSVを使う。

| 入力 | 役割 |
|---|---|
| `evaluation6_pattern_set_details_by_method.csv` | proposed / direct-log baselineを比較する詳細CSV。 |
| `evaluation6_pattern_set_details.csv` | 単一手法の詳細CSVとしても利用可能。 |

評価6詳細CSVに保存された旧 `num_occurrences` は監査用の
`num_occurrences_before_fix` として保持する。ただし、旧値の有無にかかわらず、
評価8の正式な出現数は毎回state seriesから再構築する。各method・run内で
`eval_pattern_id` ごとに系列を検索し、そのIDで得た出現だけを使用する。
系列一致によって別IDの出現を取得するfallbackは使用しない。

提案手法のtime-band awareレコードは `sequence × time_band` を評価単位とし、
別時間帯の出現を混ぜない。comparison scopeでは、同じディレクトリの
`evaluation6_comparison_summary.json` または `evaluation6_summary.json` から
`state_series`、`match_mode`、skip条件を読む。summaryにstate seriesがない場合は
`--state-series` を明示する。旧詳細CSVに `num_occurrences` が存在していても、
state seriesを特定できなければ停止する。

### 154日・提案手法のみ

`--analysis-scope proposed_154days` では、評価6と同じADLラベルset一致処理を提案手法だけに5 run実行し、各runで独立に頻度三分位を割り当てた後、帯別指標をrun平均する。LLM単独ベースラインは入力にも出力にも含めない。標準入力は次の通り。

| 入力 | 既定例 |
|---|---|
| 提案手法JSON | `output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json` |
| state series | `output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv` |
| ADL正解データ | `new_labeled_data/aruba.txt` |

`proposed_154days` では、state series全体を無条件には使用しない。state seriesの
最初の日の00:00を開始時刻とし、`--days` 日後をexclusive endとする半開区間へ、
state intervalとADL intervalの双方をclipする。`--days`を省略した場合は154日である。
summaryには元とclip後のinterval件数、開始時刻、exclusive endを保存する。

## 出現数の正式定義と監査

一つの評価レコード \(p\) について、まず同じ `eval_pattern_id` を持つ出現を取得する。
time-band awareレコードでは、開始時刻と `end-\epsilon` がともに指定時間帯に属し、
半開区間 `[start,end)` 全体がその時間帯へ収まる出現だけを採用する。
境界を横断する出現は除外し、件数と割合を保存する。これは評価5・6と同じ定義である。
取得した出現は次のキーでレコード内一意化する。

```text
(run, occurrence startのtime_band, occurrence start, occurrence end, state sequence)
```

`PatternOccurrence`自体はrunを持たないため、runは評価ループから付与する。
物理キー中の時間帯は評価6と同じ境界関数を用いて開始時刻から算出する。
ただし、採否判定は開始時刻だけではなく区間全体の包含条件を使う。
`pattern_id`は一意化キーに含めない。同一ID内で同じ物理区間が重複しても
1回だけ数えるためである。

正式な `num_occurrences` と `num_occurrences_corrected` は、この一意化後件数である。
`num_occurrences_difference` は
`corrected - before_fix` と定義するため、旧値が過大だった場合は負になる。
`duplicate_occurrences_removed` は旧値から正式値への減少量
`max(before_fix - corrected, 0)`、`own_id_duplicate_occurrences_removed` は
own-ID取得後のレコード内物理重複除去数である。`fallback_used`は常に0である。

同じ物理キーが別IDにも割り当てられる場合は、
method・run内で `eval_pattern_id` の辞書順が最小のIDをstable ownerとする。
ownerだけがその物理区間を正式件数と頻度加重へ使用し、非ownerから除く。
これにより同じ物理区間の重みはmethod・run内で合計1となる。
`cross_id_shared_physical_occurrences`はownership適用前の共有件数、
`cross_id_occurrences_removed`は非ownerから除いた件数である。
ownership方針と共有・除去件数はsummaryにも保存する。

## 頻度帯の定義

既定の `tertile` は次の手順である。

1. methodおよびrunごとに評価レコードを分ける。
2. `num_occurrences` 昇順、続いて `eval_pattern_id` などの識別子で安定ソートする。
3. できるだけ同数になるようLow、Middle、Highへ割り当てる。

同じ出現数が境界にある場合も同値を一括して同じ帯には置かず、
安定ソート後のID順で分割する。これにより各runの帯のレコード数を
できるだけ同数にし、再実行時の割当てを決定的にする。
3件未満では、Lowから順に可能な帯だけが作られる。

154日・提案手法のみでは、三分位とは別に固定回数帯を使う `fixed` モードも利用できる。既定の境界は `0,1,10,100,1000,10000` で、次の範囲になる。境界は `--fixed-frequency-bin-edges` で変更でき、すべてのrunで同じ範囲を使う。

固定回数帯にパターンがないrunも、帯別run CSVへ
`evaluation_status=empty_band`、件数0として出力する。全run集計では
件数・総出現数の平均と標準偏差にこの0を含める。一方、出現数分布と
ADL集合指標は空帯では定義できないため、パターンが存在するrunだけで
平均し、その数を `num_runs_with_patterns` に保存する。これにより、
固定帯のCSVとパターン数図は同じ全run分母を用いる。

| frequency_band | num_occurrences の範囲 |
|---|---:|
| `0` | 0回 |
| `1-9` | 1–9回 |
| `10-99` | 10–99回 |
| `100-999` | 100–999回 |
| `1000-9999` | 1,000–9,999回 |
| `10000+` | 10,000回以上 |

固定帯は、各帯に含まれるパターン数の分布と、帯別Precision / Recall / F1の変化を可視化するための分析軸である。空の帯もCSVへ件数0の行を作り、分布図でも0件として表示する。頻度が高いことだけでパターンの有用性を結論付けない。

`both` モードは入力評価を一度だけ実行し、その同じ評価レコードから `tertile` と `fixed` を続けて集計する。出力の上書きを避けるため、指定した `--output-dir` の下に `tertile/` と `fixed/` を作る。Streamlitアプリは選択式ではなく、常にこの `both` モードを使う。

## 出力

| ファイル | 内容 |
|---|---|
| `evaluation8_frequency_band_details.csv` | 評価6の詳細に修正前・修正後出現数、差分、fallback、重複監査、頻度帯を加えたレコード単位出力。 |
| `evaluation8_by_frequency_band.csv` | 頻度帯別の全run平均・標本標準偏差。 |
| `evaluation8_by_frequency_band_by_method.csv` | 14日・手法比較だけで出力するmethod × frequency band別集計。提案手法のみでは重複するため出力しない。 |
| `evaluation8_by_frequency_band_by_run.csv` | method × run × frequency bandの集計。 |
| `evaluation8_occurrence_weighted_summary.csv` | methodごとの全体occurrence-weighted指標のrun平均・標本標準偏差。 |
| `evaluation8_summary.json` | 入力、有効期間、ID・一意化方針、tie方針、run別結果、平均、重み総和検証を記録する再現用summary。 |
| `evaluation8_frequency_distribution.png` | 154日・提案手法のみの固定帯モードで出力する、帯別の平均パターン数分布。 |
| `evaluation8_frequency_band_metrics.png` | 154日・提案手法のみの固定帯モードで出力する、帯別平均Precision / Recall / F1。 |

各頻度帯では、評価レコード数、conditional/end-to-end評価可能数、
`no_occurrence`, `no_adl_overlap`, `missing`, `unknown` の件数と割合、
coverage、境界横断件数、修正後出現数の総和・範囲・平均・中央値、
pattern単位のconditional/end-to-end Exact Set Match / Jaccard /
multi-label Precision / Recall / F1を出力する。従来の `mean_*` は
end-to-endの別名である。修正後出現数で重み付けした
Jaccard / Precision / Recall / F1も、正解未定義の `no_adl_overlap`
を除くend-to-end対象に対して計算する。end-to-end対象または正の
出現重みがない帯では、頻度加重指標を0とせず空欄（N/A）にする。
`num_evaluable_patterns` は後方互換のend-to-end件数であり、
明示列 `num_end_to_end_evaluable_patterns` と同値である。

複数runでは、まず各run内で頻度帯を割り当てて指標を計算する。
`evaluation8_by_frequency_band_by_run.csv`にその値を保存し、その後、
各runを等しい重みで平均する。集計CSVの `num_patterns`、
`num_evaluable_patterns`、`total_occurrences`、各指標はrun平均であり、
対応する `std_*` はrun間の標本標準偏差である。
`min_occurrences`と`max_occurrences`は、当該帯へ属した全runの評価レコードに
おける最小値と最大値である。

summaryの `occurrence_weight_validation` はmethod・runごとに、
頻度加重で用いた重み総和、`num_occurrences_corrected` の合計、
ownership前の物理キー集合の一意件数が一致するかを検証する。
正式結果では `all_passed=true` でなければならない。

## 実行方法

### 14日・手法比較

```bash
uv run python scripts/evaluate_8_frequency_stratified_adl_consistency.py \
  --analysis-scope comparison_14days \
  --evaluation6-details results/6_adl_match/15_0_14days/evaluation6_pattern_set_details_by_method.csv \
  --state-series output/6_adl_evaluation_15_0_14days/state_series.csv \
  --output-dir results/8_vs_llm_own_id_fixed \
  --frequency-band-mode tertile
```

### 154日・提案手法のみ（固定回数帯と図）

```bash
uv run python scripts/evaluate_8_frequency_stratified_adl_consistency.py \
  --analysis-scope proposed_154days \
  --patterns-proposed output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json \
  --state-series output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --n-states 15 \
  --hamming-threshold 0 \
  --days 154 \
  --runs 5 \
  --output-dir results/8_proposed_own_id_fixed \
  --frequency-band-mode fixed \
  --fixed-frequency-bin-edges 0,1,10,100,1000,10000
```

図を保存しない場合は `--no-write-distribution-plots` を指定する。

### 154日・提案手法のみ（三分位と固定回数帯を同時実行）

```bash
uv run python scripts/evaluate_8_frequency_stratified_adl_consistency.py \
  --analysis-scope proposed_154days \
  --patterns-proposed output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json \
  --state-series output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --runs 5 \
  --days 154 \
  --n-states 15 \
  --hamming-threshold 0 \
  --output-dir results/8_proposed_own_id_fixed \
  --frequency-band-mode both \
  --fixed-frequency-bin-edges 0,1,10,100,1000,10000
```

三分位の結果は `results/8_proposed_own_id_fixed/tertile/`、固定回数帯と図は `results/8_proposed_own_id_fixed/fixed/` に保存する。

### 154日・提案手法のみ

先に154日提案手法の `_1.json` から `_5.json` を生成する。

```bash
uv run python scripts/run_llm_extraction.py \
  --days 154 \
  --hamming-threshold 0 \
  --runs 5
```

```bash
uv run python scripts/evaluate_8_frequency_stratified_adl_consistency.py \
  --analysis-scope proposed_154days \
  --patterns-proposed output/aruba_15_0_154days/llm_sequences_modes_15_0_154days_1.json \
  --state-series output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv \
  --labeled-casas new_labeled_data/aruba.txt \
  --n-states 15 \
  --hamming-threshold 0 \
  --days 154 \
  --runs 5 \
  --output-dir results/8_proposed_own_id_fixed \
  --frequency-band-mode tertile
```

14日比較の結果は `evaluation8_by_frequency_band_by_method.csv`、154日提案手法のみの結果は `evaluation8_by_frequency_band.csv` でLow / Middle / Highの `conditional_mean_*` と `end_to_end_mean_*` を区別して比較する。後方互換列 `mean_multilabel_precision`, `mean_multilabel_recall`, `mean_multilabel_f1` はend-to-endを表す。高頻度帯のPrecisionが高いかは、その値を確認して判断し、頻度のみから有用性を結論付けない。
