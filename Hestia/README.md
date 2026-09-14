# Hestia Cleanroom Smart Home Simulator

スマートホーム内の住人行動、移動、デバイス操作、センサー反応を再現可能な合成ログとして生成する、Python製の離散イベントシミュレータです。住宅・活動・週間ルーティン・住人の好みをJSONまたはYAMLで記述し、生イベント、状態ベクトル、Aruba/CASAS風ログを出力します。

> [!IMPORTANT]
> 本プロジェクトはHESTIA論文から着想を得た独立のクリーンルーム再実装です。HESTIAの公式実装ではなく、原著コードとの互換性も主張しません。実装は論文、本リポジトリの仕様、一般的な離散イベントシミュレーション技術だけを基に独自設計されています。

## 主な機能

- Pydanticによる住宅、接続、活動、7曜日ルーティン、住人、好みの事前検証
- SimPyによる住人、部屋容量、ドア、共有デバイスの離散イベント処理
- NetworkXによる重み付き最短経路移動
- 物理部屋内の論理ゾーン、ゾーン経路、room/zone切替可能な人感センサー
- 重み付き複数テンプレート、任意・反復step、締切内短縮を備えたADL内マイクロ行動
- fixed/uniform/normal/lognormal/weighted分布による開始時刻・継続時間・間隔の揺らぎ
- 時間窓、クールダウン、回数上限、復帰有無を持つ副次活動
- 通過ごとに`OPEN -> 移動時間 -> CLOSE`となる直列化されたドアセンサー
- 複数住人の共有利用と優先度ベースの好み調停
- MotionSensor、ContactSensor、DoorSensor、Light、AirConditioner、Television、SmartPlug、CoffeeMachine
- 完全イベントCSV、簡易イベントCSV、状態ベクトルCSV、Aruba/CASAS風ログ、センサー対応表
- stressだけで有効にできる欠損・遅延・OFF遅延・誤反応・反転・重複・停止・時刻ずれ
- 真値／観測ログの分離、マイクロ行動トレース、zone→物理部屋カテゴリ対応表
- 同一設定・日数・seedからバイト単位で同じ成果物を生成

## インストール

Python 3.11以上と[uv](https://docs.astral.sh/uv/)を用意してください。Docker、GPU、クラウド、外部APIは不要です。

```bash
uv sync
```

Apple Siliconを含むmacOSでは、Terminalでリポジトリ直下へ移動して同じコマンドを実行できます。依存関係は純PythonまたはmacOS向けwheelで解決されます。

## 最小実行例

```bash
uv run smart-home-sim validate examples/aruba_single_resident.yaml
uv run smart-home-sim simulate examples/aruba_single_resident.yaml \
  --days 7 --seed 42 --output outputs/aruba_seed42
```

## Hestia Studio（Webエディタ）

ローカルWebアプリの **Hestia Studio** では、部屋をドラッグ・リサイズし、部屋内の
デバイスを直感的に配置できます。住人ごとの初期位置、優先度、行動時間倍率、デバイスの
好み、曜日別ルーティンも編集でき、既存スキーマで検証したJSON/YAMLを書き出せます。
画面上部の **GUI / コード** で編集方法を切り替えられます。コード編集ではYAMLまたは
JSONを直接変更でき、検証を通った内容だけがGUIへ反映されるため、修正途中のコードで
現在の間取りが壊れることはありません。
コード画面には読み込み元の実ファイル名と書出し名を表示します。部屋（`rooms`）と人物
（`residents`）は別ファイルではなく、同じシナリオファイル内のセクションです。
上部の **YAML保存** または「実行」タブから、検証済み設定をプロジェクト内の
`scenarios/<filename>.yaml` に保存できます。「実行」タブでは保存済みYAML（および
`examples/` 内のYAML）、日数、seed、出力フォルダ名を選び、`outputs/studio/<run-name>/` に
ログを生成します。同名の出力フォルダは上書きしないため、実行名を変えてください。

```bash
uv run smart-home-sim studio --scenario examples/aruba_single_resident.yaml
```

既定では <http://127.0.0.1:8765> を開きます。別ポートで起動する場合は
`--port 9000`、ブラウザを自動で開かない場合は `--no-open` を指定してください。
部屋・デバイスの画面上の位置は、シミュレーションに影響しない `editor_layout` として
シナリオ内に保存されます。

`master-research` のStreamlitダッシュボードでは、**Hestia Studio** がComponents v2として
画面内に直接統合されます。別のStudioサーバー、ポート、iframeは不要です。Studio内の住宅
タブには評価9の compact / corridor / branched のbase住宅がすべて先読みされ、ページを
差し替えずに切り替えられます。
住宅ごとの未保存編集はページを開いている間保持されます。部屋の接続と移動時間、センサー・
デバイスの種類・所属部屋・表示位置を変更し、`scenarios/` にYAML保存できます。部屋内の
アイコン座標は表示専用の `editor_layout` です。保存ファイルはカスタムシナリオであり、
評価9の本実験planや生成処理を自動的には変更しません。

間取り画面の **論文用SVG** / **論文用PNG** は、現在の編集状態から部屋、接続、移動時間、
ドアセンサーID、センサー／デバイスID、凡例を白背景の図として書き出します。SVGはベクター、
PNGは3200 × 2000 pxです。ホーム設定の表示名が図タイトルになります。これは配置を説明する
図であり、評価9のground truthや採点入力には使用されません。

上記の `smart-home-sim studio` はHestia単体利用の互換入口として残しています。
master-researchではrootで `uv run streamlit run app/streamlit_app.py` だけを実行してください。

用途別シナリオは次の3系列です。

| 系列 | 用途 | 例 |
|---|---|---|
| `functional` | 高速な機能・回帰・ハッシュ確認 | `examples/functional/aruba_single_resident.yaml` |
| `realistic_calibrated` | 意味のあるゾーン移動と行動多様性の追加評価 | `examples/realistic_calibrated/aruba_single_resident.yaml` |
| `stress` | 高密度・複数住人・観測センサー不完全性の耐性評価 | `examples/stress/two_residents_sensor_noise.yaml` |

個別の再変換も可能です。

```bash
uv run smart-home-sim transform-state outputs/aruba_seed42/events.csv \
  --output outputs/aruba_seed42/state_rebuilt.csv
uv run smart-home-sim export-aruba outputs/aruba_seed42/events.csv \
  --output outputs/aruba_seed42/casas_rebuilt.txt --preset motion-door
```

## 観測ノイズなしの複数住宅評価

`smart-home-sim experiment` で、複数住宅のログ生成、既存研究コードによる代表状態・
ネットワーク構築、LLM抽出、系列回収・ADL対応の採点を段階的に実行できます。
LLM呼出しは `extract --allow-api` を明示した場合のみです。
条件一覧・pilot設定・実行手順・指標の注意点は
[追加評価のガイド](docs/noise_free_evaluation.md)を参照してください。

## シナリオの作成

シナリオは次の順で定義します。

1. `start_datetime`をUTCオフセット付きISO 8601で指定する
2. 部屋と部屋内デバイスを定義し、屋外の部屋を1つ指定する
3. 部屋間接続、移動秒数、任意のDoorSensorを指定する
4. 必要な部屋を論理ゾーンへ分け、zone modeのMotionSensorを配置する
5. 活動時間分布、デバイス操作、マイクロテンプレート、副次活動、ADLラベルを定義する
6. 住人の初期位置、優先度、好み、7曜日の予定・jitter・省略確率を定義する

完全な仕様は[シナリオスキーマ](docs/scenario_schema.md)、実例は[一人暮らし](examples/aruba_single_resident.yaml)と[二人暮らし](examples/two_residents.yaml)を参照してください。

## 出力

`simulate`は指定先に次を生成します。

| ファイル | 内容 |
|---|---|
| `events.csv` | 複合属性、操作主体、活動、部屋、在室正解情報を含む完全イベント |
| `events_simple.csv` | ON/OFF/OPEN/CLOSEだけの重複抑制済みイベント |
| `state_vectors.csv` | 全デバイスの最新状態を横持ちにした状態ベクトル |
| `aruba.txt` | `日時 SENSOR_ID STATE ADL_LABEL`形式。活動START/END境界を含む |
| `casas_motion_door.txt` | 研究パイプライン向け4列センサーイベント+6列ADL境界 |
| `casas_all_devices.txt` | 全対応デバイスを含む同CASAS形式 |
| `casas_sensor_map.json` | 研究パイプライン向けsensor ID map |
| `sensor_map.csv` | センサーID、型、部屋の対応表 |
| `manifest.json` | 実行条件、件数、生成後不変条件検査の結果 |

ゾーン使用時は`activity_trace.csv`、`zone_sensor_map.csv`、`casas_sensor_map_room.json`を
追加します。sensor imperfections有効時は真値`events.csv`とは別に
`events_observed.csv`と監査CSVを作り、研究CASASには観測側を出します。

詳細は[出力形式](docs/output_formats.md)を参照してください。生成物は研究用の合成データであり、実環境の統計的妥当性を自動的に保証するものではありません。

## 品質確認

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -q
```

テストは従来項目に加え、ゾーン到達性・移動、zone Motion、重み付きテンプレート、任意・反復・
時間不足step、予定時刻・分布・省略、夜間副次活動・クールダウン・非復帰、真値／観測分離、
outage・flip・safe mode、研究変換、30/220日実測を対象にします。

## 設計文書

- [アーキテクチャ](docs/architecture.md)
- [シナリオスキーマ](docs/scenario_schema.md)
- [出力形式](docs/output_formats.md)
- [再現性](docs/reproducibility.md)
- [HESTIA論文との比較](docs/hestia_comparison.md)
- [既知の制約](docs/limitations.md)
- [realisticシナリオ設計](docs/realistic_scenario_design.md)
- [校正方法](docs/calibration_method.md)
- [研究での使い分け](docs/research_usage.md)
- [意味論監査](reports/semantic_audit.md)
- [改善後の研究パイプライン統合](reports/pipeline_integration_after_improvement.md)
- [改善前の研究パイプライン監査](reports/pipeline_integration_report.md)
- [実データ品質比較](reports/data_quality_report.md)
- [再現性・長期実行監査](reports/reproducibility_report.md)

## 研究利用時の引用

本実装を利用する場合は本リポジトリのバージョンまたはコミットを記録し、着想元として次のプレプリントも参照してください。

```bibtex
@article{oliveira2025hestia,
  title   = {HESTIA: A Home Environment Simulator Targeting Inhabitant Activities},
  author  = {Oliveira, Mayki dos Santos and others},
  year    = {2025},
  journal = {TechRxiv},
  doi     = {10.36227/techrxiv.173888093.30111102/v2}
}
```

## 既知の制約

Tuyaメッセージ互換、周期レポート、電力値、連続環境値、音響機器、好みからの活動自動生成
は対象外です。realisticはfunctionalより複雑ですが、Arubaのイベント密度や生活系列を再現する
代替データではありません。詳細は[既知の制約](docs/limitations.md)と
[改善後比較](reports/functional_vs_realistic_vs_aruba.md)に明記しています。
