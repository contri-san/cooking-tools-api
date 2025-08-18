# app.py
import os
import json
from typing import Optional, List, Dict
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==== 環境変数 ====
APPLICATION_ID = os.environ.get("RAKUTEN_APPLICATION_ID")
AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID")
API_BEARER_TOKEN = os.environ.get("GPTS_ACTIONS_BEARER")  # 任意: GPTsのActionsに同値を設定
RAKUTEN_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"

# ==== HTTPセッション（簡易リトライ付き） ====
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"])
)
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))

# ==== 認証（Bearer） ====
def auth_dependency(authorization: Optional[str] = Header(None)):
    if not API_BEARER_TOKEN:
        # トークン未設定ならチェックしない（必要なら必須化しても良い）
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ", 1)[1].strip()
    if token != API_BEARER_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

# ==== FastAPI アプリ本体 ====
app = FastAPI(title="Recipe Cooking Tools Recommendation Functions")

# ヘルスチェック（Render推奨）
@app.get("/")
def root():
    return {"ok": True, "service": "alive"}

# ==== CORS ====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 必要に応じて限定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==== ユーティリティ ====
def _sanitize_url(url: str) -> Optional[str]:
    """アフィリエイトURLを安全側で許可。"""
    try:
        if not url:
            return None
        u = urlparse(url)
        allow_hosts = {
            "item.rakuten.co.jp",
            "books.rakuten.co.jp",
            "hb.afl.rakuten.co.jp",
            "afl.rakuten.co.jp",
            "www.rakuten.co.jp"
        }
        if u.scheme in {"http", "https"} and u.netloc in allow_hosts:
            return url
    except Exception:
        pass
    return None

def _extract_keywords_from_recipe(recipe_text: str) -> List[str]:
    kws: List[str] = []
    if any(k in recipe_text for k in ["レンジ", "電子レンジ", "レンチン"]):
        kws.extend(["電子レンジ調理器", "耐熱容器", "レンジ対応"])
    if any(k in recipe_text for k in ["ゆで卵", "ゆでたまご"]):
        kws.append("ゆで卵メーカー")
    if any(k in recipe_text for k in ["蒸し", "蒸す"]):
        kws.append("スチーマー")
    if any(k in recipe_text for k in ["焼き", "焼く"]):
        kws.append("グリルパン")
    if any(k in recipe_text for k in ["煮物", "煮る"]):
        kws.append("耐熱ボウル")
    if any(k in recipe_text for k in ["ごはん", "ご飯"]):
        kws.append("冷凍ごはん容器")
    kws.extend(["調理器具", "キッチン用品", "保存容器"])
    return list({k for k in kws})

def _search_rakuten_products(keyword: str) -> List[Dict]:
    if not APPLICATION_ID or not AFFILIATE_ID:
        return []
    params = {
        "applicationId": APPLICATION_ID,
        "affiliateId": AFFILIATE_ID,
        "keyword": keyword,
        "format": "json",
        "sort": "-reviewAverage",
        "hits": 10,
        "minReviewAverage": 4.0
    }
    try:
        r = session.get(RAKUTEN_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("Items", [])
        products: List[Dict] = []
        for it in items:
            item = it.get("Item", {})
            img = None
            imgs = item.get("mediumImageUrls") or []
            if imgs:
                img = imgs[0].get("imageUrl")
            prod = {
                "name": item.get("itemName"),
                "price": item.get("itemPrice"),
                "review_average": item.get("reviewAverage"),
                "review_count": item.get("reviewCount"),
                "affiliate_url": item.get("affiliateUrl"),
                "image_url": img,
                "keyword": keyword
            }
            if prod.get("name"):
                products.append(prod)
        return products
    except Exception:
        return []

def _generate_recommendation_html(products: List[Dict], title: str) -> str:
    if not products:
        return "<p>おすすめの料理グッズは見つかりませんでした。</p>"
    html = f"""
<div class="product-recommendations" role="region" aria-label="レンチン調理器具のおすすめ一覧">
  <h2>【PR】🍳 {title}におすすめの料理グッズ</h2>
  <p class="disclosure">
    ※本ページのリンクは<a href="https://www.rakuten.co.jp/" target="_blank" rel="noopener noreferrer">楽天市場</a>のアフィリエイトリンクを含みます。リンク経由のご購入で運営者が報酬を得る場合があります。
  </p>
  <div class="products-grid">
"""
    for i, p in enumerate(products):
        safe_url = _sanitize_url(p.get("affiliate_url") or "")
        href = safe_url or "#"
        rel_attr = "sponsored noopener noreferrer" if safe_url else "noopener noreferrer nofollow"
        name = p.get("name", "")
        price = p.get("price") or 0
        rating = p.get("review_average", "-")
        rcount = p.get("review_count", "-")
        html += f"""
    <div class="product-card">
      <div class="product-rank">#{i+1}</div>
      <div class="product-info">
        <h3 class="product-name">{name}</h3>
        <div class="product-details">
          <span class="price">¥{price:,}</span>
          <span class="rating">⭐ {rating} ({rcount}件)</span>
        </div>
        <a href="{href}" target="_blank" rel="{rel_attr}" class="affiliate-link" aria-label="楽天市場で詳細を見る：{name}">
          楽天市場で詳細を見る
        </a>
      </div>
    </div>
"""
    html += """
  </div>
</div>
<style>
.product-recommendations{max-width:800px;margin:20px auto;padding:20px;font-family:Arial,sans-serif}
.disclosure{font-size:12px;color:#666;margin:8px 0 0 0}
.products-grid{display:grid;gap:15px;margin-top:16px}
.product-card{border:1px solid #ddd;border-radius:8px;padding:15px;background:#f9f9f9;display:flex;align-items:center;gap:15px}
.product-rank{background:#ff6b6b;color:#fff;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;flex-shrink:0}
.product-info{flex:1}
.product-name{margin:0 0 10px 0;font-size:16px;color:#333}
.product-details{display:flex;gap:15px;margin-bottom:10px}
.price{font-weight:bold;color:#e74c3c;font-size:18px}
.rating{color:#f39c12}
.affiliate-link{background:#27ae60;color:#fff;padding:8px 16px;text-decoration:none;border-radius:4px;display:inline-block;font-size:14px}
.affiliate-link:hover{background:#219a52}
</style>
"""
    return html

def recommendCookingTools(recipe_text: str, recipe_title: str = "レンチンレシピ"):
    kws = _extract_keywords_from_recipe(recipe_text)
    if not kws:
        return {
            "success": False,
            "message": "レシピから関連キーワードを抽出できませんでした。",
            "products": [],
            "html": "<p>レシピから関連キーワードを抽出できませんでした。</p>",
            "count": 0
        }
    all_products: List[Dict] = []
    for kw in kws:
        all_products.extend(_search_rakuten_products(kw))

    # 重複排除（先頭50文字）
    uniq = {}
    for p in all_products:
        name = p.get("name")
        if not name:
            continue
        key = name[:50]
        if key not in uniq:
            uniq[key] = p

    products = list(uniq.values())
    products.sort(key=lambda x: (x.get("review_average") or 0), reverse=True)
    top10 = products[:10]
    html = _generate_recommendation_html(top10, recipe_title)

    return {
        "success": True,
        "products": top10,
        "html": html,
        "count": len(top10),
        "message": "おすすめの料理グッズが見つかりました！"
    }

# ==== I/Oモデル ====
class Req(BaseModel):
    recipe_text: str
    recipe_title: Optional[str] = None

class Product(BaseModel):
    name: Optional[str]
    price: Optional[int]
    review_average: Optional[float]
    review_count: Optional[int]
    affiliate_url: Optional[str]
    image_url: Optional[str] = None
    keyword: Optional[str]

class Res(BaseModel):
    success: bool
    products: List[Product]
    html: str
    count: int
    message: str

# ==== エンドポイント ====
@app.post("/recommend_cooking_tools", response_model=Res)
def endpoint(body: Req, _=Depends(auth_dependency)):
    try:
        if not body.recipe_text or not body.recipe_text.strip():
            raise HTTPException(status_code=400, detail="recipe_text is required")
        return recommendCookingTools(body.recipe_text, body.recipe_title or "レンチンレシピ")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
