# 現在のチェックポイント

更新: 2026-09-14。未コミットの評価9追加実装を確認基点とする。

- **実装済み**: `smart-home-sim experiment` のplan/generate/prepare/baseline/extract/evaluate、明示target、代表状態空間のcanonical gold、exact P/R/F1、gold基準fragmentation。定義と配置は[追加評価ガイド](../noise_free_evaluation.md)。
- **本実験plan**: compact / corridor / branchedごとにbaseとlarge variabilityだけを明示。3住宅×2条件×seed 11/22/33 = 18ログ、各train 7日/test 7日、LLM 3反復。汎用`default_conditions()`の24条件と2種類のpilotは維持。
- **確認済み**: plan parseで6 condition・18 run、pilotファイルhash不変。format/lint、`src`・`tests`の型検査、Hestia 115 tests、親repo評価9 7 testsが成功。controlled pilotのAPIなし接続確認済みで、LLM実呼出しは0回。
- **残る確認**: 有料LLM実行と18ログの本実験生成・評価は未実施。実行前にガイドの最大216モード呼出しと費用を確認し、必要時のみ`extract --allow-api`を使う。K=15のOther比率と検出精度は分けて読む。共有micro-deviceの一般的問題は[KNOWN_ISSUES](KNOWN_ISSUES.md)。
- **次**: 新しい実験ディレクトリで本実験を実行する。過去の論文計画は履歴として残し、現行の条件・指標定義はガイドを正本とする。
