# 調査済み問題の索引

初回確認: 2026-09-09。結果読解・KI-08の索引更新: 2026-10-01。未解決の研究判断は [docs/research/known_issues.md](../docs/research/known_issues.md) が正本。ここでは再調査を避ける入口だけを保持する。初回登録では既存結果の再実験はしていない。

## 未解決（既存docsで確認）

| 症状・判明している要因 | 参照先・残る判断 |
|---|---|
| 無引数実行が正式条件とずれる。共通h=1／従来掲載h=0、CLI固定パス・設定未参照がある。 | [KI-01](../docs/research/known_issues.md#ki-01), [KI-05](../docs/research/known_issues.md#ki-05), [KI-14](../docs/research/known_issues.md#ki-14): 既定値・条件伝播の方針。現行掲載条件は結果manifestと照合する。 |
| 評価2の独立runが疑わしい。batchから引数なし抽出でrun1 checkpointを再利用し得る。 | [KI-02](../docs/research/known_issues.md#ki-02), [KI-03](../docs/research/known_issues.md#ki-03): checkpointと集計契約。 |
| ADLの期間・分類・run分母に解釈差が残る。 | [KI-07](../docs/research/known_issues.md#ki-07), [KI-09](../docs/research/known_issues.md#ki-09): split、ラベル規則、paired/pooled集計。 |
| 旧30日scopeは入力期間未検証／外部promptとfallbackのラベル差／成果物保管方針の不一致／遷移確率だけでは複数日の反復を保証しない。 | [KI-10](../docs/research/known_issues.md#ki-10), [KI-12](../docs/research/known_issues.md#ki-12), [KI-11](../docs/research/known_issues.md#ki-11), [KI-13](../docs/research/known_issues.md#ki-13)。 |

これらの修正試行・効果がなかった方法は正本に記録されていないため不明。推測で補わず、文書の注意書きを実装修正済みと扱わない。

## 採用済み仕様

- [KI-04](../docs/research/known_issues.md#ki-04): 評価3・6のLLM-onlyは提案手法と同じ `map_vector_to_state` による完全一致→閾値内Hamming最近傍→`その他` の写像を使う。旧LLM-only成果物は再利用しない。
- [KI-06](../docs/research/known_issues.md#ki-06): 評価6・7の正式workflowは `network-equivalent`、network構築と同じ遅延OFF平滑化、Day 1–14生成／Day 15–154 validation／Day 155–220 testを使う。CLI単体の `event-driven` 既定は互換用途である。
- [KI-08](../docs/research/known_issues.md#ki-08): 正式評価6holdoutは評価7 best-condition manifestから条件・期間・canonicalパスを解決する。manifestなしはK/h明示が必要。legacy互換と区別する。

## 結果閲覧・考察・執筆の注意

- **列名と集計の差**: 既存overviewの `FRR_mean` は主指標FRRでなく日単位再現率を表示している。評価10専用表の `test_supported_pattern_fraction_mean` を使う。評価5のペアなしfragmentation=0と査読対応版N/Aも混在させない。正本・出典: [結果の読み方](../docs/research/results_guide.md)。結果ファイル自体は修正していない。
- **未実施・未決定**: 既存監査ではFableの正式評価7集計がなく、共通条件を各モデル最適条件と呼べない。人手評価は62サンプル準備まで、構造妥当性スコアは未実施。掲載集合・主モデルは未決定。根拠と次の判断: [結果入口](../docs/research/README.md)、[執筆作業表](../docs/research/manuscript_plan.md)。

## 再発を避ける実装済み対策

- **評価8の出現数重複**: 系列一致で別IDの出現を取得すると頻度・重みを誤る。現行 `scripts/evaluate_8_frequency_stratified_adl_consistency.py::attach_own_id_occurrences()` はown-ID取得→物理区間一意化→method/run内で辞書順最小IDへ所有権を付与する。ID内だけの重複除去ではID間共有を解消できないため、系列fallbackを復活させない。
- 検証先: `tests/test_evaluation8_frequency_stratified.py`、`occurrence_weight_validation()`。一意出現数と重み総和の一致を確認する。過去結果の再検証状況は今回未確認。詳細: [評価8の出現数定義](../docs/evaluations/evaluation_8_frequency_stratified_adl_consistency.md)。
