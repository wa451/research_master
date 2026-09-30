# 結果を読む・考察を書く

実行済みの評価5〜10を読む入口です。結果の数値と、その数値から論文で述べられる範囲を一緒に確認します。確認日: 2026-10-01。

## 最初に開くもの

| 目的 | 入口 |
|---|---|
| 表を検索・モデル別に絞り込んで読む | リポジトリ直下の `start_research_browser.command` をダブルクリック。端末では `python3 support/research_browser.py --open` |
| プロジェクト全体を知る | [研究の概要](../overview.md) → [パイプライン](../architecture/pipeline.md) |
| 評価ごとの目的と結果の場所を確認する | [評価結果の読み方](results_guide.md) |
| 数値をもとに考察を始める | [考察メモ](discussion_notes.md) |
| 論文の構成と残作業を決める | [論文執筆の作業表](manuscript_plan.md) |
| モデル比較の根拠を確認する | [既存比較報告](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/comparison/model_comparison_summary.md)、[比較条件の監査](../../results/model_comparison/gpt-5.6-sol_vs_claude-fable-5/comparison/comparability_audit.md) |

閲覧ビューは保存済みMarkdown表を読み、見せる列と行だけを変えます。API呼び出し・再集計・評価結果の保存は行いません。CSVダウンロードは既存の比較CSVをそのまま渡します。数値の桁を丸めず、空欄・`None`・`N/A` は元資料どおり表示します。

## 現在の結果の位置付け

- 主な比較対象は GPT-5.6 Sol と Claude Fable 5。[凍結manifest: Sol](../../results/final_evaluation_snapshot/gpt-5.6-sol/snapshot_manifest.json)、[Fable](../../results/final_evaluation_snapshot/claude-fable-5/snapshot_manifest.json) はJST 2026-10-01に作成された結果集合を記録しています。
- Solの評価7は個別センサ表現、14日生成、28条件×5 runのvalidationです。選定条件は `K=10, h=2`。評価6はDay 155–220のtestを使います。
- Fableの正式な評価7集計は既存監査で未確認です。評価6 Strict・評価10などはSolで選んだ条件を利用しており、「各モデルで最適化した比較」とは区別します。
- 人手評価は62サンプルのセットが準備されていますが、[査読対応版rerun3の記録](../../results/gpt-5.6-sol/reviewer_response/20260929_final_rerun3/reviewer_response_evaluation_summary.md)では採点待ちです。

この入口があることは、掲載する結果集合の決定や統計的有意差の確認を意味しません。結果集合の採用は[作業表](manuscript_plan.md)で決め、指標・条件の定義は各評価文書とmanifestで確認します。

## 文書と保存済み結果の役割

`docs/evaluations/` は評価定義と実行手順、`results/model_comparison/` はモデル比較用の既存表、`results/<model>/` は元の評価・run別出力、`results/final_evaluation_snapshot/` は凍結時の対応関係とhashです。`results/<model>/reviewer_response/` は査読対応版の別集計で、元集計と一部の取り扱いが異なります。

[paper_parameters.md](paper_parameters.md)にはGemini・K=15/h=0など従来の掲載条件が残っています。現在の個別センサ・holdout・複数モデル結果へ、その条件をそのまま当てはめないでください。[既知の不一致](known_issues.md)も参照し、掲載条件表は採用する結果のmanifestに合わせて確定します。

## 閲覧入口の更新

結果を追加したら [result_catalog.json](result_catalog.json) に既存Markdown表の相対パス、評価の説明、最初に表示する列を追加します。`python3 support/research_browser.py --check` で参照ファイルと列名を検査できます。別マシンで評価結果を配置していない場合は、ビューに「未配置」と表示されます。

ポートの変更は `--port 8522`、終了は起動した端末で `Ctrl+C` です。既存のStreamlitダッシュボードは実験実行用として引き続き利用できます。
