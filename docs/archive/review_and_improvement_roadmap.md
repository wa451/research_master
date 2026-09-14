# コードレビュー結果と改善ロードマップ

この文書は、レビュー入力として使われた未追跡の`iot2026_paper.pdf`(IoT 2026投稿論文。リポジトリ内の対応ソースは`iot2026_submission_ja/main_reviewed.tex`)とリポジトリ現状(コミット `81559e3` 時点)を突き合わせて実施したレビューの記録である。目的は次回以降のセッション(人間・AIエージェント双方)が、過去の議論を再現せずに続きから作業できるようにすることである。

対象読者はAIエージェントを含む。したがって各項目には、判断の根拠となった具体的なファイル・行番号・既存文書のIDを可能な限り併記する。ここに書かれた「改善提案」は決定事項ではない。着手前に必ず [AGENTS.md](../../AGENTS.md) の方針(研究条件・閾値・分母・split・seedを別作業のついでに変更しない)と [known_issues.md](../research/known_issues.md) を再確認すること。

## 0. 前提

- 論文の主張・RQ・数値は `iot2026_paper.pdf` を正本とする。この文書はその内容を要約しない。差分・懸念点のみを記録する。
- 研究ロジックの責務配置は [code_inventory.md](../architecture/code_inventory.md)、データフローは [pipeline.md](../architecture/pipeline.md)、論文採用条件は [paper_parameters.md](../research/paper_parameters.md) を参照。
- コミット前の再確認時点でのテスト状態: `uv run python -m unittest discover -s tests` → **126 tests, OK**(全通過、2026-09-04時点)。

## 1. コードレビューの総評

- 前処理(Sample-and-Hold、遅延OFF平滑化、連続状態圧縮、ハミング写像)は純粋関数へ分離されており([state_vectors.py](../../src/behavior_pattern_mining/data/state_vectors.py)、[state_mapping.py](../../src/behavior_pattern_mining/states/state_mapping.py)、[transitions.py](../../src/behavior_pattern_mining/network/transitions.py))、論文3.2〜3.4節の記述と実装を照合し、一致を確認した。
- 研究条件と実装の不一致は [known_issues.md](../research/known_issues.md) がKI-01〜KI-14として既に体系的に追跡しており、新規レビューで見つかった論点の多くは既にここに含まれている。特に研究結果の数値そのものに影響しうるものとして次を優先確認対象とする。
  - **KI-02**(評価2の5 runがrun1のcheckpointを参照しうる): 論文の「5回実行の標準偏差」という安定性主張の前提に関わる。
  - **KI-06 / KI-07**(パターン抽出用の状態系列と評価4/6/7が使うADL照合用状態系列の前処理が異なる): RQ1・RQ3双方の数値の前提に関わる。
- **KI-12を実物突合で再確認した**。実行時に読まれる [prompts/pattern_extraction_prompt.md](../../prompts/pattern_extraction_prompt.md) のADLラベル集合(10種、論文本文と一致)と、[pattern_extractor.py:72-95](../../src/behavior_pattern_mining/llm/pattern_extractor.py#L72-L95) に埋め込まれたfallback用`PROMPT_TEMPLATE`のラベル集合(8種+Noise/Ambiguous、論文と不一致)は異なる。通常運用では外部ファイルが優先されるため実害はないが、`prompts/`欠落時に無言で異なる実験条件へフォールバックするリスクは残る。
- **新規発見: `Bathing`ラベルの単一ラベル/複数ラベルマッピングが完全に食い違っている(KI-07の具体化)。**
  - [adl.py:29-44](../../src/behavior_pattern_mining/evaluation/adl.py#L29-L44) の単一ラベル用`ADL_CATEGORY_MAP`(評価4が使用)は `"Bathing": "Wake-up"`。
  - [adl.py:46-63](../../src/behavior_pattern_mining/evaluation/adl.py#L46-L63) の複数ラベル用`ADL_CATEGORY_SET_MAP`(評価6・8等が使用)は `"Bathing": ("Hygiene",)`。
  - [adl_correspondence.py:68-84](../../src/behavior_pattern_mining/evaluation/adl_correspondence.py#L68-L84) の評価5専用`EVALUATION5_ADL_CATEGORY_MAP`も `"Bathing": ("Hygiene",)`。
  - `Bathroom`・`Personal_Hygiene`はどちらの表でも`Wake-up`が共通して含まれる(部分集合関係)が、`Bathing`だけは評価4側(`Wake-up`)と評価5/6/8側(`Hygiene`)が**共通ラベルを一切持たない**。同じ生ラベルに対して評価間で正解ADLが完全に異なる。
  - **現在のAruba実験では顕在化しない**: `new_labeled_data/aruba.txt`には`Bathing`・`Bathroom`・`Personal_Hygiene`・`Toileting`のいずれも出現しない(実際に含まれる生ラベルは`Bed_to_Toilet`, `Eating`, `Enter_Home`, `Housekeeping`, `Leave_Home`, `Meal_Preparation`, `Relax`, `Respirate`, `Sleeping`, `Wash_Dishes`, `Work`のみ)。
  - **しかし`new_labeled_data/tulum2.txt`には実際に`Bathing`と`Personal_Hygiene`が含まれる**(下記IP-10参照)。他住居のデータで評価を行う際に確実に顕在化する。

## 2. 改善ロードマップ

IDは本文書内でのみ有効な参照用ラベル(`IP-xx` = Improvement Proposal)。`known_issues.md`のKI番号とは独立。

| ID | 優先度 | 内容 | 論文/RQとの対応 | 根拠・関連箇所 |
|---|---|---|---|---|
| IP-01 | 高 | KI-02を解消し、5 runを真に独立させる(runごとに別checkpointを使う) | RQ1、5.2節の安定性主張(F1標準偏差0.053 vs 0.098) | [known_issues.md#ki-02](../research/known_issues.md#ki-02)、[llm_eval_batch.py](../../src/behavior_pattern_mining/pipelines/llm_eval_batch.py)、[pattern_extractor.py](../../src/behavior_pattern_mining/llm/pattern_extractor.py) |
| IP-02 | 高 | KI-06/KI-07を解消し、パターン抽出とADL評価で同一の状態系列前処理(`network-equivalent`)に統一する | RQ1(評価6)、RQ3(評価4・5・7) | [known_issues.md#ki-06](../research/known_issues.md#ki-06)、[known_issues.md#ki-07](../research/known_issues.md#ki-07) |
| IP-03 | 高 | K, hの選定に使うデータと評価に使うデータを分離する(現状は220日全体を選定に使用) | 5.1節・5.5節限界1番目(著者も認識済み) | [evaluation_7_parameter_sensitivity_adl_interpretation.md](../evaluations/evaluation_7_parameter_sensitivity_adl_interpretation.md) |
| IP-04 | 中 | RQ2の非単調性(Middle<Low)の原因分析。系列長・時間帯・構成状態・ADL多様性を統制した追加分析を行う | RQ2、5.3節(著者が次の分析として明示) | [evaluation_8_frequency_stratified_adl_consistency.md](../evaluations/evaluation_8_frequency_stratified_adl_consistency.md) |
| IP-05 | 中 | 断片化(Fragmentation)を検証可能にする。詳細設計は本文書3節を参照 | RQ3、5.4節・5.5節限界5番目 | 本文書3節、[evaluation_5_adl_correspondence.md](../evaluations/evaluation_5_adl_correspondence.md) |
| IP-06 | 中 | Rule-M/Sとの比較条件を揃える(提案手法は5 run平均・Rule-M/Sは決定的単一run、出力数も異なる) | RQ3、5.4節(著者も限界として明記) | [evaluation_5_adl_correspondence.md](../evaluations/evaluation_5_adl_correspondence.md) Table 6相当 |
| IP-07 | 低〜中 | Hestia合成データ([hestia_dataset_integration.md](../integrations/hestia_dataset_integration.md))を用いた複数シナリオでの頑健性チェックを追加する。正式性能値としてではなく、提案手法優位性の傾向が崩れないかの探索的補足として位置づける | 5.5節限界1番目(単一住居・単一LLM) | [hestia_dataset_integration.md](../integrations/hestia_dataset_integration.md)(既に基盤整備済み。`Other`滞在比率が実Arubaと大きく乖離している点に注意) |
| IP-08 | 低〜中 | パターン名・解釈根拠(rationale)の人手評価を追加する。現状はADL集合一致度のみで意味的妥当性を代理評価している | 5.5節限界4番目(著者も明記) | 論文5.2節「names and rationales were not manually assessed」 |
| IP-09 | 低 | run数増加またはブートストラップ法による統計的検定の追加検討 | 4.1節(現状は意図的に検定を回避) | 論文4.1節 |
| IP-10 | 中〜高 | `new_labeled_data/{cairo,milan,tulum1,tulum2}.txt`・`data/{cairo,milan,tulum}.csv`は既にリポジトリ内に存在する**実データ**の他住居CASASログである。合成データ(Hestia、IP-07)より説得力のある「複数住居での検証」(5.5節限界1番目)に使える。ただし着手前に次が前提: (1) `configs/aruba_sensor_map.json`相当のセンサーマップが各住居に存在しない、(2) 各住居のADL語彙がArubaと大きく異なる(例: milanは`Guest_Bathroom`/`Master_Bathroom`/`Desk_Activity`等、tulum2は`Bathing`/`Personal_Hygiene`/`Yoga`等)ため`ADL_CATEGORY_MAP`/`ADL_CATEGORY_SET_MAP`等の拡張が必要、(3) 本文書1節で示した`Bathing`不整合を先に解消しないと、tulum2で評価4と評価5/6/8の正解ADLが食い違ったまま実験することになる | 5.5節限界1番目(単一住居・単一LLM) | 本文書1節「Bathing」項、[adl.py](../../src/behavior_pattern_mining/evaluation/adl.py) |

## 3. 個別設計メモ: 断片化(Fragmentation)検証の改善案(IP-05詳細)

### 問題の構造

`evaluation_5_adl_correspondence.md:41` の定義により、断片化判定は「**同一手法・同一run・同一時間帯**内で、パターンpがより長いパターンqの連続部分系列である」場合のみ成立する。qは各手法が実際に出力したパターン集合の中からしか選べない。

### 検討した対策: 系列長上限(2〜4)を単純に撤廃・拡大する

**却下**。理由は以下。

1. **Freq / FP-Growth / transition_probability baselineは反単調な選出基準を使っている。**
   - Freq: 出現回数の多い順に上位50件([adl_correspondence.py:702-721](../../src/behavior_pattern_mining/evaluation/adl_correspondence.py#L702-L721))。系列が長いほど出現回数は単調に減少するため、長さ上限を外しても上位50件は短い系列に占有され続ける。無制限化フラグ`COUNT_UNBOUNDED_LENGTHS`は[frequency.py:34](../../src/behavior_pattern_mining/baselines/frequency.py#L34)に既に実装されているが、単独では効果が薄い。
   - FP-Growth系: supportも同じ反単調性を持つ([adl_correspondence.py:702-721](../../src/behavior_pattern_mining/evaluation/adl_correspondence.py#L702-L721))。
   - transition_probability: スコアが各stepの遷移確率の積([adl_correspondence.py:825-861](../../src/behavior_pattern_mining/evaluation/adl_correspondence.py#L825-L861))であるため、系列が長いほどスコアは単調に減少する。
   - したがって、これら3baselineは上限を伸ばしても長い親パターンがtop-Kに入ってこない構造的制約がある。
2. **提案手法(LLM)の系列長「2〜4」は自然言語プロンプトに直接埋め込まれた研究条件である。**
   - [prompts/pattern_extraction_prompt.md:29](../../prompts/pattern_extraction_prompt.md#L29)、[pattern_extractor.py:108](../../src/behavior_pattern_mining/llm/pattern_extractor.py#L108)、[direct_log_extractor.py:151](../../src/behavior_pattern_mining/llm/direct_log_extractor.py#L151) に同一文言がある。
   - 変更は「解釈困難な長い系列を避ける」という論文の設計思想([paper_parameters.md:113](../research/paper_parameters.md))そのものの変更にあたり、AGENTS.mdの「研究条件を別作業のついでに変更しない」方針に抵触する。変更する場合は独立した実験条件として明示し、既存のK=15,h=0系列長2〜4の結果と混在させてはならない。

### 推奨する代替案

断片化の「親」を、**同一手法の出力集合の中からではなく、実際の代表状態系列(生データ)上での連続拡張**として再定義する。

- パターンpの各出現区間について、代表状態系列上で前後に数ステップ拡張した区間を作り、その拡張区間がADL的に一貫したより長いルーチンの一部として扱えるかを判定する。
- 利点:
  - 系列長2〜4という研究条件(LLMプロンプト・baseline共通)を変更せずに済む。
  - 反単調性による「短い系列しか上位に来ない」問題を回避できる。
  - 「このパターンは実データ上で本当により長い日常ルーチンの断片なのか」というRQ3本来の問いに直接答えられる。
- 代替案2(次善): baseline側だけ長さ上限を緩める(例: 4→6)。ただしこの場合も選出方式を「全体でtop-K」から「長さ区分ごとにtop-K」等に変えないと、反単調性の問題で長い系列がtop-Kから排除されたままになる。実施する場合は[evaluation_5_adl_correspondence.md:364](../evaluations/evaluation_5_adl_correspondence.md#L364)の「閾値は全手法・全runで同一に固定」という公平性原則との整合を検討すること。

### 未決定事項

上記2案のどちらを採用するか、また採用する場合の実装範囲(`adl_correspondence.py`のfragmentation判定ロジックの変更が必要)は未着手。着手する場合は、変更が既存の`results/5_pattern_quality_*/`の過去成果物と非互換になることを踏まえ、[refactoring_record.md](../architecture/refactoring_record.md)の高リスク領域の扱いに準じること。

## 4. 本文書の更新方針

- 新たな不一致・懸念が見つかった場合、まず [known_issues.md](../research/known_issues.md) に該当するKIがないか確認し、なければKIとして追加するかIP-xxとしてここに追加するかを判断する。KIは「実装と文書の不一致(未確定の仕様判断)」、IPは「今後実施すべき研究・評価の改善作業」という区別を維持する。
- 着手したIP項目は、削除せず「状態: 着手/完了」および対応するコミット・変更ファイルを追記する。
