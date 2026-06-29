# Refactoring Plan

## 方針

今回の整理では、研究ロジックと既存出力を壊さないことを優先する。大規模なコード分割や結果ファイル移動は、現状台帳と再現手順を作った後に段階的に行う。

## 今回実施した安全な整理

- `docs/` を追加し、コード台帳、パイプライン、再現手順、リファクタリング計画を配置。
- `PAPER_PARAMETERS.md` を `docs/paper_parameters.md` へ移動。
- `configs/default.yaml` を追加し、`experiment_config.py` 経由で主要設定値を読むようにした。
- `prompts/` を追加し、LLM抽出スクリプトがプロンプトを外部ファイルから読むようにした。
- `scripts/`, `outputs/`, `src/`, `tests/` を追加し、将来の移行先を明示。
- 既存の `data/`, `state/`, `picture/`, `output/` は移動しない。現在の実行コマンドが壊れるため。

## 追加実施したパッケージ化整理

- 主要な実装本体を `src/behavior_pattern_mining/` 配下へ移した。
- 主要スクリプトの実装本体を `src/behavior_pattern_mining/` に移し、実行入口を `scripts/` に集約した。
- 新しい実行入口を `scripts/` に追加した。
- 旧 `utils/` は参照がなくなったため削除した。
- `pyproject.toml` のwheel対象を `src/behavior_pattern_mining` パッケージに合わせた。

### 新しい主な実行入口

```bash
uv run python scripts/run_all.py
uv run python scripts/run_build_network.py
uv run python scripts/run_baselines.py
uv run python scripts/run_llm_extraction.py
uv run python scripts/run_llm_eval_batch.py
uv run python scripts/run_direct_log_baseline.py
uv run python scripts/run_evaluation.py
uv run python scripts/run_groundedness.py
uv run python scripts/evaluate_condition_metrics.py
uv run python scripts/evaluate_adl_labels.py
```

## 推奨フォルダ構成

```text
project/
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── configs/
│   └── default.yaml
├── data/                  # Git管理外の入力データ
├── docs/
│   ├── code_inventory.md
│   ├── pipeline.md
│   ├── refactoring_plan.md
│   ├── experiment_reproduction.md
│   └── paper_parameters.md
├── prompts/
│   ├── pattern_extraction_prompt.md
│   ├── direct_log_pattern_extraction_prompt.md
│   └── groundedness_check_prompt.md
├── scripts/               # 将来のCLI入口
├── src/
│   └── behavior_pattern_mining/
│       ├── data/
│       ├── states/
│       ├── network/
│       ├── llm/
│       ├── baselines/
│       ├── evaluation/
│       └── visualization/
├── state/                 # 現行の代表状態テーブル出力
├── picture/               # 現行の図・ネットワークJSON出力
├── output/                # 現行のパターン・評価出力
├── outputs/               # 将来の統合出力先
├── support/
├── tests/
```

## 移行状況

以下は当初の移行先候補と、現在の移行済みファイルの対応です。

| 現在 | 移行先候補 | 注意 |
|---|---|---|
| 前処理・可視化 | `src/behavior_pattern_mining/visualization/state_transition_visualizer.py` | 現在は大きな1ファイルのまま移動済み。次段階で `data/`, `states/`, `network/`, `visualization/` へ分割する。 |
| 頻度ベースライン | `src/behavior_pattern_mining/baselines/frequency.py` | 移動済み。状態マッピング共通処理は `src/behavior_pattern_mining/states/state_mapping.py` に追加済み。 |
| 遷移確率ベースライン | `src/behavior_pattern_mining/baselines/transition_probability.py` | 移動済み。 |
| 提案手法LLM抽出 | `src/behavior_pattern_mining/llm/pattern_extractor.py` | 移動済み。 |
| 直接ログLLM抽出 | `src/behavior_pattern_mining/llm/direct_log_extractor.py` | 移動済み。 |
| パターン比較評価 | `src/behavior_pattern_mining/evaluation/metrics.py`, `compare_patterns.py` | 移動済み。 |
| Groundedness評価 | `src/behavior_pattern_mining/evaluation/groundedness_check.py`, `groundedness.py` | 移動済み。 |
| 条件ベース評価 | `src/behavior_pattern_mining/evaluation/condition_metrics.py` | 移動済み。 |
| `sequence_association_mining.py` | `src/behavior_pattern_mining/baselines/association_mining.py` | 主実験に含めるか探索用に分けるか決める。 |
| 主要パイプライン入口 | `scripts/run_all.py`, `scripts/run_llm_eval_batch.py` | 移動済み。 |

## 段階的なリファクタリング手順

1. 現状固定テストを増やす。
   - 小さいCSVで前処理・状態マッピング・遷移確率を検証。
   - 既存の代表状態TSVと遷移JSONを使ったスモークテストを追加。
2. 設定読み込みを広げる。
   - 現在は `experiment_config.py` が互換レイヤーとして残っている。削除するなら、各モジュールを `src/behavior_pattern_mining/config.py` から直接読む形に移行する。
3. LLMプロンプト外部化のテストを追加する。
   - `prompts/*.md` と既存の埋め込みfallbackが同じ意味を保つことを確認する。
4. 評価ロジックをさらに小さく分割する。
   - `condition_metrics.py` と `adl.py` は大きめなので、集計・入出力・CLIを分ける。
5. ベースライン抽出のCLI引数化を進める。
   - 現在は `configs/default.yaml` 依存が中心。実験ごとの差分指定をCLIでもできるようにする。
6. `src/behavior_pattern_mining/visualization/state_transition_visualizer.py` を分割する。
   - データ読み込み、状態ベクトル化、代表状態、遷移計算、可視化の順に分ける。
7. `output/`, `picture/`, `state/` を `outputs/` 配下へ移行する。
   - 既存結果はアーカイブとして残し、新規出力だけを切り替える。

## リスクと注意点

- `picture/*/state_transition_*.json` はLLM入力なので、JSONキー名や丸め桁数を変えると結果が変わる。
- ハミング距離は「距離 <= 閾値」で代表状態に寄せる。コメントでは「閾値以上はOther」と読める箇所があるため表現を統一する。
- LLMバッチ実行とLLM抽出モジュールの出力ファイル名規約がずれないように、修正時は既存出力名との互換性を確認する。
- `output/` と `picture/` は現在Git追跡されているため、一括移動すると差分が大きい。
