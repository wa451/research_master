# SwitchBot Logger入力

`switchbot_logger` は収集・制御・Firestore保存を担い、ここでは研究用に固定したスナップショットだけを入力として使います。FirestoreやSwitchBotの認証情報をこのリポジトリへ移さないでください。

## エクスポート

`switchbot_logger` のルートで、取得期間を明示して実行します。`master-research/data/` はGit管理外のため、生の生活ログや生成物をコミットしません。

```bash
uv run --env-file .env --with-requirements requirements.txt \
  python scripts/export_firestore_to_aruba.py \
  --start "2026-09-01T00:00:00+09:00" \
  --end "2026-09-08T00:00:00+09:00" \
  --output data/data.txt \
  --report data/report.json \
  --research-output ../master-research/data/switchbot/events.csv
```

上記は次を生成します。期間ディレクトリはTokyo時刻の半開区間 `[start, end)` に対応します。

```text
data/switchbot/
└── 2026-09-01_2026-09-08/
    ├── events.csv
    └── manifest.json
```

`events.csv` はヘッダーなしの `date,time,sensor,value` 4列で、既存のCASAS入力と同じ読み込み契約です。`manifest.json` には取得元、期間、タイムゾーン、変換レポートを記録します。研究結果の再現時は、対象CSVと対応するmanifestを常に一組で保管してください。

## 分析

`master-research` のルートから、対象スナップショットを明示して実行します。

```bash
uv run python scripts/run_build_network.py \
  --input data/switchbot/2026-09-01_2026-09-08/events.csv
```

代表状態の意味づけはSwitchBotの実機センサーID（`M001`、`L001`など）に合わせて別途定義します。Arubaデータセット用の既存状態表・評価設定をそのままSwitchBotログへ混用しません。

パターン生成と、時間的に後の期間での再出現評価は評価10を使います。入力に正解ADLがないため、これはADL分類精度ではありません。

```bash
uv run python scripts/evaluate_10_switchbot.py \
  --snapshot data/switchbot/2026-09-01_2026-09-08
```

分割、指標、LLM APIの明示許可、出力契約は [評価10](../evaluations/evaluation_10_switchbot_holdout.md) を参照してください。
