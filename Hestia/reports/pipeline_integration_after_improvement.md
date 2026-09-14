# 改善後の研究パイプライン統合検証

## 結論

functional、realistic_calibrated、stressの各7日データは、`master-research`を変更せず、
K=15、h=0、1秒Sample-and-Hold、5秒遅延OFFの正式条件で、CASAS変換から時間帯別ネットワーク、
ADL state-series評価まで完走した。全3実行で警告・エラーは0。外部LLM APIは呼ばず、4時間帯の
API入力メッセージ構築まで検証した。

## 使用データ

| 系列 | Hestia raw | 研究入力行 | 変換対象 | 除外 | 使用センサー |
|---|---:|---:|---:|---:|---:|
| functional | 943 | 704 | 552 | 152 | 16 |
| realistic_calibrated | 2,109 | 1,784 | 1,616 | 168 | 34 |
| stress two-resident noise | truth 2,928 / observed 2,846 | 2,468 | 2,206 | 262 | 34 |

除外はADL境界など、研究側のセンサー状態ベクトルへ直接入れない行である。stressは観測ログから
CASASを作成し、真値は正解用に分離した。

## 状態・ネットワーク・ADL結果

| 指標 | functional | realistic | stress |
|---|---:|---:|---:|
| 1秒状態ベクトル行 | 604,800 | 604,800 | 604,800 |
| 圧縮状態区間 | 213 | 423 | 775 |
| 設定代表状態数 | 15 | 15 | 15 |
| 観測済み非Other代表状態 | 7 | 12 | 15 |
| state-series Other時間率 | 55.564% | 16.589% | 17.863% |
| formal network Other時間率 | 72.725% | 26.119% | 18.034% |
| 状態遷移 | 212 | 422 | 774 |
| network nodes | 16 | 16 | 16 |
| network edges | 38 | 44 | 71 |
| ADL区間 | 76 | 84 | 131 |
| ADL内状態変化 | 136 | 334 | 1,222 |
| 警告・エラー | 0 | 0 | 0 |

state-seriesのOther率は、1秒行に対するマッピング不能時間率として記録した。formal network側は
既存baseline比較と同じネットワークJSONの時間加重定義で、集計境界の違いにより値が異なる。

## 時間帯別変換イベント

| 系列 | Morning | Daytime | Night | Midnight | 合計 |
|---|---:|---:|---:|---:|---:|
| functional | 240 | 164 | 84 | 64 | 552 |
| realistic_calibrated | 420 | 404 | 646 | 146 | 1,616 |
| stress | 693 | 592 | 697 | 224 | 2,206 |

realisticとstressは4時間帯すべてに有効なイベントと遷移を持つ。時間帯JSON、全期間ネットワーク、
ADL区間、state-seriesはすべて生成された。

## 外部API直前のpreflight

研究側の`find_mode_json_files`、`mode_label_from_path`、`build_user_message`を読み取り専用で呼び、
各系列のMorning / Daytime / Night / Midnightを列挙し、JSONと時間帯ラベルを埋め込んだ。
12メッセージすべてで`{JSON_DATA}`と`{MODE}`が残っていないことを確認した。

| 系列 | Morning bytes | Daytime bytes | Night bytes | Midnight bytes |
|---|---:|---:|---:|---:|
| functional | 11,583 | 10,843 | 10,805 | 7,886 |
| realistic_calibrated | 11,825 | 11,374 | 12,363 | 9,970 |
| stress | 12,503 | 12,650 | 13,522 | 9,816 |

functionalのメッセージSHA-256は順に
`2c03d2d1196e2411c30efc8dd2b76c74b7e6d8dd0800402f8a826d23e6c022f0`、
`016b319972745ad2ee1183b67699a2b13b130627ae6eded87ecc31c889927688`、
`d080b248b9de8c17925745fb01475c8184c0f8d74838c456a63194de6ded012b`、
`699e79c51abfda5ab0cd9a2a6d0ca83e2345272fe763f25b27cc17ac54f65cfb`で、改善前監査と一致した。
外部APIへの送信処理は実行していない。

## 既存Aruba成果物の不変性

研究リポジトリは読み取り専用で利用し、既存正式成果物のSHA-256を記録した。

| 対象 | SHA-256 |
|---|---|
| `data/aruba.csv` | `0c32673673143ccb4cf44f093a1f75d6f17be7e5b0851ec5c042765431e35d6b` |
| `new_labeled_data/aruba.txt` | `32518ee833381ac9ba56b24695852bf5f547dc3ab08b19e1a480478b8f8903c4` |
| `picture/aruba_15_0_154days/state_transition_all.json` | `ebd1faceab205d33bb53717e08b6a805a1ca823fe8d69eb45d8d4987764b6e0f` |
| `output/5_adl_evaluation_15_0_154days/state_series.csv` | `ccb90356d12a1b991b11092681370f1d5e4fcdc006f1dced82d3de8b3aaf054c` |

生成物は`/private/tmp`に置き、Hestiaへ生データをコピーしていない。既存研究ロジック、正式条件、
Aruba評価結果は変更していない。
