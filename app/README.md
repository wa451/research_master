# Evaluation Dashboard

評価4〜10とHestia StudioをローカルGUIから利用するStreamlitアプリです。評価は既存CLIコマンドを画面上で組み立てて実行し、Studioは同一プロセス内でHestiaを直接利用します。

## 起動

```bash
uv sync
uv run streamlit run app/streamlit_app.py
```

macOSでは、リポジトリ直下の `start_dashboard.command` をダブルクリックして同じアプリを起動できる。Dockからワンクリックで起動したい場合は、同じ階層にある `master-research-dashboard.app` をDockへドラッグする。この `.app` はリポジトリ直下の `uv` 環境から直接ダッシュボードを起動するため、リポジトリ直下に置いたままにする。`.app` をダブルクリックすると、このリポジトリの既存ダッシュボードだけを停止して最新ソースで再起動し、既定のブラウザを開く。ポート8501を別アプリが使用中の場合は停止せずエラーを表示する。

一括実行では、不足ファイル生成のみ、不足ファイル生成 + 評価本体、全ステップ再実行を選べます。

評価7は14日・K=`10,15,20,25,30,35,40`・hamming=`0,1,2,3` の全28条件を各5 runで実行します。不足している条件別ファイルがある場合は、一括実行で不足分を生成してから評価7本体まで続けて実行できます。

実行LLMの既定は GPT-5.6 Sol です。評価7画面の「API疎通・JSON形式テスト」では、明示許可後に選択した1条件・1 run・1時間帯を実APIへ1回だけ送信し、通常抽出と同じプロンプトへの初回応答が厳密なJSON契約を満たすか確認できます。テスト結果は `results/<model>/api_smoke_tests/` に分離され、正式な評価7成果物には影響しません。

評価5では、Useful non-redundant pattern rate、Fragmentation rate、Contextless useless rateを表示できます。transition_probability baselineとfragmentation閾値を画面から指定できます。low-information閾値は互換引数として残りますが、診断値だけを保存する現評価には影響しません。
評価5の `runs` は既定で5です。提案手法を5回分評価し、平均summaryとrun別summaryを確認できます。frequency / rule / FP-Growth / transition_probability baselineはrunに依存しないため最初の評価runだけで計算し、FP-Growth / transition_probability の生成済みパターンは修正前のキャッシュと分離した `output/5_adl_correspondence_baselines_fixed/` から再利用します。

結果タブでは、各評価READMEの「結果の読み方」に沿って表示ファイルを並べ、CSVは表示するカラムを選択できます。

詳細な使い方、評価ごとの設定項目、ステップ、ログ、結果比較は `docs/operations/dashboard.md` を参照してください。

## 評価9: Hestia合成ログ

Hestiaは `master-research/Hestia/` に配置する。Webアプリの「評価9」では、compact / corridor / branched の部屋と接続を図で確認できる。**Hestia Studio** はComponents v2で同じStreamlitページへ直接統合され、別サーバー・別ポート・iframeなしで、3住宅を切り替えながら接続、センサー、デバイスの所属・配置を編集して `Hestia/scenarios/` にYAML保存できる。間取りは論文用SVGまたは3200 × 2000 pxのPNGとして書き出せる。保存したカスタムシナリオと画像は評価9の本実験planへ自動反映されない。同画面または `uv run python scripts/evaluate_9_hestia.py` でログ生成から採点まで実行できる（既定はAPIなし）。配置・入力契約・指標・実行方法は [評価9のガイド](../docs/evaluations/evaluation_9_hestia.md) を参照。

## 評価10: SwitchBot実宅ログ

Webアプリの「評価10」から、固定スナップショットの入力検証、train側パターン生成、test側再出現評価を段階実行できます。LLM抽出は画面で明示許可した場合だけ実行します。指標と分割契約は [評価10のガイド](../docs/evaluations/evaluation_10_switchbot_holdout.md) を参照。
