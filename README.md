# FastAPI on Render (GPTs Actions backend)

このリポジトリは、GPTs の Actions から叩ける FastAPI サービスの最小構成です。
- 楽天APIで商品検索
- アフィリエイト開示（【PR】表記・rel="sponsored"）
- Bearer 認証
- CORS 設定
- /healthz ヘルスチェック

## 必要な環境変数（Render の「Environment」画面で設定）
- `RAKUTEN_APPLICATION_ID`
- `RAKUTEN_AFFILIATE_ID`
- `GPTS_ACTIONS_BEARER`

## Render 設定（Docker不要）
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/healthz`

## ローカル起動（任意）
```bash
python -m venv .venv && source .venv/bin/activate  # Windowsは .venv\Scripts\activate
pip install -r requirements.txt
export RAKUTEN_APPLICATION_ID=xxx
export RAKUTEN_AFFILIATE_ID=yyy
export GPTS_ACTIONS_BEARER=testtoken
uvicorn app:app --reload --port 8000
```

## cURLテスト
```bash
curl -sS http://localhost:8000/recommend_cooking_tools   -H "Authorization: Bearer testtoken"   -H "Content-Type: application/json"   -d '{"recipe_text":"レンチンで簡単！鶏むね肉...","recipe_title":"レンチン蒸し料理"}' | jq .
```

## GitHub Actions (無料枠で最小CI)
`.github/workflows/ci.yml` を用意済みです。`app.py`/`requirements.txt` 変更時のみ走り、古いジョブを自動キャンセルします。

## GitHub Codespaces（無料枠の節約）
- 最小マシン（2コア）で起動
- Idle timeout を短めに
- Prebuild はOFF 推奨
