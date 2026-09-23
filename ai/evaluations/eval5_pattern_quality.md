# 評価5: パターン有用性・断片化・無文脈性（AI向け詳細）

**正本:** [docs/evaluations/evaluation_5_adl_correspondence.md](../../docs/evaluations/evaluation_5_adl_correspondence.md)
**CLI / 実装 / テスト:** `scripts/evaluate_adl_correspondence.py` → `src/behavior_pattern_mining/evaluation/adl_correspondence.py` → `tests/test_adl_correspondence.py`

## 目的と比較対象

train期間で各パターンへADL集合を割り当て、test期間でその対応が維持されるかを使って、パターン1件単位の品質を比較する。対象は `frequency`、`rule_light`、`rule_medium`、`rule_strong`、`fp_growth`、`fp_growth_filtered`、`transition_probability`、`proposed`。提案手法のLLM JSONだけがモデル依存で、baseline・state series・状態定義は共有入力である。

ここでの「Useful」は情報量の高さではない。ADLに支持され、構造的無意味でなく、長い系列の冗長な断片でないことを表す。

## 主指標の厳密な意味

評価可能パターンを分母とする（既定では`test_support=0`を除外）。

```text
useful_non_redundant = adl_grounded AND NOT structural_useless AND NOT fragmented
contextless_useless = structural_useless OR adl_unsupported
```

| 判定・率 | 定義 / 既定値 |
|---|---|
| Useful non-redundant pattern rate | `useful_non_redundant / evaluable` |
| Fragmentation rate | `fragmented / evaluable`。比較可能parentが0でも0（N/Aではない） |
| Contextless useless rate | `contextless_useless / evaluable` |
| `structural_useless` | `A→A`、`A→Other→A`、`A→B→A→B` を含む |
| `adl_unsupported` | testのany-ADL hit率 `<0.1` かつpurity `<0.1` |
| `adl_grounded` | hit率・purityが各`0.3`以上（CLI閾値） |
| `fragmented` | 同一method/run/time bandで短系列pが長系列qの連続部分列かつ、`q内のp出現数 / p出現数 >= 0.7` |

`low_information_ratio`はactive sensorが空、または明示Other等の状態の割合を残す**診断専用**である。Useful/Contextlessの真偽に使わない。互換列`is_low_information`と`num_low_information`は空欄、`--low-information-threshold`は受理するが無視する非推奨引数である。比較可能pair=0というFragmentation=0は、断片化を抑えた証拠ではない。

## 正解・split・ADL対応

- `new_labeled_data/aruba.txt`をmulti-label ADL区間に変換し、時系列順にtrain/testへ分割する（既定`--train-ratio 0.7`）。testで`assigned_adl_set_train`を再割当してはならない。
- trainでカテゴリ重なり時間/総継続時間が`0.10`以上のADLを候補にし、正の最大重なりADLは必ず含め、最大3カテゴリへ制限する。`Other_ADL`は非Otherが無い時だけ含める。
- `Sleeping→Sleep`、`Bed_to_Toilet→Wake-up+Toileting`、`Bathroom/Personal_Hygiene→Wake-up+Hygiene`、`Bathing→Hygiene`、`Wash_Dishes→Meal+Housework`、`Leave/Enter_Home→Outing`、`Housekeeping→Housework`、未知は`Other_ADL`。Sleeping終了後30分はWake-up補正を保持し得る。
- time-bandを持つレコードは半開区間`[start,end)`の開始と`end-ε`が同じ時間帯にある出現のみ使う。境界横断を混ぜない。

## 入力・標準条件・保存先

正式条件はK=15、h=0、代表状態のtrain作成154日、評価用state series 220日、network-equivalent・平滑化5秒である。`evaluate_adl_labels.py --state-series-only`により、**154日で作った状態表を再抽出せず固定して**220日を写像する。event-drivenの別再構築CSVを正式評価に使わない。

| 入力 | 役割 |
|---|---|
| `state/aruba_15_0_154days.txt` またはnetwork JSON | state IDのactive sensors解決。どちらか必須、解決不能なら推測せずエラー |
| `output/5_adl_evaluation_15_0_154days_fixed/state_series_220days.csv` | 全手法共通の照合系列 |
| frequency / rule CSV | 明示指定がなければstate seriesから生成可能 |
| FP-Growth / transition | trainから生成。cacheは条件一致時のみ再利用 |
| proposed JSON | 現モデルの `results/<model>/aruba_15_0_154days/`。run 1〜5を評価可 |

新規出力は `results/<model>/5_pattern_quality_fixed/` がCLI既定である。一方、研究文書の正式再集計例は legacy 名の `results/5_pattern_quality_without_low_information_judgment/` を明示する。新規実行ではモデル名を含む出力先を使い、過去成果物を上書きしない。K/hのCLI既定との不一致は **KI-01**。

## 実行と成果物

canonical実行はstate series作成後、`evaluate_adl_correspondence.py`へ各入力、`--train-ratio 0.7`、上述の閾値、FP-Growth（support 0.05、top 50、len 2–4、median 1800秒/p90 3600秒）、transition（top 50、min-prob 0.0、len 2–4）、`--fragmentation-containment-threshold 0.7`を渡す。`--runs 5`ではbaselineは最初のrunだけ、proposedだけ全runを評価する。欠損runの許容は`--skip-missing-runs`を明示する。

主要成果物は`evaluation5_summary_by_method.csv`、必要時の`..._by_run.csv`、`evaluation5_pattern_details.csv`、`evaluation5_summary.json`。summaryでは分子・分母、比較可能pair/child数、系列長分布、run数、skipを確認する。detailsで各真偽、parent ID、`low_information_ratio`、`evaluation_status`を監査する。

## 守る契約

- frequency/FP-Growthは重いのでcacheのkeyとなるstate series・train期間・設定を変えたら別cacheを使う。
- FP-Growthは日付×時間帯transactionの連続n-gram。transition baselineはtrain隣接遷移の条件付き確率の積で経路を順位付けする。baseline定義を比較評価の都合で変えない。
- old引数・空列、pair=0の0扱いは互換契約。詳細は`ai/DECISIONS.md`を参照する。
