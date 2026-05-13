"""
このスクリプトは、Google Gemini APIを使用して利用可能なモデルの一覧を取得し、文章生成が可能なモデルを優先的に表示します。
"""
import os
import importlib
from dotenv import load_dotenv
import sys

# .envファイルから環境変数を読み込む
load_dotenv()

# APIキーを設定（新旧の環境変数名に対応）
api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
if not api_key:
    print("エラー: GEMINI_API_KEY または GOOGLE_API_KEY が設定されていません。", file=sys.stderr)
    sys.exit(1)

try:
    genai_module = importlib.import_module("google.genai")
except ImportError:
    print(
        "エラー: google-genai が見つかりません。`uv add google-genai` を実行してください。",
        file=sys.stderr,
    )
    sys.exit(1)

client = genai_module.Client(api_key=api_key)

print("利用可能なモデルの一覧を取得します...\n")

# 利用可能なモデルをリストアップ
for model in client.models.list():
    # SDKのバージョン差異を吸収しつつ、文章生成が可能なモデルを優先表示する
    methods = (
        getattr(model, "supported_generation_methods", None)
        or getattr(model, "supported_actions", None)
        or []
    )
    if not methods or any("generate" in m.lower() and "content" in m.lower() for m in methods):
        print(getattr(model, "name", "(name unavailable)"))