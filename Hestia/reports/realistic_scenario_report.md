# realistic_calibrated 改善結果

## 結論

既存functionalの完全再現性を維持しながら、部屋内ゾーン、ADL内マイクロ行動、時刻・継続時間・
経路の分布、副次活動、因果的な機器操作を追加した。7日(seed 42)では研究入力イベントが
552から1,616、ADL内状態変化が136から334、状態遷移が212から422、観測された非Other代表状態が
7から12へ増えた。正式network JSONのOther時間率は72.73%から26.12%へ低下した。

## 追加したアーキテクチャ

- 8部屋・25論理ゾーンの二層トポロジーと、部屋内最短経路移動
- `room`同期と`zone`単独発火を選べるMotionSensor
- 重み付き複数テンプレート、任意・反復ステップ、期限内短縮を持つマイクロ行動
- fixed / uniform / clipped normal / lognormal / weighted discrete分布
- 開始時刻jitter、活動間gap、省略、平日/休日ルーティン
- 時間帯、クールダウン、最大回数、復帰可否、理由を持つ副次活動
- 活動前状態へ復元され、多人数の利用権を尊重する機器操作
- stress専用の真値→観測センサー不完全性変換と監査ログ
- ゾーン対応表、部屋カテゴリ対応、内部activity trace

既存の部屋同期、旧形式ルーティン、CLI、出力はlegacy分岐で維持した。旧単身7日出力は
943 events / 939 states、完全ディレクトリSHA-256
`5e11e89d2ec0361d82715fa0d51a7714da00d4b17e707bd238fae0a6d2a1f6eb`のままである。

## シナリオ系列

| 系列 | ファイル | 役割 |
|---|---|---|
| functional | `examples/functional/aruba_single_resident.yaml` | 既存シナリオ継承による高速回帰 |
| realistic_calibrated | `examples/realistic_calibrated/aruba_single_resident.yaml` | 単身の制御された追加評価 |
| realistic_calibrated | `examples/realistic_calibrated/two_residents.yaml` | 多人数・同時活動・共有機器調停 |
| stress | `examples/stress/high_density_single_resident.yaml` | 高頻度の意味的状態変化 |
| stress | `examples/stress/two_residents_sensor_noise.yaml` | 多人数＋明示的な観測不完全性 |

## 反復校正

校正は7日、seed 42、K=15、h=0、1秒Sample-and-Hold、5秒遅延OFFで3試行に制限した。
任意マイクロステップ保持率と副次活動確率を設定値として段階調整し、全試行で意味検証と正式
研究パイプラインを実行した。最終試行はraw 301.29 events/日、研究入力230.86 events/日、
state-series Other 16.59%、422遷移、334 ADL内変化、警告0で、総合スコア最大のため採用した。

## functional / realistic / Aruba

| 指標 | functional | realistic | Aruba | 改善倍率 |
|---|---:|---:|---:|---:|
| raw完全ログ events/日 | 134.71 | 301.29 | - | 2.24x |
| 研究入力 events/日 | 78.86 | 230.86 | 6,924.43 | 2.93x |
| network Other時間率 | 72.73% | 26.12% | 2.06% | 0.36x |
| ADL内状態変化 | 136 | 334 | 14,795 | 2.46x |
| 設定代表状態数 | 15 | 15 | 15 | 1.00x |
| 観測済み非Other代表状態 | 7 | 12 | 15 | 1.71x |
| 状態遷移 | 212 | 422 | 34,169 | 1.99x |
| 日別件数CV | 0.175 | 0.154 | 0.220 | 0.88x |

realisticの日別研究イベント数は168～286で0ではない変動を持つ。時間別ではfunctionalで0だった
03、04、14、16、20～23時にもイベントが現れ、07～11時と17～22時の活動密度が増えた。
ADL区間は76から84へ増加し、Meal 14→35、Toileting 6→11となった。Relax、Outing、Houseworkは
曜日別省略と週末差により減る日もある。完全な時間帯・ADL・部屋・センサー内訳は
`functional_vs_realistic_vs_aruba.csv`に保存している。

## Aruba集計との距離

| 距離 | functional | realistic | 改善量 |
|---|---:|---:|---:|
| 時間帯JS (bits) | 0.312937 | 0.114702 | 0.198235 |
| 部屋発火順位JS (bits) | 0.144642 | 0.065366 | 0.079276 |
| イベント間隔Wasserstein (秒) | 990.636 | 305.624 | 685.012 |
| ADL継続時間Wasserstein (分) | 91.690 | 62.338 | 29.352 |
| 遷移確率順位L1 | 6.262 | 5.519 | 0.743 |

これらは比較可能な集計量の距離であり、統計的等価性を示さない。Arubaの部屋真値はないため、
合成の部屋滞在時間とArubaの部屋別発火は同一概念として比較していない。

## 未達成目標

- 研究イベント密度はfunctional比2.93倍で、可能なら10倍という目標には未達。
- ADL内状態変化は2.46倍で、3倍目標には未達。
- 状態遷移は1.99倍で、3倍目標には未達。
- Kを15に固定する正式条件上、設定代表状態数自体は増えない。観測された非Other状態は増加した。

不足分を埋めるには短時間の再発火や追加の細粒度状態が必要だが、無意味な反転やAruba系列の模倣を
避けるという優先条件に反するため、意味的に妥当な最終値で停止した。合成データはArubaの代替ではない。
