# 評価10: SwitchBot実宅ログの時間ホールドアウト評価

## 目的と評価可能範囲

自宅で収集したSwitchBotイベントから生活行動候補の状態系列を生成し、時間的に後の未使用期間で同じ系列が再出現するかを評価する。入力に正解ADL区間がないため、本評価はADL解釈の正確さ、行動検出Precision/Recall、住人識別精度を測らない。結果は「学習期間から生成した系列の時間的安定性」の診断値として扱う。

入力は1つの固定スナップショットである。

```text
data/switchbot/2026-09-01_2026-09-08/
├── events.csv
└── manifest.json
```

`events.csv` はヘッダーなしの `date,time,sensor,value` 4列で、値は `ON/OFF`, `OPEN/CLOSE`, `PRESENT/ABSENT`, `1/0`, `TRUE/FALSE` を受理する。期間ディレクトリ名は `YYYY-MM-DD_YYYY-MM-DD` とし、現地時刻の完全なカレンダー日の半開区間を表す。

`manifest.json` はSwitchBot Loggerの研究出力schema version 1を検証する。`format=casas_csv`、列順、headerなし、timezone、`source.system=switchbot_logger`、offset付きの `source.start/end_exclusive`、`conversion_report.output_events` が必要である。期間はディレクトリ名と、出力件数はCSV行数と一致しなければならない。入力ファイルのSHA-256を中間snapshotへ保存し、後段実行時に変更を検出する。

## 分割と漏洩防止

既定ではスナップショットの完全なカレンダー日数の先頭70%（端数切捨て）をtrain、残りをtestにする。最低1日ずつ確保し、境界は現地時刻の0時に固定する。`--split-at` で境界を明示できる。

- センサー列、代表状態上位K、ハミング写像先、遷移ネットワーク、頻出系列はtrainだけから作る。
- testだけに現れるセンサーは、testがtrain表現の次元を変えないよう無視し、警告と件数を保存する。
- Sample-and-Holdと遅延OFFは時系列順の因果的処理であり、trainの末尾状態をtest開始時へ持ち越す。
- testの出現状況を見てK、h、最小出現回数、系列数を選び直した結果を未使用test性能として報告しない。
- 系列と遷移は日・時間帯の境界をまたいで数えない。

既定条件は `K=15`, `h=0`, 1秒サンプリング、遅延OFF 5秒、系列長2〜4、train最小2回、時間帯ごとの頻出上位20件である。評価10の新規条件であり、評価1〜9の既定値を変更しない。

## パターン生成

`frequency` はtrainの各日・各時間帯で連続2〜4状態を数え、`その他` を含まない系列を最小出現回数で絞って時間帯ごとの上位候補とする。同じ系列が複数時間帯に現れた場合は1件へ統合する。APIなしの既定runで必ず生成される。

`llm` は既存の提案手法と同じ時間帯別状態遷移JSONとpromptを使う。API呼出しは `--allow-api` を明示した `extract` または `run` だけで行う。入力hash、split、パラメータ、network JSONからfingerprintを作り、チェックポイントをfingerprint別に分離する。APIを許可せず `both` を採点した場合、LLM行は `missing` とし、0点としてfrequencyと混ぜない。保存済みのLLM JSONは `--llm-patterns` で指定できる。

## 指標

| 指標 | 定義 |
|---|---|
| `test_supported_pattern_fraction` | 生成パターンのうち、対応時間帯のtestに1回以上完全一致で出現した割合。 |
| `test_day_recurrence` | 各パターンについて、testの対象日数のうち1回以上出現した日数の割合。summaryはパターン等重み平均。 |
| `test_occurrences_per_day` | test出現回数を対象日数で割った値。 |
| `test_to_train_rate_ratio` | 1日あたりtest出現回数 / train出現回数。train側0回では空欄。 |
| `test_transition_coverage` | testの全隣接遷移位置のうち、その手法の1つ以上のパターンに覆われた位置の割合。重複被覆は1回と数える。 |

出現は重なりを許して数える。`test_supported_pattern_fraction` は一般的なPrecisionではなく、正解活動がなくても算出できる再出現診断である。

## 実行

APIなしでfrequency生成と評価を行う。

```bash
uv run python scripts/evaluate_10_switchbot.py \
  --snapshot data/switchbot/2026-09-01_2026-09-08
```

LLM系列も生成して両手法を採点する。

```bash
uv run python scripts/evaluate_10_switchbot.py \
  --snapshot data/switchbot/2026-09-01_2026-09-08 \
  --allow-api
```

段階実行もできる。

```bash
uv run python scripts/evaluate_10_switchbot.py --snapshot data/switchbot/2026-09-01_2026-09-08 --stage prepare
uv run python scripts/evaluate_10_switchbot.py --snapshot data/switchbot/2026-09-01_2026-09-08 --stage extract --allow-api
uv run python scripts/evaluate_10_switchbot.py --snapshot data/switchbot/2026-09-01_2026-09-08 --stage evaluate --method both
```

`--dry-run` はパスと実行段階だけを表示し、ファイルを作らない。Streamlitの「評価10」からも同じCLIを段階実行できる。

## 出力

| パス | 内容 |
|---|---|
| `output/10_switchbot/<期間>/preparation.json` | 入力hash、期間、split、パラメータ、件数、警告。 |
| `output/10_switchbot/<期間>/state_table.tsv` | trainだけで決めた代表状態表。 |
| `output/10_switchbot/<期間>/network/` | train時間帯別のLLM入力ネットワーク。 |
| `output/10_switchbot/<期間>/frequency_patterns.json` | trainで生成したfrequency系列。 |
| `output/10_switchbot/<期間>/llm/<fingerprint>/` | 同一入力・split・パラメータ・networkだけで再利用するLLM出力とチェックポイント。 |
| `output/10_switchbot/<期間>/{train,test}_state_segments.json` | 日・時間帯境界で分けた固定状態系列。 |
| `results/10_switchbot/<期間>/evaluation10_summary.csv` | 手法別の主要指標とstatus。 |
| `results/10_switchbot/<期間>/evaluation10_pattern_details.csv` | パターン別のtrain/test出現・日単位再現。 |
| `results/10_switchbot/<期間>/evaluation10_summary.json` | 再現条件、入力パス、summary、出力一覧。 |

`data/`, `output/`, `results/`, `picture/` は既存方針どおりGit管理外であり、評価10の状態表も `output/` 配下へ保存する。実宅ログや派生成果物をコミットしない。
