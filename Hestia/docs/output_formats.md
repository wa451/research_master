# 出力形式

CSVはUTF-8・ヘッダー付きで、行は`timestamp`と内部連番で安定ソートされます。時刻は
オフセット付きISO 8601、マイクロ秒精度です。

## 常時出力

| ファイル | 内容 |
|---|---|
| `events.csv` | デバイス、主体、ADL、物理部屋、全室在室正解を持つ真値完全ログ |
| `events_simple.csv` | 同一状態連続を除いたON/OFF/OPEN/CLOSE。stressでは観測側 |
| `state_vectors.csv` | デバイス最新状態、`occupants`、住人別`active_activities`。stressでは観測側 |
| `aruba.txt` | legacy形式。stressでは観測側 |
| `casas_motion_door.txt` | Motion/Contact/Door + 6列ADL境界。研究推奨、stressでは観測側 |
| `casas_all_devices.txt` | 全対応デバイス + ADL境界 |
| `casas_sensor_map.json` | 個別IDのidentity map |
| `sensor_map.csv` | ID、型、物理部屋の対応 |
| `manifest.json` | 条件、件数、意味検証結果、任意機能件数 |

`events.csv`の列は`timestamp`、`device_id`、`device_type`、`state`、`value`、
`resident_id`、`resident_name`、`occupants`、`activity_id`、`activity_label`、
`room_id`、`room_name`、`event_source`、`run_id`、`seed`です。複合属性はキー順固定JSON、
共有制御中は`controlled_by`を含みます。

CASASセンサー行は4フィールドです。

```text
YYYY-MM-DD HH:MM:SS.ffffff SENSOR_ID ON|OFF|OPEN|CLOSE
```

ADL境界は研究parser向け6フィールドです。

```text
YYYY-MM-DD HH:MM:SS.ffffff activity::RESIDENT START ADL_LABEL begin
YYYY-MM-DD HH:MM:SS.ffffff activity::RESIDENT END   ADL_LABEL end
```

## ゾーン使用時だけ

| ファイル | 内容 |
|---|---|
| `activity_trace.csv` | routine選択、テンプレート、内部step、START/END/SKIPPED、回数、理由 |
| `zone_sensor_map.csv` | ID、型、物理部屋、ゾーンID・名 |
| `casas_sensor_map_room.json` | 複数ゾーンセンサーIDから元の物理部屋カテゴリへの統合map |

`activity_trace.csv`は研究CASASへ混ぜない完全監査ログです。マイクロ行動の内部ラベルはここに
残し、CASASのADLラベルは親活動のままにします。

## 不完全性有効時だけ

| ファイル | 内容 |
|---|---|
| `events_true.csv` | `events.csv`と同じ真値の明示コピー |
| `events_observed.csv` | 不完全性適用後の観測完全ログ |
| `events_simple_true.csv` | 真値簡易ログ |
| `state_vectors_true.csv` | 真値状態ベクトル |
| `aruba_true.txt` | 真値legacy CASAS |
| `sensor_imperfection_audit.csv` | 真時刻、観測時刻、drop/flip/duplicate等、理由、前後状態 |

この場合も`events.csv`は真値です。一方、`events_simple.csv`、`state_vectors.csv`、
`aruba.txt`、`casas_motion_door.txt`、`casas_all_devices.txt`は観測側なので、研究パイプラインへ
誤って真値を渡しません。`manifest.json`には真値・観測件数、安全モード、監査件数を追加します。
