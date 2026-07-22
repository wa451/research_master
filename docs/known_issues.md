# 既知の不一致・未解決事項

この文書は、現在の実装・テスト・設定・既存文書を照合して見つかった、研究上または互換性上の判断が必要な不一致を記録する。ここに記す挙動は、意図した仕様として確定したものではない。修正する場合は、過去結果への影響を確認し、研究条件として採用する挙動を明示してから、実装・テスト・文書を同時に更新する。

| ID | 対象 | 現在観測される挙動 | 影響と必要な判断 | 主な確認箇所 |
|---|---|---|---|---|
| <a id="ki-01"></a>KI-01 | 共通の `h` | `configs/default.yaml` と一部の無引数実行は `h=1`、論文採用条件と一部の正式評価手順は `h=0` を使う。 | 無引数実行を論文結果の再現手順とみなせない。各評価の正式条件と共通既定値を統一するか、用途別に維持するかを決める。 | `configs/default.yaml`, `scripts/run_all.py`, `docs/paper_parameters.md` |
| <a id="ki-02"></a>KI-02 | 評価2のrun | 外側のbatchはrun番号を切り替えるが、抽出処理は引数なしで呼ばれ、`run1` のcheckpointを参照し得る。 | 5 runが独立試行でない可能性がある。run別checkpointへ変更する場合は既存結果を再評価する。 | `src/behavior_pattern_mining/pipelines/llm_eval_batch.py`, `src/behavior_pattern_mining/llm/pattern_extractor.py` |
| <a id="ki-03"></a>KI-03 | 評価2の集計 | Excelにはrun別Precision/Recall/F1と平均が出力されるが、標準偏差や出力パターン数は出力されない。 | 文書上の研究要件に標準偏差を含めるか、現在の出力契約を正式とするかを決める。 | `src/behavior_pattern_mining/pipelines/llm_eval_batch.py` |
| <a id="ki-04"></a>KI-04 | 評価3の写像 | direct-log側は `--hamming-threshold` を受け取るが、系列への最終写像は完全一致のみで、提案手法の最近傍ハミング写像と一致しない。 | 比較の公平性に関わる。写像を共通化するか、異なる前処理を比較条件として採用するかを決める。 | `src/behavior_pattern_mining/llm/direct_log_extractor.py`, `src/behavior_pattern_mining/states/state_mapping.py` |
| <a id="ki-05"></a>KI-05 | 評価3の条件と集計 | 評価側の入力パスはK=15を固定し、頻度baselineはh=1を参照する。Excelはrun別行のみで平均行を持たない。 | 非既定K/hで異なる条件の成果物を比較し得る。可変条件の伝播方法と集計行の契約を決める。 | `src/behavior_pattern_mining/evaluation/direct_log.py`, `scripts/run_direct_log_baseline.py` |
| <a id="ki-06"></a>KI-06 | 評価4・6・7の状態系列 | パターン抽出は1秒Sample-and-Holdと遅延OFFを使う一方、ADL照合用状態系列の既定は `event-driven` である。 | 発生数・区間・指標が変わり得る。`network-equivalent` を正式条件にするか、異なる前処理を維持するかを決める。 | `scripts/evaluate_adl_labels.py`, `src/behavior_pattern_mining/evaluation/adl.py` |
| <a id="ki-07"></a>KI-07 | 評価4の期間・分類 | 既定はsplitなしで全期間を照合する。また `Bathroom`、`Personal_Hygiene`、`Bathing` は時間帯によらず `Wake-up` へ分類される。 | 記述評価か検出性能評価か、評価期間とtrain/test分離、ADL分類規則を確定する必要がある。 | `src/behavior_pattern_mining/evaluation/adl.py`, `scripts/evaluate_adl_labels.py` |
| <a id="ki-08"></a>KI-08 | 評価6のCLI既定 | 引数なしでは正式14日条件と異なるh=1側のパスや旧state-seriesパスを使い、`n_states` / `hamming_threshold` はsummaryでnullになり得る。 | 正式条件をCLI既定にするか、必須の明示引数として維持するかを決める。 | `scripts/evaluate_6_compare_adl_interpretation_set.py` |
| <a id="ki-09"></a>KI-09 | 評価6のrun集計 | 欠損runは手法ごとに独立して除外され、LLM使用量も手法別のcomplete runで平均される。ラベル別・時間帯別値は全run詳細をpoolして再集計する。 | pairedな共通run・run等重み・pooled集計のどれを正式な分母とするかを決める。 | `scripts/evaluate_6_compare_adl_interpretation_set.py`, `src/behavior_pattern_mining/evaluation/llm_usage.py` |
| <a id="ki-10"></a>KI-10 | 評価8の30日scope | `comparison_30days` は互換読込用として存在するが、scope名と入力detailsの期間を検証しない。14日scopeと既定出力先も共有する。 | 期間検証を追加するか、互換scopeのまま別出力先を運用上必須にするかを決める。 | `scripts/evaluate_8_frequency_stratified_adl_consistency.py` |
| <a id="ki-11"></a>KI-11 | 成果物管理 | `docs/artifact_policy.md` は固定した最終成果物の最小限管理を想定するが、現在の `.gitignore` は `output/`, `picture/`, `results/` を除外し、これら3ディレクトリに追跡成果物がない。 | Git管理か外部保管か、論文値の正本を決める。既存成果物を一括追加して解決しない。 | `.gitignore`, `docs/artifact_policy.md` |
| <a id="ki-12"></a>KI-12 | prompt fallback | 通常読む外部promptと、欠落時の埋め込みfallbackで許可ADLラベル集合が一致しない。 | fallbackを再現契約に含めるか、prompt欠落をエラーとするかを決める。LLM条件を変えるため文書だけでは解決しない。 | `src/behavior_pattern_mining/llm/pattern_extractor.py`, `docs/experiment_reproduction.md` |
| <a id="ki-13"></a>KI-13 | 遷移確率の解釈 | 遷移確率0.2以上はfrom状態内の相対頻度条件であり、「複数日で反復」を直接保証しない。 | 論文上の反復性の説明を維持するなら、別の根拠または指標が必要である。 | `src/behavior_pattern_mining/baselines/transition_probability.py`, `docs/paper_parameters.md` |
| <a id="ki-14"></a>KI-14 | 設定ファイルの適用範囲 | `dataset.input_csv` や一部の出力ディレクトリ設定を参照せず、スクリプト内の固定パスを使う入口がある。 | 設定を正本にするか、入口ごとの固定パスを互換仕様として維持するかを決める。 | `configs/default.yaml`, `scripts/run_build_network.py` |

## 取り扱い

- 文書のみの作業では、表の挙動を「仕様」へ昇格させず、該当評価文書からこのIDを参照する。
- 実装を変更する場合は、影響する過去成果物、評価分母、K/h、run集合、CSV/JSON契約を先に特定する。
- 解消した項目は削除せず、採用した判断、変更日、対応するテストまたは結果移行方針を追記する。
