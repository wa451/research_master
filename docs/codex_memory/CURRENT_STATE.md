# 現在のチェックポイント

更新日: 2026-09-12。今回の対象はSwitchBot実宅ログを使う評価10。リポジトリ全体の進捗ではない。

- **完了**: train期間だけで代表状態・時間帯別network・frequency/任意LLM系列を生成し、固定写像したtest期間で再出現を測る評価10を追加。仕様・入口・実装・テストは [eval10ルート](EVALUATION_ROUTES.md#eval10-switchbot実宅ログ) から辿る。
- **再現性**: SwitchBot Loggerのmanifest schema、期間、CSV行数、入力hashを検証。test-onlyセンサーはtrain表現から除外し、LLM checkpointは入力・split・条件・network fingerprint別に分離する。
- **確認**: 評価10の8テスト、全141テスト、CLI help、Streamlit import、Python構文、ローカルリンク、`git diff --check` に合格。実宅スナップショットは未配置のため未実行、Gemini APIも未呼出し。
- **既存の別作業**: 開始時から文書再配置、評価9/Hestia、Web等の未コミット変更あり。その全体の完了は推測・検証していない。
