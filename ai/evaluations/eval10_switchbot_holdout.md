# 評価10: SwitchBot実宅ログの時間ホールドアウト（AI向け詳細）

**正本:** [docs/evaluations/evaluation_10_switchbot_holdout.md](../../docs/evaluations/evaluation_10_switchbot_holdout.md)、[SwitchBot Logger連携](../../docs/integrations/switchbot_logger.md)
**CLI / 実装 / テスト:** `scripts/evaluate_10_switchbot.py` → `src/behavior_pattern_mining/evaluation/evaluation10_switchbot.py` → `tests/test_evaluation10_switchbot.py`

## 評価可能な主張

実宅SwitchBotイベントからtrainで生活行動候補の状態系列を作り、時間的に後の未使用testで同じ系列が再出現するかを測る。正解ADL区間が無いので、ADL解釈の正確さ、行動検出Precision/Recall、住人識別精度は**測らない**。結果はtrainで作った系列の時間的安定性の診断であり、再出現率を一般的なPrecision/Recallと呼ばない。

## 入力スナップショットと検証

入力は`data/switchbot/YYYY-MM-DD_YYYY-MM-DD/`の固定snapshotで、headerなし`events.csv`（`date,time,sensor,value`）と`manifest.json`を持つ。受理する値はON/OFF、OPEN/CLOSE、PRESENT/ABSENT、1/0、TRUE/FALSE。ディレクトリ名は現地時刻の完全カレンダー日の半開区間。

manifest schema v1は`format=casas_csv`、列順、headerなし、timezone、`source.system=switchbot_logger`、offset付きstart/end_exclusive、`conversion_report.output_events`を検証する。期間とCSV行数が一致しない入力は止める。入力SHA-256を中間snapshotへ保存し、後段で変更検知する。

## splitと漏洩防止

既定は完全日数の先頭70%（端数切捨て）をtrain、残りをtestへ、最低1日ずつ、現地0時境界。`--split-at`で明示可。

- センサー列、代表状態上位K、ハミング写像先、network、frequency候補はtrainだけで作る。
- testだけのsensorはtrain表現を変えないよう無視し、警告・件数を保存する。
- Sample-and-Holdと5秒遅延OFFは因果的に処理し、train末尾状態をtest開始へ持ち越す。
- testを見てK/h、最小出現回数、系列数を選び直したものを未使用test性能と報告しない。日・時間帯境界をまたいで系列/遷移を数えない。

既定条件はK=15、h=0、1秒sampling、遅延OFF 5秒、系列長2〜4、train最小2回、時間帯ごとのfrequency上位20。評価10固有の条件であり、評価1〜9を変更しない。

## 手法と指標

`frequency`はtrainの日×時間帯で2〜4状態の連続系列を数え、Otherを含まない系列を閾値で絞り上位候補にする。同一系列が複数帯にあれば統合する。APIなしで必ず生成する。

`llm`は既存提案手法と同じ時間帯別network JSON・promptを使う。input hash、split、パラメータ、network JSONのfingerprint別にcheckpointを分離する。API呼出しは`extract`または`run`での`--allow-api`だけ。許可せず`both`を採点するとLLMは`missing`で、0点としてfrequencyへ混ぜない。保存済みJSONは`--llm-patterns`で指定できる。

| 指標 | 定義 |
|---|---|
| `test_supported_pattern_fraction` | 対応時間帯のtestに完全一致で1回以上出る生成パターンの割合 |
| `test_day_recurrence` | 各patternでtest対象日のうち1回以上出た日割合。summaryはpattern等重み平均 |
| `test_occurrences_per_day` | test出現数 / test対象日数 |
| `test_to_train_rate_ratio` | 1日あたりtest出現 / train出現。train 0は空欄 |
| `test_transition_coverage` | test全隣接遷移位置のうち、手法の1つ以上のpatternで覆われる割合。重複被覆は1回 |

出現は重なりを許して数える。

## 実行・保存・監査

APIなしの標準実行は `uv run python scripts/evaluate_10_switchbot.py --snapshot data/switchbot/2026-09-01_2026-09-08`。LLMも生成する場合だけ`--allow-api`を追加する。段階実行は`--stage prepare`、`--stage extract --allow-api`、`--stage evaluate --method both`。`--dry-run`はパス・段階だけを表示し、ファイルを作らない。Streamlit評価10も同じCLIを段階実行する。

`preparation.json`、train state table、network、frequency patterns、train/test segmentsは`output/<model>/10_switchbot/<期間>/`に保持する。LLM fingerprint/checkpoint/usageと評価結果は`results/<model>/10_switchbot/<期間>/`。`evaluation10_summary.csv`（手法別指標・status）、`evaluation10_pattern_details.csv`（pattern別train/test出現・日別再現）、summary JSONを確認する。

中間の具体的なファイルは`output/<model>/10_switchbot/<期間>/`内の`state_table.tsv`、`network/`、`frequency_patterns.json`、`{train,test}_state_segments.json`である。LLMは`results/<model>/10_switchbot/<期間>/llm/<fingerprint>/`に保存され、同じ入力fingerprintでも別モデル間で共有しない。summary JSONには入力、split、パラメータ、method別summary、出力一覧を保存する。`preparation.json`には入力hash、期間、split、件数、test-only sensor等の警告を保存する。

実宅ログ、`data/`、`output/<model>/`、`results/<model>/`、`picture/`はGit管理外であり、内容・派生成果物をコミットしない。入力hash、test-only sensor、CSV/JSON契約、API opt-inを変更する場合は専用テストと正本も更新する。
