# 考察メモ

[結果閲覧の入口](README.md)に戻る。2026-10-01時点の保存済み比較表から、観測事実と検討する解釈を分けた執筆用メモです。数値は読みやすさのため小数第4位に丸めています。原表はリンク先にあり、掲載時には採用する結果集合・分母・標準偏差を確認します。

## 1. ADL集合の整合性

| モデル | Full LLM-only F1 | Full Proposed F1 | Strict LLM-only F1 | Strict Proposed F1 | Strict paired ΔF1（平均±SD） |
|---|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | 0.6445 | 0.7840 | 0.6624 | 0.8639 | 0.2015 ± 0.0892 |
| Claude Fable 5 | 0.6017 | 0.7705 | 0.5860 | 0.7592 | 0.1732 ± 0.0732 |

出典: [Full](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval6_full.md)、[Strict](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval6_strict.md)、[paired ΔF1](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval6_strict_delta_f1.md)。F1は `mean_multilabel_f1`、各比較は5 runです。

**観測:** 両モデルでProposedの平均F1がLLM-onlyを上回り、Strictのpaired ΔF1平均も正です。

**考察の仮説:** STNにまとめた入力が、ADLと対応する系列の選択・解釈を助ける可能性があります。Strict比較はこの仮説を議論する根拠になります。

**追加で見る点:** Precision/Recallのどちらに差があるか、出現被覆率や予測欠損が差を説明するか、[run別差](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval6_strict_by_run.md)が一部のrunに偏るか。モデル一般に対する優越性や統計的有意差は、この平均値だけでは結論づけません。

## 2. パターン品質と抽出量

**観測:** [評価5](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval5.md)のProposedのUseful non-redundant率はSol 0.7306、Fable 0.7248。rule_medium/strongは0.8000、遷移確率法は0.6122です。有用パターン数はそれぞれSol 11.8、Fable 15.8、rule_medium/strong 16、遷移確率法30です。

**考察の仮説:** 出力を絞る方法と有用な候補を多く残す方法で役割が違う可能性があります。比率と絶対数、系列長、無文脈率を併記すると、提案手法の得失を説明できます。

**追加で見る点:** Proposedは5 run、決定的baselineは1 runという違いがあります。またProposedのfragmentation=0には比較可能ペア数=0の行が含まれます。[査読対応方針](../evaluations/reviewer_response_final_pipeline.md)ではこの場合N/Aなので、0を「断片化しない証明」として使わないでください。評価5の自動ADL対応を、人の説明納得度と同一視しません。

## 3. 条件選定と頻度

**観測:** [評価7](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval7.md)ではSolの `K=10,h=2` がvalidationのF1 0.7831でrank 1、`K=10,h=3` が0.7758でrank 2です。

**考察の仮説:** 代表状態数と写像の許容幅の組合せが、状態の情報量と系列の再出現性に関係している可能性があります。全28条件を見て、近傍条件の傾向とrunのばらつきを説明します。

**追加で見る点:** 部屋統合表現の旧K/h条件と直接比較しないこと。Fableでは正式評価7の集計がないため、両モデルの最適K/hが同じとは主張しません。[評価8](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval8.md)は固定bin・帯ごとの母数・conditional/end-to-endを揃えてから、低頻度側の出現なしと高頻度側の整合性を検討します。

## 4. 合成ログでの限界

**観測:** [評価9の14日train・7日test](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval9.md)ではSolのF1はcompact_base 0.0151、corridor_base 0.1330、Fableはcompact_base 0.0000、corridor_base 0.1442です。性能は家屋条件によって異なります。

**考察の仮説:** 家屋構造、状態の表現、正解系列との対応が性能差に関係している可能性があります。Arubaのラベル集合F1とHestiaの系列F1は定義が異なるため、数値を直接比較して「何倍悪化」とは書きません。

**追加で見る点:** 条件×seed×run、正解系列数、抽出数、target episode被覆率、Otherへの写像、断片化を見ます。これらを調べる前に、低F1の原因をLLMだけに帰属させないでください。

## 5. 実宅ログでの将来再現性

| モデル | 平均抽出数 | testで1回以上出た割合 FRR（平均±SD） | test日単位再現率（平均±SD） |
|---|---:|---:|---:|
| GPT-5.6 Sol | 1.0 | 0.1250 ± 0.2500 | 0.0500 ± 0.1000 |
| Claude Fable 5 | 9.4 | 0.3889 ± 0.0885 | 0.2487 ± 0.0633 |

出典: [評価10専用表](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval10.md)。FRRは `test_supported_pattern_fraction_mean` です。

**観測:** 固定条件の今回の実宅ログではFableのFRRと日単位再現率が高く、抽出数も多くなっています。

**考察の仮説:** モデルによる抽出量・系列長・時間帯の選択の違いが、未来での再出現に関係する可能性があります。[時間帯別](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval10_time_band.md)・[系列長別](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/tables/table_model_comparison_eval10_length.md)とrun別に掘り下げます。

**追加で見る点:** 正解ADLがないため、行動解釈の正しさは未評価です。抽出が少ないrunと空のrunの扱い、共通条件の出所、データ期間、単一住宅という範囲を明記します。[overviewのFRR列名の問題](results_guide.md)にも注意してください。

## 6. 現時点で本文に残す限界

人手による説明評価は採点待ち、Fable固有のK/h探索は未確認、既存成果物では比較可能な構造妥当性スコアが未実施です。5 runは住宅や被験者の数ではありません。これらを[論文作業表](manuscript_plan.md)で管理し、完了済みと未実施を区別します。
