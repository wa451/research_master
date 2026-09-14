# シナリオスキーマ

JSONとYAMLで同じ構造を使用し、未知フィールドは拒否します。子ファイルの
`extends: relative/path.yaml`は設定ローダーが親のトップレベルを継承し、子にある
トップレベル項目だけを置換します。循環継承は拒否されます。

## ルート

| フィールド | 内容 |
|---|---|
| `schema_version` | 現在は`1` |
| `id`, `name` | 空でない識別子と表示名 |
| `start_datetime` | UTCオフセット付き日時 |
| `rooms` | ID一意。`is_outside=true`はちょうど1室 |
| `connections` | 全物理部屋を連結する重み付き無向辺 |
| `activities` | ADL、主デバイス、マイクロ行動、副次活動 |
| `residents` | 初期位置、優先度、好み、7曜日routine |
| `editor_layout` | 任意。Hestia Studio用の画面配置メタデータ。シミュレーションには不使用 |
| `sensor_imperfections` | 既定無効の観測センサー不完全性 |

## Hestia Studioの画面配置

`editor_layout`は、Webエディタで調整した見た目をシナリオと一緒に保存する任意項目です。
`room_positions`はキャンバス全体に対するパーセント値の
`{x, y, width, height}`、`device_positions`は部屋内に対するパーセント値の
`{x, y}`です。いずれも既存の部屋ID／デバイスIDだけを参照できます。

```yaml
editor_layout:
  room_positions:
    living_room: {x: 10, y: 20, width: 38, height: 48}
  device_positions:
    L_LIVING: {x: 66, y: 45}
```

この項目は視覚化のためだけのもので、乱数消費、トポロジ、デバイス操作、生成物には影響しません。

## 物理部屋、ゾーン、デバイス

部屋は`id`、`name`、1以上の`capacity`、`devices`を持ちます。ゾーンを使う場合は
`zones`、`default_zone_id`、`zone_connections`を定義します。ゾーン辺の
`travel_seconds`は0以上で、全部のゾーンが到達可能でなければなりません。

`motion_mode`は次の2種類です。

- `room`（既定）: 同室の全MotionSensorを従来どおり同期する。
- `zone`: MotionSensorの`zone_id`を必須とし、住人がいるゾーンだけをONにする。

ゾーンIDは住宅全体で一意です。デバイスの`zone_id`は設置された物理部屋内でなければ
なりません。使用可能な型は`MotionSensor`、`ContactSensor`、`DoorSensor`、`Light`、
`AirConditioner`、`Television`、`SmartPlug`、`CoffeeMachine`です。

物理部屋間`connections`は`source`、`target`、0以上の`travel_seconds`、任意の
`door_sensor_id`を持ちます。接続ドアはCLOSE開始のDoorSensorで、1本の辺にだけ割り当て
られます。

## 分布

分布指定は次を共通利用します。

| `kind` | 必須パラメータ |
|---|---|
| `fixed` | `value` |
| `uniform` | `low`, `high` |
| `normal` | `mean`, `standard_deviation` |
| `lognormal` | `mu`, `sigma` |
| `weighted` | `choices: [{value, weight}, ...]` |

`clip_min`、`clip_max`は任意です。すべての抽選は`RandomManager`を通ります。

## 活動とマイクロ行動

活動は`room_id`、任意の`zone_id`、`base_duration_minutes`、従来の
`variation_fraction`を持ちます。`duration_distribution`があればそちらを使い、
`min_duration_minutes`と`max_duration_minutes`で切り詰めます。

`device_actions`は活動中保持するアクチュエータ操作です。MotionSensor、ContactSensor、
DoorSensorはここから直接操作できません。同じ共有機器を他住人が使う間は優先度・好み調停
を維持し、最後の利用終了時に活動前状態へ戻します。

`micro_action_templates`は`id`、正の`weight`、順序付き`steps`を持ちます。ステップは次を
指定できます。

- `room_id`、`zone_id`: 省略時は親活動の場所。
- `dwell_minutes`: 共通分布。
- `optional_probability`: 任意実行確率。
- `repeat_count`: 共通分布を整数へ丸めた反復数。
- `device_actions`: ステップ中だけ保持する因果的操作。
- `reason`: 完全トレースに残す理由。

テンプレートは重み付きで1つ選択されます。ステップ移動・滞在・親場所への帰路が主活動の
締切を超える場合、滞在を短縮またはステップを省略します。マイクロ操作では冷蔵庫などの
ContactSensorをOPENして元状態へ戻せますが、MotionSensorと接続DoorSensorは空間移動が
駆動します。親活動とマイクロステップで同じデバイスを重複保持する設定は拒否します。

## 副次活動

`secondary_activities`は次を持ちます。

| フィールド | 内容 |
|---|---|
| `activity_id`, `probability`, `block_minutes` | 対象、ブロックごとの確率、判定間隔 |
| `preserve_primary_devices` | 割込み中も主機器を保持するか |
| `cooldown_minutes` | 同一割込みの最短間隔 |
| `max_occurrences` | 1主活動内の上限 |
| `allowed_start_hour`, `allowed_end_hour` | 両方指定する時間窓。日跨ぎ可 |
| `return_to_primary` | 終了後に主活動場所へ戻るか |
| `reason` | 完全トレースに残す発生理由 |

割込みの移動・活動・帰路は主活動残時間内に収まり、ネストした副次活動は行いません。
`return_to_primary=false`では親活動は移動先で終了します。

## 住人とroutine

住人は`initial_room_id`、ゾーン部屋では任意の`initial_zone_id`、`priority`、`preferences`、
正の`duration_multiplier`、0から1の`secondary_activity_factor`を持ちます。

`weekly_routine`は月曜から日曜まで必須です。従来どおり活動ID文字列を並べると、乱数消費を
含め旧実行経路を保ちます。詳細エントリでは次を指定できます。

```yaml
- activity_id: meal_preparation
  scheduled_start_minute: 465
  start_jitter_minutes: {kind: normal, mean: 0, standard_deviation: 10,
                         clip_min: -20, clip_max: 20}
  gap_before_minutes: {kind: uniform, low: 1, high: 8}
  inclusion_probability: 0.9
```

前活動が予定時刻を越えた場合、時刻を巻き戻さず直後に開始します。省略されたエントリも
`activity_trace.csv`へ理由付きで残ります。

## センサー不完全性

`sensor_imperfections.enabled`は既定`false`です。有効時は`default_profile`とセンサーID別
`profiles`で次を独立指定できます。

- `drop_probability`、`duplicate_probability`、`flip_probability`
- `false_trigger_probability`と`false_trigger_duration_seconds`
- `detection_delay_seconds`、`off_delay_seconds`、`clock_skew_seconds`
- `outage_windows: [{start_minute, end_minute}]`

`safe_mode=true`は同一センサーの同一状態連続を抑制します。不完全性は真値生成後の観測層に
だけ適用され、通常・realisticシナリオには混入しません。

## 主な実行前エラー

重複ID・辺、到達不能な部屋／ゾーン、負の移動時間、容量超過、未知参照、曜日欠落、不正な
状態、受動センサーの不正操作、接続ドアの重複利用、矛盾するマイクロ機器操作、未完の時間窓、
不正な分布パラメータ、非センサーへの故障profileは`validate`時に拒否されます。
