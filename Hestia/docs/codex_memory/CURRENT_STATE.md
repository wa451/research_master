# 現在のチェックポイント

更新: 2026-09-09。確認基点: `5106374`＋未コミットの追加評価実装。

- **実装済み**: `smart-home-sim experiment` のplan/generate/prepare/baseline/extract/evaluate。3住宅×8条件、観測ノイズ無効、前半固定表で後半を写像、系列回収と住人別真値による家全体ADL採点。詳細・場所は[追加評価ガイド](../noise_free_evaluation.md)。
- **既存コード**: Hestiaのengine/schemaおよび外部`master-research`は未変更。CLI登録・READMEのみ既存追跡ファイルを変更。開始時からの`AGENTS.md`と`paper_writeup_plan.md`の作業を保存。
- **確認済み**: 24条件の生成、完全出力ディレクトリの独立seed一致、正解漏洩防止、境界マッチ、重複住人ラベル、欠落run、APIデフォルト無効をテスト。必須5チェック成功、109 tests passed。
- **接続確認**: `outputs/noise_free_smoke/` に3住宅単身＋compact2人の各4日を生成。既存研究コードでprepare、頻度対照と採点、API dry-run、完了済み生成/準備の再利用を確認。LLM実呼出しは0回。
- **残る確認**: 有料LLM実行と本実験は未実施。まずガイドの呼出し数確認後、必要時のみ`extract --allow-api`。K=15でOtherが多い住宅があるので、前半側の表現診断と検出精度を分ける。共有micro-device検証の一般的問題は[KNOWN_ISSUES](KNOWN_ISSUES.md)。
- **次**: 実験規模・K等を確定して別出力で本評価を実行。過去の論文計画は履歴として残し、新実験の指標定義はガイドを正本とする。
