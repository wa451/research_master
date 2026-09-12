# 調査済み問題の索引

確認日: 2026-09-09。未解決の研究判断は [docs/known_issues.md](../known_issues.md) が正本。ここでは再調査を避ける入口だけを保持する。初回登録では既存結果の再実験はしていない。

## 未解決（既存docsで確認）

| 症状・判明している要因 | 参照先・残る判断 |
|---|---|
| 無引数実行が正式条件とずれる。共通h=1／論文h=0、CLI固定パス・設定未参照がある。 | [KI-01](../known_issues.md#ki-01), [KI-05](../known_issues.md#ki-05), [KI-08](../known_issues.md#ki-08), [KI-14](../known_issues.md#ki-14): 既定値・条件伝播の方針。 |
| 評価2の独立runが疑わしい。batchから引数なし抽出でrun1 checkpointを再利用し得る。 | [KI-02](../known_issues.md#ki-02), [KI-03](../known_issues.md#ki-03): checkpointと集計契約。 |
| 比較法・ADL照合の入力条件が揃わない。direct-log最終写像は完全一致、ADL系列の既定はevent-driven。 | [KI-04](../known_issues.md#ki-04), [KI-06](../known_issues.md#ki-06): 正式な比較前処理。 |
| ADLの期間・分類・run分母に解釈差が残る。 | [KI-07](../known_issues.md#ki-07), [KI-09](../known_issues.md#ki-09): split、ラベル規則、paired/pooled集計。 |
| 旧30日scopeは入力期間未検証／外部promptとfallbackのラベル差／成果物保管方針の不一致／遷移確率だけでは複数日の反復を保証しない。 | [KI-10](../known_issues.md#ki-10), [KI-12](../known_issues.md#ki-12), [KI-11](../known_issues.md#ki-11), [KI-13](../known_issues.md#ki-13)。 |

これらの修正試行・効果がなかった方法は正本に記録されていないため不明。推測で補わず、文書の注意書きを実装修正済みと扱わない。

## 再発を避ける実装済み対策

- **評価8の出現数重複**: 系列一致で別IDの出現を取得すると頻度・重みを誤る。現行 `scripts/evaluate_8_frequency_stratified_adl_consistency.py::attach_own_id_occurrences()` はown-ID取得→物理区間一意化→method/run内で辞書順最小IDへ所有権を付与する。ID内だけの重複除去ではID間共有を解消できないため、系列fallbackを復活させない。
- 検証先: `tests/test_evaluation8_frequency_stratified.py`、`occurrence_weight_validation()`。一意出現数と重み総和の一致を確認する。過去結果の再検証状況は今回未確認。詳細: [評価8の出現数定義](../evaluation_8_frequency_stratified_adl_consistency.md)。
