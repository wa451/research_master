# 評価9: Hestia合成ログによる系列回収・ADL意味対応

## 概要

Hestiaで生成したセンサーログに提案手法（代表状態 → 状態遷移ネットワーク → LLM抽出）を適用し、生成時の正解を用いて系列回収とADLの意味対応を評価する。既存のHestia `experiment` 基盤をmaster-researchのCLIとWebアプリから実行する。評価1〜8の指標・前処理・データは変更しない。

本評価は制御された合成データ上の診断評価であり、実Arubaの性能値と混ぜて集計しない。HESTIA論文の公式実装の再現でもない。

## RQ

- 住宅構造と行動の揺らぎ（base / large variability）を変えたとき、代表状態に投影された反復系列をどの程度回収できるか。
- 抽出系列のADLラベル集合は、後半の正解活動区間とどの程度一致するか。
- 回収できない原因として、代表状態に含まれないOtherや活動の観測可能性がどの程度関係するか。

## 配置とセットアップ

Hestiaの実体は `master-research/Hestia/` に置かれ、`master-research` の親リポジトリでGit管理されている。親repoをcloneすれば、Hestiaのソース・設定・テスト・文書も同じ `Hestia/` 配下に取得される。
したがって、移動前の `/Users/wataru/Desktop/Hestia` は使用せず、別途Hestiaをcloneまたは配置する必要もない。Hestia単体のGit管理ではなく、親リポジトリの履歴として変更を記録する。

master-research直下で実行する。

```bash
uv sync
uv sync --project Hestia
uv run streamlit run app/streamlit_app.py
```

HestiaはPython 3.11以上を使う。依存環境はmaster-researchとHestiaで分離する。CLIは `uv run --project <Hestiaの絶対パス> --frozen smart-home-sim experiment ...` を呼び、Hestiaのworkerはmaster-researchの `.venv/bin/python` で既存研究コードを実行する。

仮想環境ごと手動移動した場合、実行スクリプトに旧絶対パスが残ることがある。その場合は `uv sync --project Hestia --reinstall` で修復する。

## 指標

採点ロジックと閾値は [Hestiaの評価仕様](../../Hestia/docs/noise_free_evaluation.md) を継承する。

| 指標 | 読み方 |
|---|---|
| `precision`, `recall`, `f1` | train target episodeから固定したcanonical goldと、抽出された一意な`(time_band, representative-state sequence)`のexact match。frequencyにも同じ定義を適用。 |
| `TP`, `FP`, `FN` | canonical goldを正とする一意な系列集合の件数。 |
| `fragmentation_rate` | gold canonicalのうち別canonicalではないproper contiguous subsequenceをpotentialとし、test出現の0.7以上が親target episode内に含まれる抽出fragment数をpotential総数で割る。 |
| `catalog_recall` | 前半の完了活動内で2活動区間以上に現れた、時間帯付き連続2〜4状態の正解catalogの回収率。生のtemplateそのものの回収率ではない。 |
| `test_visible_catalog_recall` | catalogのうち後半にも現れた系列に限定した回収率。 |
| `test_target_episode_coverage` | 後半の対象活動で、抽出したcatalog系列が少なくとも1回完全に含まれる活動の割合。 |
| `test_supported_pattern_fraction` | 抽出系列のうち後半に出現した割合。 |
| `train_other_duration_ratio`, `test_other_duration_ratio` | 固定した代表状態表に表現されない時間の割合。LLM以前の情報損失として読む。 |
| `adl_macro_f1` | 後半の正解活動のある時間領域で、家全体の複数ADLラベルを時間重なりで採点したmacro-F1。 |

CSVは各指標の `_mean`, `_std`, `_n_seeds` を持つ。seed内のLLM反復を平均した後にseed間で平均・標本標準偏差を計算する。1seedの標準偏差は空欄（JSONではnull）。欠落・invalid反復のあるseedは主集計から除外し、`expected_runs`, `complete_runs`, `missing_runs`, `invalid_runs`, `expected_seeds`, `complete_seeds` を併記する。

Primary goldはHestiaのtemplateそのものではない。正解activity episodeから生成されたセンサログを
research_masterと同じ前処理に通し、trainだけで作った代表状態表へ固定写像したepisode内系列から
作る。target・time bandごとにtrain episode support最大、次いで最長（2〜4）の候補をcanonicalとし、
同率は全て保持する。proper contiguous subsequenceはfragment候補として同じcatalog内で親IDを持つ。
testは固定写像、出現件数、採点にだけ使い、canonical選定、K、閾値、抽出へ戻さない。

抽出集合が空ならprecisionはnull、goldが空ならrecallはnull、両方空ならF1もnull、片方だけが空なら
F1は0とする。potential fragmentが1件以上あってemitted 0件ならfragmentation rateは0であり、
potential自体が0件のときだけN/Aである。`catalog_precision_diagnostic` は従来catalog用の診断値として
残し、Primary precisionと区別する。詳細JSONにはgold catalog、target episodeの実行経路・投影系列、
fragment包含率、活動観測可能件数、ADLのmicro・ラベル別指標も含む。

## 入力・出力

| パス（既定） | 内容 |
|---|---|
| `Hestia/examples/experiments/noise_free_pilot.yaml` | 4条件 × 1seed × 4日、LLM各1反復の動作確認計画。前半2日・後半2日。 |
| `Hestia/examples/experiments/controlled_gold_pilot.yaml` | 1人・2 target・4日・固定seed/揺らぎなしのAPI不要gold契約pilot。 |
| `Hestia/examples/experiments/noise_free.yaml` | 本実験。3住宅 × 2条件（base / large variability）× 3seed = 18ログ。各ログ14日（train 7日/test 7日）、LLM各3反復。 |
| `output/9_hestia/pilot/experiment.json` | 確定した計画snapshot。 |
| `output/9_hestia/pilot/runs/<condition>/seed_<seed>/` | 元ログ、正解、学習入力、代表状態・network、抽出結果、個別採点、再現用hash。 |
| `results/9_hestia/pilot/evaluation9_summary.csv` | 条件・手法別の集計。最初に読むファイル。 |
| `results/9_hestia/pilot/evaluation9_summary_runs.csv` | seed・LLM run・condition単位のstatusとPrimary指標。 |
| `results/9_hestia/pilot/evaluation9_summary.json` | `runs` にseed・反復別statusと指標、`summary` に集計を保存。 |
| `output/logs/evaluation_dashboard/` | Webのコマンド履歴と実行ログ。workerの詳細ログは各runの `runtime/`。 |

既にHestiaの `experiment generate` で作成した `experiment.json` と `runs/` のあるディレクトリも指定できる。生成を省いてprepare以降を個別実行する場合、以後の設定はそのディレクトリ内のsnapshotを使う。画面の計画ファイル指定はgenerateにだけ適用される。

Studioの `events.csv` / `casas_motion_door.txt` 単体には本評価が要求する計画・正解・train/test契約がないため、そのまま評価9へ投入することはできない。単体ログを従来の研究前処理に渡す手順は [Hestiaデータ統合](../integrations/hestia_dataset_integration.md) を参照する。

## Webアプリでの実行手順

1. 左サイドバーで **評価9** を選ぶ。
2. **3住宅のつながり** で compact / corridor / branched の部屋、接続、ドアセンサー、移動時間を確認し、計画、生成ログ・中間成果物ディレクトリ、集計先を設定する。base / large variability は同じ住宅構造を使う。既定はpilot。K・seed・日数・平滑化は計画ファイルで変更する。サイドバーの共通平滑化は評価9には適用しない。
3. 詳細な配置を確認・変更する場合は **Hestia Studio** タブでStudioを起動し、Studio内の compact / corridor / branched タブを切り替える。各住宅の未保存編集はページを開いている間保持される。編集は `Hestia/scenarios/` にYAML保存できるが、評価9の本実験planへは自動反映されない。**論文用SVG** / **論文用PNG** では部屋・接続・センサー／デバイス配置を論文向け画像として保存できる。この画像は住宅構造の説明用であり、ground truthや検出器入力には使用しない。
4. 必要なら共通の **dry-run** でコマンドだけ記録する。実処理・API呼出しは行わない。
5. **不足ファイル生成 + 評価本体** で一括実行する。API許可OFFでは、生成 → 前処理 → 頻度対照 → LLM予算表示 → 採点まで実行する。LLMはmissing、頻度対照は採点済みになる。
6. 提案手法も採点する場合は、ステップ4のモデル・呼出し数を確認し、**LLM抽出のAPI呼出しを許可** をONにしてステップ4を実行し、続いてステップ5を実行する。master-researchの既存認証設定を使う。
7. **結果比較** タブで `results/9_hestia/pilot` を選び、CSVとJSONを確認する。

評価9は一括実行の各前段を毎回CLIに渡して、既存成果物のhashを検証する。ファイルの存在だけで前段を飛ばさない。完了済みの生成・前処理・LLM反復は既存CLIが検証して再利用する。「全ステップを再実行」も強制上書きではない。計画・コードの変更や不完全な生成が検出された場合は停止するため、新しい実験ディレクトリと集計先を指定する。

「不足ファイル生成のみ」は採点以外を実行する。API許可ONなら、このモードにもLLM抽出が含まれる。

## CLIでの実行手順

### 0. controlled gold pilot（APIなし）

```bash
uv run python scripts/evaluate_9_hestia.py \
  --plan Hestia/examples/experiments/controlled_gold_pilot.yaml \
  --experiment output/9_hestia/controlled_gold_pilot \
  --output-dir results/9_hestia/controlled_gold_pilot \
  --method frequency
```

この実行は生成、train-only準備、frequency抽出、gold採点を行い、Gemini APIを呼ばない。

### 1. APIなしで全段階を確認

```bash
uv run python scripts/evaluate_9_hestia.py
```

コマンド確認のみの場合は `--dry-run` を追加する。このCLIのdry-runはファイルを一切書かない（Webのdry-runは履歴のみ保存する）。

### 2. 提案手法のLLM抽出と再採点

```bash
uv run python scripts/evaluate_9_hestia.py --stage budget
uv run python scripts/evaluate_9_hestia.py --stage extract --allow-api
uv run python scripts/evaluate_9_hestia.py --stage evaluate --method both
```

`--allow-api` はextractまたはrunだけで指定できる。extractも許可なしでは予算表示のみ。失敗した段階で後続を停止し、子プロセスの終了コードを返す。

### 3. 本実験用の別ディレクトリ

```bash
uv run python scripts/evaluate_9_hestia.py \
  --plan Hestia/examples/experiments/noise_free.yaml \
  --experiment output/9_hestia/full \
  --output-dir results/9_hestia/full
```

本実験の6 conditionは `compact_base`, `compact_variable`, `corridor_base`,
`corridor_variable`, `branched_base`, `branched_variable` である。baseは基準性能の確認、
large variability（`*_variable`）は開始時刻±45分、活動・step時間±30%という大きな揺らぎに
対する提案手法の頑健性確認のために採用する。2 residents / late / home / low / high / fixedは
Hestiaの汎用条件として維持するが、この本実験planには含めない。

このコマンドもAPIなし。本実験の新規モード抽出は全4時間帯がある場合最大216回で、通信・解析retryによってAPIリクエストが増える場合がある。続きの個別ステップでも同じ `--experiment` と `--output-dir` を指定する。

## 比較と内部処理

- 提案手法の状態抽出・写像・ネットワーク・LLMはmaster-researchの既存実装を呼ぶ。
- `frequency` は前半の連続2〜4状態、最低support=2、頻度上位20件の動作確認用対照。既存研究の頻度baselineとは別定義。ADL予測は行わず、ADL指標はnull。
- 検出器には正解ラベルや住人IDを渡さない。代表状態・ネットワーク・頻度対照は前半だけで構築し、後半はその状態表に固定して写像する。
- planの`targets`はtarget ID、activity、resident、time band、各日に繰り返す開始予定時刻列を持つ。未指定planは従来スケジュールと互換。target指定時も既存routine/activity/micro-templateとconditionの揺らぎを使う。
- 複数住人の正解活動は住人・活動IDで保持し、採点は家全体の複数ラベルとして行う。住人識別精度ではない。
- 欠落LLMを0点扱いしない。APIなしでコマンドが成功しても、提案手法の評価完了を意味しない。

## パラメータと注意点

pilotの既定はK=15、h=0、平滑化0秒、観測ノイズなし、seed=11。既存評価の平滑化5秒やevent-driven既定とは独立した研究条件である。[既知の不一致 KI-06・07](../research/known_issues.md) を既存評価側で解消する変更は行っていない。

後半の結果を見てKや閾値を調整した成績を、未使用testの性能として報告しない。pilotの1seedから統計的結論を出さない。詳細な条件、catalogの境界条件、missing集計、制約は [Hestia評価仕様](../../Hestia/docs/noise_free_evaluation.md) を参照する。
