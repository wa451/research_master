# 論文執筆・評価ロードマップ

最終更新: 2026-08-30

## この文書について

このリポジトリで実施したHESTIA論文とのレビュー結果と、研究論文執筆に向けた
やるべきことをまとめたものです。後続のセッション（人間・AIのどちらが読んでも）が
文脈をゼロから再構築しなくて済むように、決定済み事項・未決定事項・具体的な
アクションを分けて記載します。関連する既存文書は末尾の「参考文書」を参照してください。

## 1. レビュー結果の要約（2026-08-30時点で確認済み）

### 1.1 本実装とHESTIA論文の関係

- 本リポジトリは[AGENTS.md](../AGENTS.md)に明記されている通り、**HESTIA論文の概念に着想を得た
  独立再実装**であり、原著ソース・設定・Tuya互換出力の複製ではない。
- 論文との詳細な対応表は[docs/hestia_comparison.md](hestia_comparison.md)、
  意味論レベルの監査は[reports/semantic_audit.md](../reports/semantic_audit.md)に既にある。
  本セッションで以下を独立に再検証し、両文書の記述が正確であることを確認した。
  - デバイスの「活動前状態への復元」ロジック（[devices.py](../src/smart_home_sim/devices.py):
    `begin_use`で`_idle_state`を保存、`end_use`で利用者0件になった時点で`desired_state()`が
    保存済み状態を返し復元する）。
  - 実装済みデバイス種別はMotionSensor/ContactSensor/Light/AirConditioner/Television/
    SmartPlug/CoffeeMachineの7種で、論文が挙げる7 Products中「sound system（スマート
    スピーカー等の音響機器）」は未実装。ContactSensor（ドア）は論文にない独自拡張。
  - 経路探索は論文のA*ではなくNetworkX最短経路（目的は同じ、内部方式は意図的に不一致）。
  - 優先度が同じ住人間の調停規則（resident IDの辞書順）は論文が明記しない独自定義。
- `uv sync` / `ruff format --check` / `ruff check` / `pyright` / `pytest -q`（65件）は
  全てグリーン（[AGENTS.md](../AGENTS.md)の必須チェック）。

### 1.2 Hestia Studio（Web GUI）の追加

- 論文が限界として挙げる「GUIの欠如」に対応するローカルWeb GUIを追加し、
  コミット済み（`feat: add Hestia Studio web editor`）。
- `editor_layout`は表示専用のスキーマフィールドで、エンジン・乱数消費・生成イベントに
  一切影響しないことをテストで保証済み（`test_editor_layout_does_not_change_complete_simulation_outputs`）。
- パストラバーサル対策（保存・実行対象を`scenarios/`・`examples/`配下に限定、
  `extends`継承チェーンもプロジェクトroot外を参照不可）を実装・テスト済み。
- [docs/architecture.md](architecture.md)にStudioの節を追記済み。

### 1.3 論文の統計的検証の再現状況

- 論文の実験的評価（14日間・4機器・実環境とのMann-Whitney U検定）は**再現していない**。
  本リポジトリの監査は7日間の記述統計・分布比較であり、論文実験の再現ではない
  （[docs/hestia_comparison.md](hestia_comparison.md)の「未対応」欄に明記）。
- センサーノイズ（presence sensorの誤検知等）も再現していない。`sensor_imperfections`は
  stress限定の独自耐性評価モデルであり、物理センサー故障の再現ではない
  （[docs/limitations.md](limitations.md)）。

## 2. 論文執筆上の重要な注意点

### 2.1 やってはいけない推論

**「HESTIA論文の手法・概念を参考にツールを実装した」→「だからこのツールの生成ログも
HESTIA論文と同程度に実世界に近い」という推論は成立しない。**

理由: 統計的検証（Mann-Whitney Uで有意差なし）は「特定の実装 × 特定の実測データ」の
ペアに対してのみ成立する事実であり、実装が変われば（設計思想が同じでも）再検証なしに
結果は継承されない。この推論を論文に書くと、査読で「その検証はご自身の実装で
実施したのか」と問われた際に破綻する。

### 2.2 実環境での新規データ収集をせずに主張できる範囲

ユーザーの意向（実環境比較はしないが、可能なら実世界に近いと言いたい）を踏まえた、
誠実に主張できる最大限のライン:

1. **手法としての妥当性を引用する**（自分の実装の検証結果としてではなく、先行研究の
   知見として）:
   「活動駆動型の離散イベントシミュレーションというアプローチは、先行研究[HESTIA]に
   おいて実環境との統計的近似性（時間帯別メッセージ頻度・稼働時間、Mann-Whitney U検定で
   4機器中3機器がp>0.05）が報告されている。本研究はこの設計思想を踏襲した独立実装を
   用いるが、当該検証を自身の実装に対して再実施したものではない。」
2. **公開実測データセット（Aruba/CASAS）との比較を引用する**（新規データ収集不要、
   既に本リポジトリにある）:
   [reports/functional_vs_realistic_vs_aruba.md](../reports/functional_vs_realistic_vs_aruba.md)、
   [docs/limitations.md](limitations.md)に実測Arubaとのイベント密度・状態遷移数比較がある。
   ただし現状は数値目標未達（イベント密度でArubaの約3.3%等)と正直に書かれているため、
   「近い」ではなく「差分を定量化した上で評価に用いた」という書き方にする。
3. 上記1・2を組み合わせれば「実世界からかけ離れた恣意的な合成データではない」という
   根拠は示せるが、**「実世界ログの代表サンプルである」という強い主張は避ける**。

### 2.3 Methods節の記述方針（下書き）

> 本研究では、Oliveira et al. のHESTIA [引用] で提案された活動駆動型・離散イベント
> シミュレーションの概念に基づく独立実装のツールを用いて合成スマートホーム操作ログを
> 生成した。本実装はHESTIA原著のソースコード・設定形式・出力プロトコル（Tuya準拠）とは
> 独立であり、原著が実施した実環境とのMann-Whitney U検定による統計的検証を再現した
> ものではない。代わりに、(a) 生成ログが位置・時間・活動・機器状態に関する意味論的
> 不変条件を満たすことを自動検証し、(b) 公開実測データセットAruba/CASASとのイベント
> 密度・状態遷移数の比較により生成データの特性を定量化した。

## 3. 研究テーマ：頻出パターン検出

### 3.1 決定事項（ユーザー回答より）

- 検出対象は「品質」ではなく**頻出パターン**：同じ操作パターンが繰り返し出現する
  ログから、その繰り返しパターンを検出したい。
- 実環境での比較実験は実施しない方針。

### 3.2 未決定事項（次に詰めるべき点）

- [ ] **パターンの定義**: 生イベント列（デバイスON/OFF等の低レベル操作列）を対象にするか、
      活動（ADL）単位の高レベル系列を対象にするか。現実の検出器はground truthのADL
      ラベルを持たない想定が自然なため、**生イベント列を検出器の入力にし、ADLラベルは
      評価時の正解データとしてのみ使う**設計を推奨（未確定・要合意）。
- [ ] パターンの一致判定基準（完全一致か、時間の揺らぎ・順序の入れ替えをどこまで
      許容するか）。

### 3.3 アクションプラン（優先順）

1. [ ] 上記3.2の「パターンの定義」を確定する。
2. [ ] Hestia Studioを使い、以下を意図的に埋め込んだシナリオを設計する。
   - 高頻度で繰り返すactivity（例: 毎日近い時刻の`USE_PC_NIGHT`）
   - 低頻度・一回性のactivity（ディストラクタ）
   - `variation_fraction`（時間の揺らぎ）、副次活動、複数住人の競合による
     「同じパターンでも毎回微妙に違う」自然なノイズ
3. [ ] 複数seed・複数日数でコーパスを生成する（`smart-home-sim simulate`または
   Studioの「実行」タブ）。
4. [ ] 正解ラベルの扱いを決める: 生成された`events.csv`の`Activity`/
   `ActivityUserAction`/`Space`/`ActorInhabitant`列はprecision/recall算出用の
   正解データとして保持し、検出器にはデバイス状態変化列のみを渡す。
5. [ ] 頻出パターン検出アルゴリズム（PrefixSpan、GSP、モチーフ発見等）を実装・適用し、
   埋め込んだ既知パターンの再現率・適合率を測定する。
6. [ ] （任意・発展）`sensor_imperfections`を有効にした観測データに対しても同じ検出を
   行い、欠損・遅延・誤発火下での頑健性を評価する。
7. [ ] Methods節を2.3の下書きをベースに執筆し、頻出パターン検出の評価結果と合わせて
   まとめる。

## 4. 完了済みタスク（本セッション）

- [x] 論文（`references/hestia_paper_v2.pdf`）全17ページの内容確認。
- [x] 既存監査文書（hestia_comparison.md, semantic_audit.md, limitations.md）の
      内容を独立検証（デバイス復元ロジック、デバイス種別、lint/型/テスト）。
- [x] `docs/architecture.md`にHestia Studioの節を追加。
- [x] Studio機能一式（`studio.py`, `studio_static/`, `tests/test_studio.py`,
      関連ドキュメント更新）をコミット（`feat: add Hestia Studio web editor`）。

## 参考文書

- [docs/hestia_comparison.md](hestia_comparison.md) — 論文との機能対応表
- [reports/semantic_audit.md](../reports/semantic_audit.md) — 意味論レベルの監査詳細
- [docs/limitations.md](limitations.md) — 既知の制約
- [docs/research_usage.md](research_usage.md) — 既存研究パイプラインでの使い分け方針
  （本文書の頻出パターン検出とは別の既存研究トラック向け）
- [docs/architecture.md](architecture.md) — アーキテクチャ全体（Studioの節を含む）
- [reports/functional_vs_realistic_vs_aruba.md](../reports/functional_vs_realistic_vs_aruba.md) —
  Aruba実測データとの比較
