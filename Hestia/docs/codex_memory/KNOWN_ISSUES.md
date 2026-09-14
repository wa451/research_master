# 調査済みの問題・注意点

用途: 原因・試行の結論だけを残す。以下の数値は既存レポートの条件による過去の測定で、今回の再測定ではない。記録のない失敗策は推測しない。

| 状態・症状 | 原因／試したこと・限界 | 残件・参照 |
|---|---|---|
| 未達: realisticの密度・ADL内変化・遷移数 | 因果的な移動・操作だけでは実Arubaの短周期再発火を表せない。ゾーン・micro・副次活動を追加し3候補で校正したが、密度10倍・変化/遷移各3倍の目標には不足 | 改善自体はあり「無効」ではない。さらなる校正は未実施。[制約](../limitations.md)、[3候補の結果](../../reports/calibration_history.md) |
| 指標差: Other率がnetworkと再構築seriesで異なる | 集計境界の違い。同じK/h/保持/OFF条件でも26.12%と16.59%になり、条件統一だけでは一致しない | 比較元と同じnetwork JSON定義を使い、seriesは別診断として記録。[校正方法](../calibration_method.md) |
| 既存parserの制約: 多人数の同名ADL境界 | 既存研究parserはresident IDを真値キーにしない。新しい`experiment`ではHestiaの真値CSVをresident/activity別に読み、家全体の複数ADL集合で採点して回避。既存parser自体は未変更 | 新実験は[追加評価ガイド](../noise_free_evaluation.md)。従来経路の制約は[limitations](../limitations.md) |
| 未修正: 共有micro-deviceの終了を検証器が誤検出 | `Device.transition`が状態・属性の不変時にイベントを省略し、micro利用の終了をCSVから復元できない場合がある。新実験では共有機器を活動単位、microを移動・滞在に限定し検証を維持 | 一般的なmicro-device競合の修正は別タスク。[追加評価の制約](../noise_free_evaluation.md) |
| 文書の陳腐化: 古い監査にGUI・ノイズ・開始時刻揺らぎが未実装とある | `reports/semantic_audit.md`は拡張前の記述を含む。現行`studio.py` / `imperfections.py` / `schema.py`には対応機能がある | 既存文書は今回変更せず。機能の有無は現行コードと[architecture](../architecture.md)で確認。`docs/paper_writeup_plan.md`にもデバイス種別数など古い記述がある |

修正済みの再発防止（利用前状態復元・CASAS境界）は[DECISIONS.md](DECISIONS.md)に集約。モデル全般の対象外機能は[limitations.md](../limitations.md)を参照。
