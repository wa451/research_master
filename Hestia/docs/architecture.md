# アーキテクチャ

## 処理方向

```text
JSON/YAML (+ extends)
  -> config.py / schema.py       読込、継承、相互参照検証
  -> home.py / zones.py          物理部屋・部屋内ゾーンの重み付き経路
  -> engine.py                   SimPy住人プロセス、routine、締切
       -> randomness.py          全確率分布と選択の単一seed源
       -> devices.py             センサー、家電、共有利用調停、状態復元
       -> events.py              真値イベント収集
       -> traces.py              routine/micro/secondaryの判断トレース
  -> imperfections.py            stressだけの真値→観測センサー変換
  -> outputs.py                  CSV、状態ベクトル、CASAS、対応表
  -> validation.py               真値の時系列・空間・活動・機器不変条件
  -> cli.py                      非対話CLI
  -> studio_service.py           Studio共通サービス（検証・保存・変換・実行）
  -> studio.py                   単体起動用FastAPIアダプタ
```

シミュレーション中の可変状態は`SimulationEngine`内に閉じ、モジュール乱数は使いません。
既存の文字列routine、ゾーンなし、旧副次活動だけの設定は専用のlegacy分岐を通るため、追加
機能が乱数消費や出力ファイル集合を変えません。

## 空間

`HomeGraph`は物理部屋の無向グラフ、`ZoneGraph`は物理部屋ごとの論理ゾーングラフです。
同コストの最短経路はID列の辞書順で決定します。物理部屋の容量はSimPy Resourceで管理し、
部屋内移動は同じResourceを保持したまま行います。

zone modeでは`zone_occupants`を別に持ち、退出元の最後の住人で対応MotionSensorをOFF、
到着先の最初の住人でONにします。room modeは従来どおり物理部屋の全MotionSensorを同期
します。`occupants`の正解情報は研究互換性のため物理部屋単位のままです。

部屋間ドアはDoorSensorごとのResourceで`OPEN -> 退出 -> 移動時間 -> CLOSE`を直列化し、
その後に到着部屋容量を取得します。これによりOPEN重複と容量1部屋間の循環待ちを防ぎます。

## 活動、マイクロ行動、時間

詳細routineは予定分+日別jitterを下限にし、前活動が延びれば即時開始します。活動時間は設定
分布、上下限、住人倍率の順で決まります。

主活動START後に重み付きマイクロテンプレートを1つ選び、任意ステップ、反復、移動、滞在、
一時機器利用を順に実行します。各ステップ前に親場所への帰路を予約し、締切不足なら滞在を
短縮または省略します。内部ラベルは活動境界を増やさず`activity_trace.csv`へ分離するため、
全マイクロ行動は同じ親ADLに属します。

拡張副次活動は時間窓、クールダウン、回数上限を満たす候補だけを抽選します。移動・副活動・
任意の帰路を主活動締切内に予約します。共有機器は副次活動前後で明示的に解放・再取得し、
他住人が使用中ならその住人の設定を維持します。

## デバイスと共有制御

各Deviceは住人別利用集合を持ち、`(-priority, resident_id)`で勝者を決定します。最初の利用前
状態と属性を保存し、最後の利用終了時に復元します。状態・属性が完全一致する操作はイベントに
しません。マイクロ操作も同じ調停を使うため、一時的な冷蔵庫接触やSmartPlug操作が主活動終了
時の復元を壊しません。

## 真値と観測

`EventCollector`が作る真値は常に`events.csv`へ保存し、完全意味検証の対象にします。
`sensor_imperfections.enabled=true`の場合だけ、`imperfections.py`が受動センサー行へ欠損、
遅延、OFF遅延、誤反応、反転、重複、停止期間、時刻ずれを適用します。アクチュエータとADL
境界は保持します。研究向けCASASと通常の`state_vectors.csv`は観測側から作り、真値版も別名
で残します。全変更理由は監査CSVへ出します。

## Hestia Studio（Webフロントエンド）

`studio_service.py`は、シミュレーション本体（`engine.py`以下）へ手を加えず、
`config.py`の`load_scenario`、`schema.py`の`Scenario`、`SimulationEngine`を呼び出す
transport非依存のサービス層です。master-researchのStreamlit Components v2はこの層を直接
呼び出します。`studio.py`はHestia単体CLIとの互換性を保つ任意のFastAPIアダプタです。
どちらも入出力契約は共通で、Studio固有の分岐はエンジン内部に存在しません。

- **状態**：ドラッグ・リサイズ・入力途中はブラウザ内だけで処理します。Streamlit統合では
  Components v2のstateに住宅ごとの編集状態を保持し、検証・保存・import/export・実行だけを
  triggerでPythonへ渡します。Python側は受け取ったシナリオJSONをその場で
  `Scenario.model_validate`し、検証済みシナリオだけをGUIへ反映します。
- **ファイルアクセスの境界**：`_allowed_scenario_files`がプロジェクトroot配下の`scenarios/`と
  `examples/`だけを一覧・実行対象にし、`_is_within`で全ての読み書きパスがrootの外に出ないこと
  を都度検証します。`load_scenario(..., allowed_root=root)`により、`extends`継承チェーンも
  root外のファイルを参照できません。保存・出力ディレクトリ名は`_safe_yaml_filename`/
  `_safe_output_name`で英数字ベースの安全な basename に制限します。
- **表示専用データ**：`editor_layout`（`room_positions`/`device_positions`）はスキーマ上
  `Scenario`の一部ですが、エンジンとバリデーションは一切参照しません。GUIでの配置変更が
  乱数消費や生成イベントに影響しないことは`test_editor_layout_does_not_change_complete_simulation_outputs`
  で保証しています。
- **実行**：`StudioService.run_simulation`はStudioから選べる保存済みYAMLのみを対象に
  `SimulationEngine`をCLIと同じ経路で呼び出し、一時ディレクトリへ出力してから原子的に
  `outputs/studio/<run-name>/`へ配置します。同名ディレクトリは上書きしません。

## 出力後検証

`validation.py`はタイムゾーン・時刻順、住人の一意所在と隣接移動、容量、活動の入れ子と場所、
room/zone Motion遷移、ドア対と通過時間、週間routine順、共有機器調停、一時停止・再開、活動前
状態復元、終了時未完了状態を検査します。観測ノイズは在室真値と一致しないことが目的なので、
真値だけを完全意味検証します。
