# 評価9: Hestia合成ログによる系列回収・ADL意味対応

> **モデル別保存:** `experiment.json`、生成ログ、truth、prepared state/networkは従来どおり `output/<model>/9_hestia/` に置く。LLM JSON・mode checkpoint・usage・LLM個別採点は `results/<model>/9_hestia/<experiment>/artifacts/`、集計は同experiment直下へ保存する。Hestia CLIにはmodel-specific artifact rootが自動で渡され、別モデルのcomplete markerを参照しない。

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
uv run streamlit run app/streamlit_app.py
```

Webアプリはrootのeditable path dependencyとしてHestiaを直接importし、Hestia Studio用の別環境・別サーバーを起動しない。HestiaはPython 3.11以上を使う。評価9 CLIは再現性のため、従来どおり `uv run --project <Hestiaの絶対パス> --frozen smart-home-sim experiment ...` を呼び、Hestiaのworkerはmaster-researchの `.venv/bin/python` で既存研究コードを実行する。Hestia単体の開発・テスト時だけ `uv sync --project Hestia` を使う。

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
| `Hestia/examples/experiments/noise_free.yaml` | 本実験。3住宅 × 2条件（base / large variability）× 3seed = 18ログ。各ログ21日（train 14日/test 7日）、LLM各3反復。Arubaの正式評価と同じ14日間の履歴から系列を生成する。 |
| `Hestia/examples/experiments/noise_free_duration.yaml` | 期間感度評価。既存本実験と同じ6条件・3seed・LLM各3反復で、各runの35日rawログを1回だけ生成する。 |
| Webの「本実験・小規模確認」 | `noise_free.yaml`の全条件・全設定を継承し、seed=[11]、LLM 1反復だけへoverrideするeffective plan。6ログ、fresh最大24 API calls。 |
| `output/<model>/9_hestia/pilot/experiment.json` | 確定した計画snapshot。 |
| `output/<model>/9_hestia/pilot/runs/<condition>/seed_<seed>/` | 元ログ、正解、学習入力、代表状態・network、抽出結果、個別採点、再現用hash。 |
| `results/<model>/9_hestia/pilot/evaluation9_summary.csv` | 条件・手法別の集計。最初に読むファイル。 |
| `results/<model>/9_hestia/pilot/evaluation9_summary_runs.csv` | seed・LLM run・condition単位のstatusとPrimary指標。 |
| `results/<model>/9_hestia/pilot/evaluation9_summary.json` | `runs` にseed・反復別statusと指標、`summary` に集計を保存。 |
| `output/<model>/logs/evaluation_dashboard/` | Webのコマンド履歴と実行ログ。workerの詳細ログは各runの `runtime/`。 |
| `output/<model>/logs/evaluation_dashboard/evaluation9_plans/` | Webで確定したseed・LLM run数を含む、内容hash付きのeffective plan。 |

既にHestiaの `experiment generate` で作成した `experiment.json` と `runs/` のあるディレクトリも指定できる。生成を省いてprepare以降を個別実行する場合、以後の設定はそのディレクトリ内のsnapshotを使う。画面の計画ファイル指定はgenerateにだけ適用される。

Studioの `events.csv` / `casas_motion_door.txt` 単体には本評価が要求する計画・正解・train/test契約がないため、そのまま評価9へ投入することはできない。単体ログを従来の研究前処理に渡す手順は [Hestiaデータ統合](../integrations/hestia_dataset_integration.md) を参照する。

## Webアプリでの実行手順

1. 左サイドバーで **評価9** を選ぶ。
2. **実験プリセット** でPilot、本実験・小規模確認、または本実験を選び、seed一覧と同一condition・seedあたりのLLM run数を設定する。小規模確認は`noise_free.yaml`を読み、他の全項目を維持してseed=[11]、LLM 1反復だけをoverrideする。既定パスは`output/<model>/9_hestia/full_smoke`と`results/<model>/9_hestia/full_smoke`。画面はconditions、train/test日数、seed・反復数を表示する。K・日数・平滑化・condition詳細はこの画面では変更せず、サイドバーの共通平滑化も評価9には適用しない。
3. **実行規模** でcondition数、seed数、LLM run数、4時間帯、Hestia生成run数、推定Gemini API呼び出し回数を確認する。未実行時のfresh推定は `condition数 × seed数 × llm_runs × 4時間帯`で、小規模確認は24回、本実験は216回。prepare済みの同一experimentがあれば、既存`extraction_budget()`によるcheckpoint反映後の残件数を優先する。JSON parse retryを含む上限も表示するが、backendのtransport retryは予測に含まれない。
4. 詳細な配置を確認・変更する場合は **Hestia Studio** タブを開き、Studio内の compact / corridor / branched タブを切り替える。各住宅の未保存編集はページを開いている間保持される。編集は `Hestia/scenarios/` にYAML保存できるが、評価9の本実験planへは自動反映されない。**論文用SVG** / **論文用PNG** では部屋・接続・センサー／デバイス配置を論文向け画像として保存できる。この画像は住宅構造の説明用であり、ground truthや検出器入力には使用しない。
5. 必要なら共通の **dry-run** でコマンドだけ記録する。コマンドには画面上に表示されたeffective planのパスが入り、実処理・API呼出しは行わない。
6. **不足ファイル生成 + 評価本体** で一括実行する。API許可OFFでは、生成 → 前処理 → 頻度対照 → LLM予算表示 → 採点まで実行する。LLMはmissing、頻度対照は採点済みになる。
7. 提案手法も採点する場合は、ステップ4のモデル・呼出し数を確認し、**LLM抽出のAPI呼出しを許可** をONにしてステップ4を実行し、続いてステップ5を実行する。master-researchの既存認証設定を使う。
8. **結果比較** タブで `results/<model>/9_hestia/pilot` を選び、CSVとJSONを確認する。

評価9は一括実行の各前段を毎回CLIに渡して、既存成果物のhashを検証する。ファイルの存在だけで前段を飛ばさない。完了済みの生成・前処理・LLM反復は既存CLIが検証して再利用する。「全ステップを再実行」も強制上書きではない。計画・コードの変更や不完全な生成が検出された場合は停止するため、新しい実験ディレクトリと集計先を指定する。

LLM出力がJSONとしては読めても、採点契約（状態列2〜4件・時間帯別ADLラベル）を満たさない場合は完了扱いにしない。再実行時は不正だった時間帯のcheckpointと出力を `predictions/llm/invalid_completed/` に退避し、その時間帯だけを再抽出する。正常な時間帯・反復・前処理成果物は再利用する。

画面で確定した設定はsourceの`noise_free_pilot.yaml` / `noise_free.yaml`を上書きせず、全ExperimentPlan項目を保持したeffective planとして保存する。同じ内容は同じhashのファイルを再利用する。同じexperiment出力先へ異なるeffective planを適用すると、従来どおり`experiment.json`との一致検証で停止するため、設定変更時は新しい実験ディレクトリを使う。
比較はHestia生成処理と同じraw snapshot一致で行う。旧snapshotが後から追加された既定項目を欠く場合も既存成果物を暗黙に書き換えず、画面が実行前に停止する。表示される **推奨する新しい出力先へ切り替える** を押すと、hash付きの生成先・集計先へ一度に変更できる。同じパスを使いたい場合は確認チェック後に **既存成果物をバックアップして同じ出力先を再利用** を押す。既存の生成・集計成果物は削除せず`output/<model>/logs/evaluation_dashboard/evaluation9_backups/`へ退避し、空いた元パスを新しいplanで再利用する。hash検証自体は無効化しない。

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

## train期間感度評価

「過去何日分のセンサログで性能が安定するか」を調べる追加実験で、本実験と揃えた14日trainを正式baselineとする。3日は短期間、7日は1週間、14日は2週間、28日は4週間の履歴を表す。testは全条件で7日固定とし、曜日を一巡させつつ評価期間長の違いを交絡させない。

各condition × seedについて35日ログを1回だけ生成し、Day 29〜35を共通testとする。trainはtest直前から遡るため、3日=Day 26〜28、7日=Day 22〜28、14日=Day 15〜28、28日=Day 1〜28である。同じrawログと同じtestを使うpaired comparisonであり、期間ごとのシミュレーション差を持ち込まない。`output/<model>/9_hestia/duration/raw/`が18個のraw run、`windows/train_{3,7,14,28}d/`が期間依存成果物である。派生windowにはraw生成markerのhash、window開始、train/test日数を保存し、状態表・network・checkpointを期間間で混同しない。

各windowは対象train sliceだけで代表状態、canonical gold/catalog、状態遷移network、frequency候補、LLM入力を作る。testはそのwindowの代表状態表へ固定写像し、K、h、閾値、canonical選択、抽出には使用しない。28日状態表を短い条件へ流用しない。モデル、prompt、K=15、h=0、平滑化、targets、時間帯、採点は本実験と同一である。

canonical goldはtrain期間ごとに変化し得る。このためexact-match `precision/recall/f1` は母集合が完全に同じ性能尺度とは限らず、単純な大小だけで結論を出さない。主比較では `adl_macro_f1`、`test_target_episode_coverage`、`test_visible_catalog_recall`を併読する。14日差分は同じcondition・seedを対応づけた「各期間の値 − 14日値」（相対変化率ではない差分）であり、LLM反復をseed内平均してからseed間平均・標本標準偏差を求める。

```bash
uv run python scripts/evaluate_9_duration.py --dry-run
uv run python scripts/evaluate_9_duration.py --stage generate
uv run python scripts/evaluate_9_duration.py --stage prepare
uv run python scripts/evaluate_9_duration.py --stage baseline
uv run python scripts/evaluate_9_duration.py --stage budget
uv run python scripts/evaluate_9_duration.py --stage extract --allow-api
uv run python scripts/evaluate_9_duration.py --stage evaluate --method both
```

`--duration-workers`（既定4）で、期間windowを同時に処理する数を指定できる。`generate` と `evaluate` は1回ずつ直列で実行し、`prepare`、`baseline`、`budget`／`extract` は同じ工程内の期間だけを並列にする。各工程は全期間の完了を待つため、window内の前処理→対照→抽出→集計という依存関係と既存の出力形式は変わらない。API利用時は同時リクエスト数も増えるので、利用枠に応じて値を下げる。`--duration-workers 1`は従来の直列実行である。

`--train-days 3,7,14,28`でwindow一覧を明示できるが、14日baselineとraw planの最大train日数（28日）は必須である。API opt-inは既存評価と同じで、許可OFFは0 calls。fresh上限は `6 conditions × 3 seeds × 3 LLM runs × 4 time bands × 4 durations = 864 calls`、parse retry上限は現行3試行で2592回である。transport retryは含まない。raw生成は18回だけで、LLM抽出は異なるnetworkを持つ72 windowごとに行う。

出力は `results/<model>/9_hestia/duration/evaluation9_duration_summary.csv`、`evaluation9_duration_summary_runs.csv`、`evaluation9_duration_summary.json`。summaryはtrain/test日数、condition（`overall`を含む）、method、model、各指標のmean/std/n_seeds、run status、主要指標のpaired `*_delta_vs_14d_*`を持つ。期間感度プロトコルはv2であり、旧7日基準のsummaryとは混在させず再集計する。`adl_macro_f1`、`test_target_episode_coverage`、`f1`のcondition別・overall SVGも生成し、Webの結果比較では同CSVを期間軸の折れ線で表示できる。Webは既存`prepared.json`の研究コード／設定指紋も実行前に照合し、不一致なら既存成果物を上書きせず、新しい出力先への切替または明示バックアップを要求する。前者は現在の指紋を出力先名にも含める。

## 比較と内部処理

- 提案手法の状態抽出・写像・ネットワーク・LLMはmaster-researchの既存実装を呼ぶ。
- `frequency` は前半の連続2〜4状態、最低support=2、頻度上位20件の動作確認用対照。既存研究の頻度baselineとは別定義。ADL予測は行わず、ADL指標はnull。
- 検出器には正解ラベルや住人IDを渡さない。代表状態・ネットワーク・頻度対照は前半だけで構築し、後半はその状態表に固定して写像する。
- planの`targets`はtarget ID、activity、resident、time band、各日に繰り返す開始予定時刻列を持つ。未指定planは従来スケジュールと互換。target指定時も既存routine/activity/micro-templateとconditionの揺らぎを使う。
- 複数住人の正解活動は住人・活動IDで保持し、採点は家全体の複数ラベルとして行う。住人識別精度ではない。
- 欠落LLMを0点扱いしない。APIなしでコマンドが成功しても、提案手法の評価完了を意味しない。

## パラメータと注意点

pilotの既定はK=15、h=0、平滑化0秒、観測ノイズなし、seed=11。評価6・7の正式workflowで採用した平滑化5秒・`network-equivalent`・holdoutとは独立した研究条件である。評価9の期間分割・正解なしという制約は [既知の不一致 KI-07](../research/known_issues.md) と混同しない。

後半の結果を見てKや閾値を調整した成績を、未使用testの性能として報告しない。pilotの1seedから統計的結論を出さない。詳細な条件、catalogの境界条件、missing集計、制約は [Hestia評価仕様](../../Hestia/docs/noise_free_evaluation.md) を参照する。
