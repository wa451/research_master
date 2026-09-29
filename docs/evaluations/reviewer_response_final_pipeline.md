# 査読対応最終評価パイプライン

`scripts/run_reviewer_response_pipeline.py` は既存の GPT-5.6 Sol 成果物だけを読み取る集計器である。LLM API、抽出、前処理、状態生成を呼ばず、既存 `results/` を変更しない。`--output-dir` は空でない既存ディレクトリを拒否する。

```bash
uv run python scripts/run_reviewer_response_pipeline.py \
  --output-dir results/gpt-5.6-sol/reviewer_response/20260929_final
```

評価5では `(time_band, normalized_state_sequence)` を評価単位にし、比較可能な短系列・長系列ペアがない run の fragmentation は `N/A` とする。これは旧結果の値を変更せず、査読対応版の別集計でのみ適用する。

評価6は Full-pipeline と Strict Ablation を別表に保存する。Strict は両手法が完了した run の積集合だけを用いる。既存成果物には episode-level の再標本化単位がないため、5 run 集計値のブートストラップ CI は出力しない。

評価7は既存 validation 集計と best-condition manifest のみ、評価8は既存の固定共通 frequency bin のみを使う。評価9は完了した Hestia duration 実験の 14-day window を、評価10は未ラベル実宅ログの future recurrence を出力する。実宅について ADL F1 は作成しない。

人手評価セットの公開ファイルには手法名・run番号を含めない。対応表 `human_evaluation_blind_key_internal.csv` は評価者へ渡さず、採点後だけ `scripts/aggregate_human_evaluation.py` に渡す。
