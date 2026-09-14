# 観測ノイズなし・複数住宅での提案手法評価

ユーザーが指定した提案手法は「センサーログ → 代表状態 → 状態遷移ネットワーク →
LLMによるパターン検出」。本機能は、この手法を既存の `master-research` の実装で
実行し、Hestia生成ログの正解を使って採点するための追加実験基盤です。
既存の評価5〜8、公開実データ、研究側のコード・設定は変更しません。
新しい公開実データの準備も不要です。合成ログによる結果を実環境での性能保証や
HESTIA原著の再現実験とは呼びません。

## 条件と実験規模

`examples/experiments/noise_free.yaml` は本実験の確定planです。compact / corridor /
branchedの3住宅それぞれについて、baseとlarge variabilityの2条件だけを明示し、計6条件を
生成します。各条件はseed 11 / 22 / 33で反復するため、合計18ログです。

| 条件 | 住人数・生活習慣・頻度 | 行動の揺らぎ | 採用理由 |
|---|---|---|---|
| base | 1人・early・daily | small: 開始±10分、活動・step時間±10% | 基準性能を確認するため |
| large variability | 1人・early・daily | large: 開始±45分、活動・step時間±30% | 行動開始時刻や活動・step時間の大きな揺らぎに対する提案手法の頑健性を確認するため |

住宅・設備の定義と観測ノイズ無効の条件は従来から変更しません。

`default_conditions()` が提供する2 residents / late / home / low frequency / high frequency /
fixed variabilityは削除せず、汎用Hestia実験や別planから引き続き利用できます。ただし、評価9の
本実験planには含めません。

空間数には屋外を含みます。屋外に人感センサーは置かず、出入口のドアを観測します。
全住宅で部屋人感・照明・ドア・コーヒー機器・TV・PC用プラグを使用します。
住宅条件は間取りとセンサー数・配置の複合条件であり、それぞれの単独効果は分離しません。

本実験の作業は1回/日です。食事・休憩・作業には共通の
`prepare → use → finish` を配置します。食事は台所→リビング→台所、休憩・作業は
活動室→台所→活動室を移動し、機器・照明は活動単位で利用します。
睡眠・衛生活動・外出も混在させます。これは管理された反復行動シナリオであり、
実生活の完全な日程・行動分布を再現する設定ではありません。

本実験は3住宅 × 2条件 × 3seed = 18ログ、各14日（train 7日/test 7日）で、LLMは
各ログ3反復です。全4時間帯がある場合、新規のモード抽出は最大216回で、さらに
parse/通信retryがあり得ます。
この規模は費用の承認を意味しません。接続確認用の従来pilotに加えて、正解系列の契約を
APIなしで確認する `examples/experiments/controlled_gold_pilot.yaml` を用意しています。
後者はcompact・1人・固定seed・4日（train 2日/test 2日）で、mealとworkを1日1回ずつ
反復します。どちらも統計的結論には不十分です。

## 明示target設定

`targets` を省略した既存planは、従来どおりconditionのmeal / relax / workスケジュールを
使います。`targets` を指定すると、これら3活動と明示targetと同じactivityの従来枠を置き換え、
通常のHestia routineとactivity / micro-templateを使って実行します。設定済みの任意activityを
targetにできます。明示されていない睡眠・衛生・外出は背景活動として残ります。

```yaml
targets:
  - id: morning_meal
    activity_id: meal
    resident_id: resident_1
    time_band: Morning
    scheduled_start_minutes: [390]
  - id: daytime_work
    activity_id: work
    resident_id: resident_1
    time_band: Daytime
    scheduled_start_minutes: [660]
fragmentation_containment_threshold: 0.7
```

`scheduled_start_minutes` は各日に繰り返す開始予定で、列の長さが1日あたりの意図した反復数に
なります。時刻順が意図した活動順序です。指定時刻は宣言したtime band内でなければなりません。
conditionのvariabilityによる開始時刻揺らぎ、活動時間揺らぎ、step時間揺らぎは維持されます。
`truth/target_episodes.json` にはtarget ID、activity/ADL、resident、予定時刻、実start/end、
実time band、意図した日次・全期間反復数、選択template、実行されたstep・部屋経路を保存します。
生成されなかった予定episodeも `generated: false` で区別します。

## 実行方法

Hestiaリポジトリ直下で実行します。`master-research` に既存の `.venv/bin/python` が
必要です。Hestia側にはpandasやLLM SDKの追加インストールを要求しません。

```bash
uv sync
uv run smart-home-sim experiment generate examples/experiments/controlled_gold_pilot.yaml \
  --output outputs/controlled_gold_pilot
uv run smart-home-sim experiment prepare outputs/controlled_gold_pilot \
  --research-root /Users/wataru/Desktop/master-research
uv run smart-home-sim experiment baseline outputs/controlled_gold_pilot
uv run smart-home-sim experiment evaluate outputs/controlled_gold_pilot --method frequency

# 従来の複数住宅pilot
uv run smart-home-sim experiment generate examples/experiments/noise_free_pilot.yaml \
  --output outputs/noise_free_pilot
uv run smart-home-sim experiment prepare outputs/noise_free_pilot \
  --research-root /Users/wataru/Desktop/master-research
uv run smart-home-sim experiment baseline outputs/noise_free_pilot
uv run smart-home-sim experiment evaluate outputs/noise_free_pilot
```

ここまではAPIを呼びません。LLM結果は `missing`、頻度対照だけが採点済みになります。
生成したJSON計画を直接編集したい場合は次のコマンドも使えます。

```bash
uv run smart-home-sim experiment plan --pilot --output outputs/my_pilot_plan.json
uv run smart-home-sim experiment plan --output outputs/my_full_plan.json
```

抽出の前に、モデル名・temperature・未完了反復数・呼出し数を確認します。

```bash
uv run smart-home-sim experiment extract outputs/noise_free_pilot \
  --research-root /Users/wataru/Desktop/master-research
```

実際のLLM呼出しには **明示的に `--allow-api` が必要** です。
既存の研究側 `.env` の認証設定を使います。キーを出力・コピー・変更しません。

```bash
uv run smart-home-sim experiment extract outputs/noise_free_pilot \
  --research-root /Users/wataru/Desktop/master-research --allow-api
uv run smart-home-sim experiment evaluate outputs/noise_free_pilot --method both
```

`prepare/baseline/extract/evaluate` は `--condition compact_two --seed 11` で選択できます。
`evaluate --summary outputs/my_scores` は集計先の指定です。通常は選択条件を含む名前で
`evaluation/summary_*.csv` と `.json` を出力します。

## 漏洩防止と既存手法との接続

- 各住宅/seed内で時間順に分割。代表状態表とネットワーク、頻度対照、canonical選定は
  前半だけで実施。
  後半も前半の状態表に固定して写像します。住宅をまたぐ転移学習の評価ではありません。
- 検出器の入力は `input/train.txt` の4フィールド（日時・sensor ID・状態）と、
  部屋・機器の意味を表す1対1の対応表のみ。ActivityBoundary・resident・activity・
  occupants・template・正解ラベルを渡しません。後半の写像に限り `input/sensors.txt` を使用。
  生の `events_simple.csv` にも真値列が残るため、それをそのまま検出器へ渡しません。
- `research_worker.py` は既存の状態抽出・写像・ネットワークexport・LLM抽出関数を呼びます。
  PNG描画だけを省略。既存手法を別アルゴリズムで置換しません。
- 1秒Sample-and-Hold、K=15、Hamming閾値=0、平滑化0秒を計画に明記。
  観測ノイズなしと平滑化は別設定です。平滑化を変える場合は別出力で実験します。
- 前半で選ばれた状態表に入らない状態はOtherとなります。その割合は検出精度と別に報告。
  Kを後半の正解・成績を見て選び直さないでください。
- LLMは前半の時間帯別network JSONだけを受け取ります。target ID、episode、template、
  gold catalog、test情報は渡しません。既存外部promptを必須とし、
  「単身高齢者宅」の1箇所だけを「住人N人の模擬住宅」へ置換してsnapshot保存します。
  その他の指示とモデル/temperatureは研究コードから取得。旧埋込promptへのfallbackは不可。
- 時間帯・1秒サンプリングの契約が研究側で変わったら停止してadapterの再確認を求めます。
  networkの時間帯別遷移・継続時間の計算は既存実装を継承します。採点側は下記の厳密境界で
  再出現を数えるため、networkの集計値と採点件数が同一とは限りません。

## 2種類の正解と採点

### 1. 埋め込んだ行動系列の回収

正解はtemplateのstep IDではありません。次の順で作ります。

`正解activity episode → 生成センサログ → research_masterと同じ1秒Sample-and-Hold前処理
→ trainだけで作った代表状態表へ全期間を固定写像 → episode内の代表状態系列 → gold catalog`

episode境界で状態区間を切り、連続する同一状態を1つにまとめます。Other、不連続時間、日付、
time bandをまたいで系列を接続しません。これにより、実際に観測・前処理された状態空間で
採点し、Hestia内部表現を検出器に都合のよい状態ID正解として扱うことを避けます。

canonicalはtarget・time bandごとにtrain episode support最大の2〜4状態系列を求め、その中で
最長のものを全て採用します。同率候補は辞書順で全て保持します。つまり、最大4という検出器の
契約内で最も安定して長い実現系列を親とし、後半の出現や成績を見て1候補を選びません。
`evaluation/gold_catalog.json` はcanonicalとproper contiguous subsequenceを区別し、各行に
`gold_pattern_id`, target/activity/resident, time band, representative-state sequence,
canonicalフラグ、親gold ID、train episode support、test episode countを保存します。

Primaryの系列採点は一意な `(time_band, representative-state sequence)` 同士のexact matchで、
canonicalだけを正解集合とします。近似一致は使いません。

- `TP`: canonical goldにも抽出集合にもある系列
- `FP`: 抽出されたがcanonical goldにない系列
- `FN`: canonical goldにあるが抽出されなかった系列
- `precision = TP / (TP + FP)`
- `recall = TP / (TP + FN)`
- `f1 = 2TP / (2TP + FP + FN)`

抽出集合が空ならprecisionはnull、goldが空ならrecallはnull、両方空ならF1もnullです。
片方だけが空ならF1は0です。frequency対照も同じPrimary定義で採点します。

従来の全subsequence catalogと次の指標は後方互換の診断値として残します。

- `catalog_recall`: catalogの何割を抽出したか。時間帯と状態ID列の完全一致。
- `test_visible_catalog_recall`: 後半にも出現したcatalogに限定した回収率。
- `test_target_episode_coverage`: 後半の対象活動のうち、抽出したcatalog系列が少なくとも
  1回完全に含まれる活動の割合。変換段階の欠落も含めた指標です。
- `test_observable_target_episodes`: catalog系列がそもそも後半の活動内で観測できた件数。
  回収件数との差と、対象活動総数との差を分けて確認します。
- `training_truth_diagnostics`: 前半の対象活動数と、2〜4状態が表現できた活動数。
- `test_other_duration_ratio`: 後半のOther時間割合。高い場合はLLM以前の情報損失です。
  `train_other_duration_ratio` も出し、前半側の表現能力を別に確認できます。
- `test_supported_pattern_fraction`: 抽出系列のうち後半で実際に出現した割合。

Otherを削除して両側をつなげません。日付・時間帯・train/test境界・不連続時間を
またぐマッチは禁止。自己反復 `A A` と機械的な `A B A B` は候補から除外し、
`A B A` は許可します。生ログのノイズ追加ではなく、評価系列の定義です。

`catalog_precision_diagnostic` と `out_of_catalog_count` も残しますが、従来catalogにない
自然な発見は誤りとは限りません。これを一般的なprecision/false positiveと呼ばないでください。
catalogが空ならrecallはnull、完了済みの抽出 `[]` なら正解ありのrecallは0です。

### 2. gold基準の断片化

長さ3以上のcanonical `q` から長さ2以上のproper contiguous subsequenceを全て自動生成します。
そのsubsequenceが同じtime bandの別canonicalとして正当に定義されている場合はpotential
fragmentから除外します。抽出されたpotential fragment `p` のtest出現のうち、対応する
`q` のtarget episode内に完全包含される割合が閾値以上ならredundant fragmentです。閾値は
`fragmentation_containment_threshold`、既定0.7で、評価5と同じ包含方向です。

分子・分母はどちらも一意な `(time_band, representative-state sequence)` で数えます。
Primaryは `fragmentation_rate = num_emitted_fragments / num_potential_fragments` です。
potentialが1件以上ありemittedが0件なら0かつ`evaluated`、potential自体が0件のときだけnullかつ
`not_applicable_no_potential_fragments`です。診断用の
`extracted_fragment_rate_diagnostic = fragmented extracted / testで出現した抽出pattern` は
別列とし、Primaryと混同しません。

### 3. ADLの意味対応

LLMの `ADL系列ラベル` は既存promptの定義に従ってラベル集合として扱います。
系列の各状態と各ラベルを1対1に対応させたり、ADL順序正解率を主張したりはしません。
後半の系列出現区間にラベル集合を割り当て、生成側の活動区間と時間単位で比較します。
Sleep / Wake-up / Meal / Relax / Outing / Hygiene / Toileting / Housework / Work / Other
以外や、ラベル欠落の出力はinvalidです。

正解活動のSTART/ENDは `(resident_id, activity_id)` で対応づけるので、同じラベルの
2人同時行動も保持できます。採点単位は **家全体の複数ラベル** です。同ラベルの
重なりは区間の和集合とし二重加算せず、異なるADLの同時成立は両方認めます。
住人の識別精度を測る実験ではありません。

ラベル別の時間precision/recall/F1、micro、macro-F1を保存します。macroは真値か
予測に支持のあるラベルが対象です。予定間の待ち時間は正解ADLがないため意味評価の
領域から除外し、`annotated_fraction` と領域外の予測時間も報告します。
真値があるのに予測が空ならF1=0、両方空ならnull。正解が1秒未満ずれる境界も
時間重なりでそのまま反映し、恣意的な許容幅は追加しません。

## 対照・反復・再実行

`frequency` は前半の連続2〜4状態の頻度上位20件を選ぶ簡単な動作確認用対照です。
同頻度は時間帯/系列の辞書順、最低support=2。真値も後半も使って選びません。
こちらのsupportは出現回数であり、catalogの活動区間数とは異なります。
ADLを推測しないためADL指標はnullです。既存研究の頻度baselineやPrefixSpanとは
別定義であり、提案手法の置換や優位性を証明する十分な比較群ではありません。

同じ `(条件, seed)` のLLM反復をまず平均し、その後seed間の平均・標本標準偏差を
出します。LLM反復を別住宅・別seedとして数えません。欠落/invalidの反復があるseedは
主集計から外し、予定件数・完了件数・除外数を明示。1seedでは標準偏差はnull。
不足したLLM結果を0点にして平均へ混ぜません。抽出件数は揃えていないので、結果の解釈には
件数差も必要です。有意差検定、信頼区間、全組合せ相互作用評価はこの実装には含めません。

`runs/<condition>/seed_<seed>/` に次を保存します。

- `scenario.json`, `run.json`, `generated.json`: 設定・生成コードhash・生成物hash
- `simulation/`: 真値込みの元出力とstep trace（検出器入力ではない）
- `input/`: 正解列のないCASAS・sensor対応表
- `truth/`: 住人別活動区間・固定したmotif定義
- `truth/target_episodes.json`: target予定と生成episode、実start/end、選択template・実行step経路
- `analysis/`: 前半の状態表・network・固定表で写像した全期間series・prompt/model snapshot
- `prepared.json`: 研究コード/config/lockfile・adapter・Pythonバージョン・分析成果物のhash
- `predictions/`: 頻度対照、LLM反復別JSON・時間帯checkpoint・API側のusage記録
- `evaluation/gold_catalog.json`: 投影済みtarget episodeとcanonical/fragment catalog
- `evaluation/`: 反復別採点、採点コードhash
- `runtime/`: 失敗調査用のログ。API usageは既存実装の記録範囲であり、請求総額とは限らない

集計stemが `evaluation9_summary` の場合、JSONはrun詳細とcondition/method集計、
`evaluation9_summary_runs.csv` はseed・LLM run詳細、`evaluation9_summary.csv` はcondition/method
集計です。詳細にはstatus（complete/missing/invalid）、TP/FP/FN、precision/recall/F1、gold・抽出件数、
potential/emitted fragment件数、fragmentation rate/statusを保存します。集計は各seed内でLLM runを
平均してからseed間の平均・標本標準偏差を計算し、欠落/invalid runのあるseedを主集計から除外します。
missing/invalid runの採点値は0ではなくnull、fragmentation statusは`not_evaluated`です。

生成/準備の完了済みデータはhash一致時だけ再利用。設定やコードが変わった場合は別の
出力先を使います。途中失敗した生成/準備ディレクトリを黙って削除・上書きしません。
LLMは同一入力・同一snapshotの時間帯checkpointから再開し、完了した反復は再課金せず
スキップします。シミュレーションのseed再現性と、外部LLM応答の非決定性は別です。

## 既知の制約

既存のイベント検証器は、同じ共有機器へのmicro-step利用が状態変化なしで終了した場合、
利用終了をCSVから復元できず誤検出するケースがあります。今回のtemplateは共有機器を
活動単位で管理し、micro-stepは移動・滞在に限定します。検証器を無効化していません。
この一般的な共有micro-device問題自体は今回修正していません。

実装時のpilotではK=15でOtherが多い住宅も確認しました。これは自動的に補正せず、
診断値として残します。Kを検討する場合は前半データ内の検証等で条件を決め、別出力で
新たに実験してください。後半の成績を見た再調整結果を未使用testの成績とは呼べません。

古い `paper_writeup_plan.md` の未決定事項は履歴として残し、本追加実験の操作・指標は
本書を参照してください。公開実データによる既存評価と本実験は、それぞれ異なる主張を
支えるものとして論文中でも分けて説明する必要があります。
