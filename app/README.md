# Evaluation Dashboard

評価4、評価5、評価6、評価7、評価8をローカルGUIから実行するStreamlitアプリです。既存CLIコマンドを画面上で組み立てて実行します。

## 起動

```bash
uv sync
uv run streamlit run app/streamlit_app.py
```

一括実行では、不足ファイル生成のみ、不足ファイル生成 + 評価本体、全ステップ再実行を選べます。

評価7では、代表状態数Kとハミング距離を複数指定して `scripts/evaluate_7_parameter_sensitivity_adl_interpretation.py` を実行できます。不足している条件別ファイルがある場合は、一括実行で不足分を生成してから評価7本体まで続けて実行できます。

評価5では、Useful non-redundant pattern rate、Fragmentation rate、Contextless useless rateを表示できます。transition_probability baselineとfragmentation閾値を画面から指定できます。low-information閾値は互換引数として残りますが、診断値だけを保存する現評価には影響しません。
評価5の `runs` は既定で5です。提案手法を5回分評価し、平均summaryとrun別summaryを確認できます。frequency / rule / FP-Growth / transition_probability baselineはrunに依存しないため最初の評価runだけで計算し、FP-Growth / transition_probability の生成済みパターンは修正前のキャッシュと分離した `output/5_adl_correspondence_baselines_fixed/` から再利用します。

結果タブでは、各評価READMEの「結果の読み方」に沿って表示ファイルを並べ、CSVは表示するカラムを選択できます。

詳細な使い方、評価ごとの設定項目、ステップ、ログ、結果比較は `docs/evaluation_streamlit_dashboard.md` を参照してください。

## 評価9: Hestia合成ログ

Hestiaは `master-research/Hestia/` に配置する。Webアプリの「評価9」または `uv run python scripts/evaluate_9_hestia.py` でログ生成から採点まで実行できる（既定はAPIなし）。配置・入力契約・指標・実行方法は [評価9のガイド](../docs/evaluation_9_hestia.md) を参照。
