# 論文掲載用パラメータ一覧

本研究で使用した主要なパラメータを以下にまとめています。論文本体には、以下の「コア設定値」セクションの値を明示してください。

---

## 1. コア設定値（論文に必須記載）

### 1.1 状態遷移ネットワーク構築 (`scripts/run_build_network.py`, `src/behavior_pattern_mining/visualization/state_transition_visualizer.py`)

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| **代表状態の数（K）** | 15 | 頻度上位K個の状態パターンを選定 |
| **ハミング距離の閾値** | 1 | 異なるセンサー数の許容値（これ以上はOther扱い） |
| **最小遷移確率（可視化）** | 0.1 | グラフ表示時の最小エッジ閾値 |
| **データ期間** | 154日 | 分析対象の日数 |
| **データ期間比率** | 0.7 | 全体日数の70%を使用する場合の設定値 |
| **サンプリング間隔** | 1秒 | 状態ベクトル化の時間粒度 |
| **遅延OFF窓幅** | 5秒 | チャタリング除去時のスムージング窓（秒） |

**時間帯モード定義:**
- Morning: 06:00 - 10:00
- Daytime: 10:00 - 18:00
- Night: 18:00 - 24:00 (次日00:00)
- Midnight: 00:00 - 06:00

---

### 1.2 ベースライン手法チェーン（遷移確率ベース）

#### 確率的閾値抽出 (`scripts/run_baselines.py`, `src/behavior_pattern_mining/baselines/transition_probability.py`)

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| **遷移確率の閾値** | 0.2 | 20%以上の遷移エッジのみ選定 |
| **最小系列長** | 2 | 検出する行動パターンの最小ノード数 |
| **最大系列長** | 4 | 検出する行動パターンの最大ノード数 |
| **除外状態** | "その他" | フィルタリング対象の状態 |
| **状態の再訪許可** | False | 同じ状態を複数回通過することを禁止 |
| **TOP_N** | 0 | 0の場合は条件を満たす全パターンを抽出（件数制限なし） |

---

### 1.3 LLM抽出手法 (`scripts/run_llm_extraction.py`, `src/behavior_pattern_mining/llm/pattern_extractor.py`)

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| **モデル名** | gemini-2.5-pro | Google Gemini APIモデル |
| **温度（Temperature）** | 0.2 | 出力の決定性（低いほど確定的） |
| **時間帯別分析** | 有効 | 4つのモード別にPromptを実行 |
| **入力形式** | JSON | 状態遷移ネットワークの構造化データ |

**Prompt仕様:**
- タスク: 状態遷移グラフから生活行動パターンを抽出
- 出力制約: 
  - パターン長: 2〜4ノード
  - 形式: 「パターン名」「解釈の根拠」「遷移のパターン」を含むJSON
  - 行動ルートの網羅性: 遷移確率20%以上のエッジをたどるすべてのパターンを抽出

---

### 1.4 評価指標 (`scripts/run_evaluation.py`, `src/behavior_pattern_mining/evaluation/compare_patterns.py`)

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| **評価対象スコープ** | modes_only | 時間帯モード別の結果のみを評価 |
| **ベースライン1（確率的）** | prob_threshold_sequences | 遷移確率0.2以上のパターン |
| **ベースライン2（頻度ベース）** | state_sequence_counts | 状態遷移の頻出度による抽出 |
| **LLM出力** | llm_sequences_modes | 4時間帯×LLM抽出の統合結果 |
| **部分一致許可（ベース⊇LLM）** | False | 完全一致のみをTP判定 |
| **部分一致許可（LLM⊇ベース）** | False | 完全一致のみをTP判定 |

**評価指標:**
- **Precision**: TP / (TP + FP) — LLMが提案したパターンがベースラインに存在する割合
- **Recall**: TP / (TP + FN) — ベースラインが見つけた頻出パターンをLLMが拾い上げた割合
- **F1-score**: 2 × Precision × Recall / (Precision + Recall) — バランス指標

---

## 2. 実験実行設定 (`scripts/run_llm_eval_batch.py`)

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| **実行回数** | 5 | LLM復数回実行による評価指標の安定性確認 |
| **最大リトライ回数** | 3 | API失敗時（トークン上限等）の再試行上限 |
| **実行間隔** | 0秒 | 試行間の待機時間 |

---

## 3. 関連技術仕様

### 3.1 状態ベクトル化
- **形式**: 各センサーのON/OFF状態を1秒ごとに記録
- **圧縮**: 連続する同じ状態ベクトルを除去し、遷移点のみ保持
- **状態マッピング**: ハミング距離≥1の未知状態は"その他"に分類

### 3.2 時間帯モード分析
- 各モードについて個別に遷移確率行列を計算
- モード外のイベントは評価対象外
- JSONエクスポートは全体版＋4モード版＝5ファイル

### 3.3 LLM統合
- **入力**: 時刻帯別の状態遷移JSON（ノード＆エッジリスト）
- **推論プロセス**: 
  1. 主要状態（長滞在時間、特徴的センサー配置）の解釈
  2. 遷移確率20%以上のエッジをたどる行動ストーリー抽出
  3. JSONフォーマットで出力
- **時間帯別解釈の保持**: 同じ遷移パターンは1つのグループにまとめるが、`time_band_interpretations` に時間帯別のパターン名・ADL系列ラベル・解釈根拠を保持する

---

## 4. 出力ファイル構成

### 4.1 ベースライン出力
```
output/
├── prob_threshold_sequences_154days.json
│   └── [{"states": [...], "probability": ...}, ...]
└── state_sequence_counts_154days.json
    └── [{"states": [...], "frequency": ...}, ...]
```

### 4.2 LLM出力
```
output/
├── llm_sequences_modes_154days.json
│   └── [{"パターン名": "...", "遷移のパターン": [...]}, ...]
└── batch_YYYYMMDD_HHMMSS/
    ├── llm_sequences_modes_154days_1.json (Run 1)
    ├── llm_sequences_modes_154days_2.json (Run 2)
    ├── llm_sequences_modes_154days_3.json (Run 3)
    ├── llm_sequences_modes_154days_4.json (Run 4)
    ├── llm_sequences_modes_154days_5.json (Run 5)
    ├── evaluation_report_154days_1.txt
    ├── evaluation_report_154days_2.txt
    └── llm_eval_runs_154days.xlsx
        - Sheet: "Metrics"
        - Columns: Run | Prob_Precision | Prob_Recall | Prob_F1 | State_Precision | State_Recall | State_F1
        - Last Row: Average metrics across all runs
```

### 4.3 可視化出力
```
picture/
├── aruba_15_1_154days/
│   ├── state_transition_all.png (全期間)
│   ├── state_transition_all.json
│   ├── state_transition_Morning.png
│   ├── state_transition_Morning.json
│   ├── state_transition_Daytime.png
│   ├── state_transition_Daytime.json
│   ├── state_transition_Night.png
│   ├── state_transition_Night.json
│   ├── state_transition_Midnight.png
│   ├── state_transition_Midnight.json
│   ├── timeline_all.png
│   ├── timeline_Morning.png
│   ├── timeline_Daytime.png
│   ├── timeline_Night.png
│   └── timeline_Midnight.png
└── state/
    └── state_state_aruba_15_1_154days.txt
        - 代表状態の詳細（センサー配置）
```

---

## 5. 論文の「方法」セクションで推奨される記述

### 5.1 参考テンプレート

**「本研究では以下のパラメータ設定を採用した：」**

1. **状態遷移ネットワーク構築:**
   - 代表状態K=15（頻度上位）
   - ハミング距離閾値=1
   - サンプリング間隔1秒、遅延OFF窓幅5秒によるセンサーノイズ除去

2. **ベースライン手法（確率的）:**
   - 遷移確率20%以上のエッジを選定
   - 系列長2〜4ノードの組み合わせを列挙
   - 同一状態の再訪は禁止

3. **LLM手法:**
   - モデル: Gemini 2.5 Pro (温度0.2)
   - 時間帯モード4分割での施行
   - 遷移確率20%以上をPromptで咀嚼させる

4. **評価:**
   - Precision/Recall/F1スコアで比較
   - 完全一致のみをTP判定
   - 5回の試行で平均値を算出

---

## 6. 補考：パラメータの根拠

### なぜK=15か
- テスト環境（aruba.csvなど）での最適値
- 過度に細粒度でなく、かつ統計的に有意な代表パターン数

### なぜ閾値0.2か
- 20%以上の遷移確率 = 「複数日で繰り返されやすい」の目安
- 1回限りの偶発的な遷移を除外

### なぜパターン長2〜4か
- 2: 最小の「意味を持つ行動」（A→B）
- 4: 短期の「行動シナリオ」（A→B→C→D）
- 5以上は単に長く、解釈が困難になるため

### なぜ温度0.2か
- 確定的な出力（低温度）で一貫性を確保
- 創造性が不要なタスク（パターン列挙）に適切

---

## 7. 改変履歴

| 版 | 日付 | 変更内容 |
|-----|------|---------|
| 1.0 | 2026-04-28 | 初版テンプレート作成 |
