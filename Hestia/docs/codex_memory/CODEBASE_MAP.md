# コードベースの地図

用途: 場所・入口・テストを特定する索引。パスはリポジトリroot基準。

## 配置

- `src/smart_home_sim/`: シミュレータとCLI、Studio。`studio_static/`の`index.html` / `app.js` / `styles.css`がブラウザUI。
- `tests/`: pytest。`conftest.py::minimal_scenario_data`が共通の最小設定。
- `examples/`: 単身・二人の基本例。`functional/`は回帰、`realistic_calibrated/`は追加研究評価、`stress/`は高密度・観測ノイズ評価。
- `scripts/`: `run_research_pipeline.py`が別研究repoとの接続、`calibrate_realistic.py`が設定校正、`analyze_realism.py` / `compare_data_quality.py`が比較、`run_long_validation.py`が長期検証。
- `docs/`: 現行仕様・設計。`reports/`: 過去の監査・測定結論。`references/`: 論文資料。
- `scenarios/`はStudio保存時に作成。`outputs/`は生成物（git対象外）。`pyproject.toml`は依存・CLI・検査設定、`uv.lock`は依存固定。

## 主要入口と対応テスト

以下の実装ファイルは`src/smart_home_sim/`、テストは`tests/`配下。

| 実装・シンボル | 役割 | 主なテスト |
|---|---|---|
| `cli.py::app` | Typer入口 `smart-home-sim`: validate / simulate / studio / transform-state / export-aruba | `test_cli_and_outputs.py` |
| `config.py::load_scenario`, `schema.py::Scenario` | JSON/YAML継承、Pydantic型・参照・トポロジ検証 | `test_schema.py`, `test_realism_features.py` |
| `home.py::HomeGraph`, `zones.py::ZoneGraph` | 物理部屋・論理ゾーンの経路 | `test_randomness_and_home.py`, `test_realism_features.py` |
| `engine.py::SimulationEngine.run` | 住人プロセスと出力全体の統括。`_perform_activity`→legacy/enhanced、`_move` / `_move_zone`→移動 | `test_engine_integration.py`, `test_boundary_conditions.py` |
| `devices.py::Device`, `DeviceManager`; `models.py::ActivityUse` | 状態遷移、共有利用・好み調停 | `test_devices.py`, `test_boundary_conditions.py` |
| `randomness.py::RandomManager` | 分布・確率・重み付き選択 | `test_randomness_and_home.py`, `test_realism_features.py` |
| `events.py::EventCollector`, `traces.py::ActivityTraceCollector` | 真値イベント、routine/micro/secondary判断トレース | `test_engine_integration.py`, `test_realism_features.py` |
| `imperfections.py::apply_sensor_imperfections` | 真値→観測と変更理由監査 | `test_realism_features.py` |
| `outputs.py::transform_state_csv`, `export_aruba`, `CasasPreset` | CSV・状態ベクトル・CASAS・対応表 | `test_cli_and_outputs.py` |
| `validation.py::validate_generated_events`, `audit_event_semantics` | 生成後の時空間・活動・機器不変条件 | `test_boundary_conditions.py`, `test_engine_integration.py` |
| `engine.py::hash_output_directory` | ファイル名と内容による完全出力ハッシュ | `test_reproducibility_and_e2e.py` |
| `studio.py::create_studio_app`, `serve_studio` | FastAPIによる編集・検証・保存・実行 | `test_studio.py` |

## データフロー

`cli.py` / `studio.py` → `load_scenario` → `Scenario` → `SimulationEngine.run` → 住人・機器・移動 → `EventCollector` → 真値`events.csv`。
真値 → 任意の`apply_sensor_imperfections` → 観測`events_observed.csv` → simple CSV / state vectors / Aruba・CASAS。
ノイズ無効時は真値から変換。真値の意味検証 → `manifest.json` → `SimulationResult`（件数・検証・ハッシュ）。ゾーン・トレース・真値別名出力は利用機能に応じて追加。

詳細: [アーキテクチャ](../architecture.md)、[設定仕様](../scenario_schema.md)、[出力契約](../output_formats.md)。

## master-research内の配置と評価9

このrepoの実体は `master-research/Hestia/`（独立Gitを保持、親repoではignore）。親の `scripts/evaluate_9_hestia.py` とStreamlitの評価9が本repoの `experiment` CLIを呼ぶ。操作・入力契約は [評価9ガイド](../../../docs/evaluations/evaluation_9_hestia.md)。単体Studioログではなく実験計画と正解を持つexperimentディレクトリを使用する。
