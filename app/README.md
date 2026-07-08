# Evaluation Dashboard

評価4、評価5、評価6、評価7をローカルGUIから実行するStreamlitアプリです。既存の評価ロジックは変更せず、画面上で既存CLIコマンドを組み立てて実行します。

## 起動

```bash
uv sync
uv run streamlit run app/streamlit_app.py
```

評価7では、代表状態数Kとハミング距離を複数指定して `scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py` を実行できます。不足している条件別ファイルがある場合は、一括実行ボタンで不足ファイル生成用の前段CLIだけを順に実行できます。評価7本体は、入力が揃ったことを確認してから個別ボタンで実行します。

詳細な使い方、評価ごとの設定項目、ステップ、ログ、結果比較は `docs/evaluation_streamlit_dashboard.md` を参照してください。
