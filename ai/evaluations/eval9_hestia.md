# 評価9: Hestia合成ログの系列回収・ADL意味対応（AI向け詳細）

**正本:** [docs/evaluations/evaluation_9_hestia.md](../../docs/evaluations/evaluation_9_hestia.md)、[Hestia採点仕様](../../Hestia/docs/noise_free_evaluation.md)
**CLI / 実装 / テスト:** `scripts/evaluate_9_hestia.py` → `src/behavior_pattern_mining/evaluation/evaluation9_hestia.py` → `Hestia/` experiment CLI → `tests/test_evaluation9_hestia.py`

## 研究上の位置付け

Hestia生成センサーログへ既存の提案手法（代表状態→状態遷移network→LLM抽出）を適用し、生成時の正解から系列回収とADL意味対応を診断する。実Arubaの性能値と混ぜない。HESTIA論文の公式実装再現でもない。評価1〜8の前処理・指標・データは変更しない。

Hestiaはこの親repoの`Hestia/`に含まれる。移動前の外部`/Users/wataru/Desktop/Hestia`を使わず、別cloneもしない。Webはroot editable dependencyを直接importする。評価9 CLIのみHestiaの別uv環境でexperiment CLIを呼び、workerはrootの研究コードを実行する。

## train/testとgold契約

- detectorへ正解ラベル・住人IDを入力しない。代表状態、network、frequency候補、canonical goldは**前半trainだけ**で作る。後半testはその状態表へ固定写像し、canonical/K/h/抽出を選び直さない。
- Primary goldはHestiaの生templateではない。train episodeを研究コードと同じ前処理へ通し、trainだけで作った状態表へ固定写像したepisode内系列から作る。target/time-bandごとにtrain episode support最大、次に最長（2〜4状態）のcandidateをcanonicalにし、同率は全て保持する。
- proper contiguous subsequenceはfragment候補。後半は出現・採点だけに使う。複数住人の正解は住人/activity IDで保持するが、採点は家全体のmulti-label ADLであり住人識別精度ではない。

## 指標と欠損規則

| 指標 | 定義 |
|---|---|
| `precision/recall/f1`, TP/FP/FN | canonical gold と抽出された一意な`(time_band, representative-state sequence)`のexact match |
| `fragmentation_rate` | parent target episodeへtest出現の70%以上が含まれる抽出fragment / potential fragment。potential 0だけN/A、potentialありかつemitted 0は0 |
| `catalog_recall` | 前半の完了活動で2 episode以上に現れる2〜4状態・時間帯付きcatalogの回収率 |
| `test_visible_catalog_recall` | そのcatalogのうち後半にも現れたものに限定 |
| `test_target_episode_coverage` | 後半対象活動のうちcatalog系列が完全に1回以上含まれる割合 |
| `test_supported_pattern_fraction` | 抽出系列のうち後半に出現した割合 |
| `train/test_other_duration_ratio` | 状態表に表現されない時間。LLM以前の情報損失 |
| `adl_macro_f1` | 後半の正解活動領域で家全体multi-labelを時間重なり採点したmacro-F1 |

抽出空ならprecision=null、gold空ならrecall=null、両方空ならF1=null、片方だけ空ならF1=0。seed内ではLLM反復を平均してからseed間平均と標本標準偏差を出す。1 seedのstdは空欄/null。missing/invalid反復があるseedは主集計から除外し、expected/complete/missing/invalid run・seed数を併記する。欠落LLMを0点扱いして提案手法完了と誤認しない。

## 実験・モデル別成果物

`experiment.json`、生成ログ、truth、prepared state/networkは`output/<model>/9_hestia/`。LLM JSON、mode checkpoint、usage、LLM個別採点は`results/<model>/9_hestia/<experiment>/artifacts/`、集計はそのexperiment直下。Hestia CLIへmodel-specific artifact rootが渡るため、別モデルのcomplete markerを再利用しない。

標準planは`Hestia/examples/experiments/noise_free_pilot.yaml`（4 condition×1 seed×4日、前半2/後半2、LLM各1反復）、API不要のgold契約確認は`controlled_gold_pilot.yaml`、本実験は`noise_free.yaml`（6 condition）。主出力は`evaluation9_summary.csv`（最初に読む）、seed/run/condition別`evaluation9_summary_runs.csv`、`evaluation9_summary.json`。Webのログ・effective planは`output/<model>/logs/evaluation_dashboard/`に残る。Studioの単体`events.csv`/`casas_motion_door.txt`にはplan・truth・train/test契約がないため、直接評価9の入力にしない。

## 実行段階・API安全性

`controlled_gold_pilot.yaml` + `--method frequency`はAPIなしのgold契約pilot。通常の`evaluate_9_hestia.py`もAPIなしでは生成、prepare、frequency、budget、採点までであり、提案LLMはmissing。LLMは`--stage extract --allow-api`または`run --allow-api`だけが呼ぶ。`--dry-run`はCLIでは一切ファイルを書かない。

```bash
# API不要のgold契約pilot
uv run python scripts/evaluate_9_hestia.py \
  --plan Hestia/examples/experiments/controlled_gold_pilot.yaml \
  --experiment output/9_hestia/controlled_gold_pilot \
  --output-dir results/<model>/9_hestia/controlled_gold_pilot --method frequency

# LLM抽出と再採点（明示opt-in）
uv run python scripts/evaluate_9_hestia.py --stage budget
uv run python scripts/evaluate_9_hestia.py --stage extract --allow-api
uv run python scripts/evaluate_9_hestia.py --stage evaluate --method both
```

本実験は`--plan Hestia/examples/experiments/noise_free.yaml --experiment output/9_hestia/full --output-dir results/<model>/9_hestia/full`を明示する。train 14日/test 7日で、Aruba正式評価と同じ14日間の履歴から系列を生成する。6 conditionは`compact_base`, `compact_variable`, `corridor_base`, `corridor_variable`, `branched_base`, `branched_variable`で、variableは開始時刻±45分、活動・step時間±30%の揺らぎである。

Webは評価9を選び、plan preset/seed/LLM runを設定する。共通平滑化、K、日数、condition詳細を画面から変更せず、effective planとしてhash付き保存する。既存成果物はファイル存在でスキップせず、CLIのhash検証へ委譲する。plan/code変更・不完全生成なら新experiment/output先で停止する。既存と異なるplanを同じパスへ使う時は、UIが作るbackupへ退避する明示操作だけを使い、hash検証を無効化しない。

## duration感度

`evaluate_9_duration.py`は本実験と同じ14日trainを正式baselineとする追加評価。各condition×seedで35日rawを1回生成し、Day29–35を共通test、trainは直前の3/7/14/28日へ変えるpaired比較。各windowで状態表・canonical・network・checkpointを独立に作り、28日状態表を短期間へ流用しない。canonicalがtrain期間で変わるため、exact P/R/F1だけの単純大小で結論せず、`adl_macro_f1`、target coverage、visible catalog recallを併読する。14日との差は相対率でなく同condition/seedの値差である。

本実験は6 condition×3 seed×3 LLM run×4帯、durationはさらに4期間を掛ける（fresh最大864 API calls、parse retry上限2592、transport retry除く）。API許可前に予算を確認する。

durationは`evaluate_9_duration.py`へ順に`--stage generate`、`prepare`、`baseline`、`budget`、`extract --allow-api`、`evaluate --method both`を渡す。出力は`results/<model>/9_hestia/duration/evaluation9_duration_summary.csv`、`..._summary_runs.csv`、`..._summary.json`と、`adl_macro_f1`・target coverage・F1のcondition別/overall SVGである。

## 不変条件

- 評価9の指標を親側へ再実装しない。Hestiaの評価仕様とCLIを正本として使う。
- pilot既定はK=15、h=0、平滑化0秒、観測ノイズなし、seed=11。評価6・7で採用した5秒・`network-equivalent`・holdoutとは独立した条件である。
- testを見てK/hやtargetを調整した値を未使用test性能として報告しない。pilot 1 seedから統計的結論を出さない。
