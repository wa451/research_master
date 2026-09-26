# 既知の不一致・未解決事項

この文書は、現在の実装・テスト・設定・既存文書を照合して見つかった、研究上または互換性上の判断が必要な不一致を記録する。ここに記す挙動は、意図した仕様として確定したものではない。修正する場合は、過去結果への影響を確認し、研究条件として採用する挙動を明示してから、実装・テスト・文書を同時に更新する。

| ID | 対象 | 現在観測される挙動 | 影響と必要な判断 | 主な確認箇所 |
|---|---|---|---|---|
| <a id="ki-01"></a>KI-01 | 共通の `h` | `configs/default.yaml` と一部の無引数実行は `h=1`、論文採用条件と一部の正式評価手順は `h=0` を使う。 | 無引数実行を論文結果の再現手順とみなせない。各評価の正式条件と共通既定値を統一するか、用途別に維持するかを決める。 | `configs/default.yaml`, `scripts/run_all.py`, `docs/research/paper_parameters.md` |
| <a id="ki-02"></a>KI-02 | 評価2のrun | 外側のbatchはrun番号を切り替えるが、抽出処理は引数なしで呼ばれ、`run1` のcheckpointを参照し得る。 | 5 runが独立試行でない可能性がある。run別checkpointへ変更する場合は既存結果を再評価する。 | `src/behavior_pattern_mining/pipelines/llm_eval_batch.py`, `src/behavior_pattern_mining/llm/pattern_extractor.py` |
| <a id="ki-03"></a>KI-03 | 評価2の集計 | Excelにはrun別Precision/Recall/F1と平均が出力されるが、標準偏差や出力パターン数は出力されない。 | 文書上の研究要件に標準偏差を含めるか、現在の出力契約を正式とするかを決める。 | `src/behavior_pattern_mining/pipelines/llm_eval_batch.py` |
| <a id="ki-04"></a>KI-04 | 評価3・6のLLM-only写像 | **Resolved / 採用仕様（2026-09-26）**: direct-log/LLM-onlyは `map_vector_to_state` を再利用し、完全一致後に閾値内の最近傍Hamming写像、同距離はstate table順、範囲外は `その他` とする。h=0は完全一致のみで従来互換。この写像は評価3だけでなく、評価6のsplit/legacy LLM-only生成にも共通である。 | 提案法とLLM-onlyのK,h・state table・写像規則を揃える。過去のLLM-only成果物は旧完全一致写像のため、正式比較には再生成が必要。テスト: `tests/test_direct_log_time_split.py`。 | `src/behavior_pattern_mining/llm/direct_log_extractor.py`, `src/behavior_pattern_mining/states/state_mapping.py` |
| <a id="ki-05"></a>KI-05 | 評価3の条件と集計 | 評価側の入力パスはK=15を固定し、頻度baselineはh=1を参照する。Excelはrun別行のみで平均行を持たない。 | 非既定K/hで異なる条件の成果物を比較し得る。可変条件の伝播方法と集計行の契約を決める。 | `src/behavior_pattern_mining/evaluation/direct_log.py`, `scripts/run_direct_log_baseline.py` |
| <a id="ki-06"></a>KI-06 | 評価6・7の状態系列 | **Resolved / 採用仕様（2026-09-26）**: 評価6・7の正式command builderは `network-equivalent` とnetwork構築と同一の遅延OFFsmoothing値を明示する。固定した14日版state tableを全220日へ適用し、holdoutでは評価7がDay 15–154、評価6がDay 155–220だけを採点する。`evaluate_adl_labels.py` 単体のevent-driven既定と `split-mode legacy` は互換用途として残す。 | 前処理が変わるため旧event-driven state seriesの指標・K,h選択は正式結果として再利用しない。テスト: `tests/test_dashboard_model_selection.py`, `tests/test_evaluation7_staged_workflow.py`。 | `app/command_builder.py`, `scripts/evaluate_adl_labels.py`, `src/behavior_pattern_mining/evaluation/adl.py` |
| <a id="ki-07"></a>KI-07 | 評価4の期間・分類 | 既定はsplitなしで全期間を照合する。また `Bathroom`、`Personal_Hygiene`、`Bathing` は時間帯によらず `Wake-up` へ分類される。 | 記述評価か検出性能評価か、評価期間とtrain/test分離、ADL分類規則を確定する必要がある。 | `src/behavior_pattern_mining/evaluation/adl.py`, `scripts/evaluate_adl_labels.py` |
| <a id="ki-08"></a>KI-08 | 評価6のCLI既定 | 引数なしでは正式14日条件と異なるh=1側のパスや旧state-seriesパスを使い、`n_states` / `hamming_threshold` はsummaryでnullになり得る。 | 正式条件をCLI既定にするか、必須の明示引数として維持するかを決める。 | `scripts/evaluate_6_compare_adl_interpretation_set.py` |
| <a id="ki-09"></a>KI-09 | 評価6のrun集計 | 欠損runは手法ごとに独立して除外され、LLM使用量も手法別のcomplete runで平均される。ラベル別・時間帯別値は全run詳細をpoolして再集計する。 | pairedな共通run・run等重み・pooled集計のどれを正式な分母とするかを決める。 | `scripts/evaluate_6_compare_adl_interpretation_set.py`, `src/behavior_pattern_mining/evaluation/llm_usage.py` |
| <a id="ki-10"></a>KI-10 | 評価8の30日scope | `comparison_30days` は互換読込用として存在するが、scope名と入力detailsの期間を検証しない。14日scopeと既定出力先も共有する。 | 期間検証を追加するか、互換scopeのまま別出力先を運用上必須にするかを決める。 | `scripts/evaluate_8_frequency_stratified_adl_consistency.py` |
| <a id="ki-11"></a>KI-11 | 成果物管理 | 2026-09-22からLLM生成物・checkpoint・metrics・評価5〜10は `results/<model>/`、共有入力・前処理は `output/` に分離した。Geminiの旧モデル依存成果物は移行先のSHA-256一致を確認後、`scripts/migrate_gemini_results.py --cleanup-verified` で削除できる。共有入力・state series・network・baselineは `output/` に残る。一方 `.gitignore` は引き続き `output/`, `picture/`, `results/` を除外する。 | モデル間混同はpath/metadata検証で防止したが、論文値の外部正本は未確定。既存成果物を一括追加して解決しない。 | `.gitignore`, `docs/operations/artifact_policy.md`, `scripts/migrate_gemini_results.py` |
| <a id="ki-12"></a>KI-12 | prompt fallback | 通常読む外部promptと、欠落時の埋め込みfallbackで許可ADLラベル集合が一致しない。 | fallbackを再現契約に含めるか、prompt欠落をエラーとするかを決める。LLM条件を変えるため文書だけでは解決しない。 | `src/behavior_pattern_mining/llm/pattern_extractor.py`, `docs/operations/experiment_reproduction.md` |
| <a id="ki-13"></a>KI-13 | 遷移確率の解釈 | 遷移確率0.2以上はfrom状態内の相対頻度条件であり、「複数日で反復」を直接保証しない。 | 論文上の反復性の説明を維持するなら、別の根拠または指標が必要である。 | `src/behavior_pattern_mining/baselines/transition_probability.py`, `docs/research/paper_parameters.md` |
| <a id="ki-14"></a>KI-14 | 設定ファイルの適用範囲 | `dataset.input_csv` や一部の出力ディレクトリ設定を参照せず、スクリプト内の固定パスを使う入口がある。 | 設定を正本にするか、入口ごとの固定パスを互換仕様として維持するかを決める。 | `configs/default.yaml`, `scripts/run_build_network.py` |
| <a id="ki-15"></a>KI-15 | Arubaセンサ表現間の比較 | 2026-09-25から既定は物理センサ34個を個別に保持する `individual`、従来の10部屋・場所ラベル統合は `room` として選択できる。個別成果物は `aruba_individual_*`、従来成果物は互換の `aruba_*` に分離する。 | 特徴量数が違うため、hamming閾値の絶対値や既存のh=0採用結果を表現間で直接比較できない。各表現で同じ評価範囲・run集合による感度分析を行い、表現自体を実験条件として報告する必要がある。 | `configs/aruba_sensor_map*.json`, `scripts/run_build_network_from_labeled_casas.py`, `scripts/run_llm_extraction.py`, `scripts/evaluate_adl_labels.py` |

## 取り扱い

- 文書のみの作業では、表の挙動を「仕様」へ昇格させず、該当評価文書からこのIDを参照する。
- 実装を変更する場合は、影響する過去成果物、評価分母、K/h、run集合、CSV/JSON契約を先に特定する。
- 解消した項目は削除せず、採用した判断、変更日、対応するテストまたは結果移行方針を追記する。
