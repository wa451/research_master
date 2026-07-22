# Refactoring Record and Next Steps

この文書は、完了した構造整理の設計判断と、今後の段階的な改善候補を記録する。現在の実行方法は [README.md](../README.md)、責務配置は [code_inventory.md](code_inventory.md) を正本とする。

## 維持する原則

- 研究ロジック、前処理、評価指標、閾値、split、run集計、LLM条件を構造整理のついでに変更しない。
- CLI、既定値、出力パス、CSV列、JSONキー、既存成果物との互換性を回帰テストで固定する。
- 生データ、秘密情報、既存結果は移動・削除・上書きしない。
- [known_issues.md](known_issues.md) の未確定挙動を、リファクタリング時に暗黙の仕様へしない。

## 完了した構造整理

| 領域 | 現在の配置 | 判断 |
|---|---|---|
| 設定 | `configs/default.yaml`, `experiment_config.py` | 既存モジュール互換のため定数公開レイヤーを残した。 |
| 実行入口 | `scripts/` | 新しい実行はscriptsから行う。後段評価にはまだ実処理が残る。 |
| 実装本体 | `src/behavior_pattern_mining/` | baseline、LLM、evaluation、pipeline、可視化をパッケージ化した。 |
| 状態ベクトル前処理 | `src/behavior_pattern_mining/data/state_vectors.py` | Sample-and-Hold、遅延OFF、連続状態圧縮を純粋関数へ分離した。 |
| 代表状態写像 | `src/behavior_pattern_mining/states/state_mapping.py` | 共通の読み込み・ハミング写像処理を分離した。 |
| 遷移集計 | `src/behavior_pattern_mining/network/transitions.py` | 出現回数、遷移確率、滞在時間を純粋関数へ分離した。 |
| 描画と出力統括 | `src/behavior_pattern_mining/visualization/state_transition_visualizer.py` | 出力契約維持のため統括クラスを残した。 |
| LLM prompt | `prompts/` | 外部ファイルを実行時に読み、既存fallbackは互換用に残した。 |
| 回帰テスト | `tests/` | 前処理、写像、遷移、評価4〜8、LLM応答解析の固定テストを追加した。 |

`state/`, `picture/`, `output/`, `results/` は現在の契約に含まれるため、統合ディレクトリへの一括移動は行っていない。

## 今後の小さな改善候補

1. 評価5〜8の大きなscriptsから、集計・schema検証・入出力を一つずつ `src/behavior_pattern_mining/evaluation/` へ移す。
2. `state_transition_visualizer.py` のデータ形式別読み込みと描画を、PNG/EPS/JSON/状態表の回帰テスト追加後に分ける。
3. `experiment_config.py` の利用箇所を減らす場合は、同じ既定値とパス解決を保つ互換層を段階的に置き換える。
4. CLIごとに固定された入力・出力パスと設定ファイルの適用範囲を棚卸しする。方針決定までは [KI-14](known_issues.md) として扱う。
5. LLM promptの外部版とfallbackの差を研究条件として解消する。現在は [KI-12](known_issues.md) のため文言だけを同期しない。

## 着手前に必要な回帰確認

- 小規模fixtureで前処理、同一状態圧縮、代表状態写像、遷移確率を比較する。
- 対象CLIの引数・既定値と、出力CSVヘッダー・JSONキー・ファイル名を固定する。
- LLM処理はAPIを大量実行せず、保存済み応答またはモックでprompt選択と応答解析を確認する。
- ADL評価は分母、欠損run、train/test境界、時間帯境界をテストする。

## 高リスク領域

- `picture/*/state_transition_*.json` はLLM入力であり、キー、順序、丸め、ノード・エッジ選択の変更が結果へ波及する。
- 代表状態写像、`h`、状態系列前処理は複数評価の入力を変える。
- LLM checkpoint、run番号、欠損run処理は平均・標準偏差の母集団を変える。
- `output/`, `picture/`, `state/`, `results/` の移動や再生成は過去結果との対応を失わせる。

これらを変更する作業では、対応する評価文書、[artifact_policy.md](artifact_policy.md)、[known_issues.md](known_issues.md) を先に確認する。
