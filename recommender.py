"""
recommender.py  –  Recommendation Engine

Generates product recommendations using heuristic scoring (no ML library needed).

Three recommendation modes:
  1. get_recommendations(user_id) – personalized, based on interaction history
  2. get_trending()               – most interacted products in the last 7 days
  3. get_top_rated()              – highest average user ratings

Scoring logic for personalised recommendations:
  - Category affinity score  (most important signal)
  - Product popularity score (how often it's interacted with overall)
  - Average rating bonus
  - Novelty boost            (products the user hasn't seen yet)
  - Purchased products are excluded from all recommendations
"""

from collections import defaultdict
from math import sqrt
from database import get_db

# ── Action importance weights ──────────────────────────────────────────────
# Each action type carries a different signal strength.
# For 'rate', the weight is further multiplied by the star value (1-5).
ACTION_WEIGHTS = {
    'purchase': 5,   # Strongest signal – user committed money
    'wishlist': 3,   # Strong intent – saved for later
    'rate':     2,   # Base; multiplied by star rating → 2-10
    'search':   1.5, # User explicitly searched for this product
    'click':    1,   # Weakest – passive browsing interest
}


def get_recommendations(user_id, limit=8):
    """
    Return personalised product recommendations for *user_id*.
    Fast path: only scores products in the user's top categories.
    """
    db = get_db()

    # Fetch user's interaction history (capped for performance)
    rows = db.execute('''
        SELECT i.product_id, i.action, i.rating, p.category
        FROM   interactions i
        JOIN   products     p ON i.product_id = p.product_id
        WHERE  i.user_id = ?
        ORDER  BY i.id DESC
        LIMIT  200
    ''', (user_id,)).fetchall()

    # Cold-start: new user with no history → fall back to trending
    if not rows:
        db.close()
        return get_trending(limit)

    # ── Build category preference scores ──────────────────────────────────
    category_scores = defaultdict(float)
    purchased_ids   = set()
    interacted_ids  = set()

    for row in rows:
        pid      = row['product_id']
        action   = row['action']
        rating   = row['rating']
        category = row['category']
        interacted_ids.add(pid)
        if action == 'purchase':
            purchased_ids.add(pid)
        weight = ACTION_WEIGHTS.get(action, 1)
        if action == 'rate' and rating:
            weight *= float(rating)
        category_scores[category] += weight

    max_score = max(category_scores.values(), default=1)
    for cat in category_scores:
        category_scores[cat] /= max_score

    # Pick top 5 categories to keep the candidate set small
    top_cats = sorted(category_scores, key=category_scores.get, reverse=True)[:5]

    # ── Score only products in the user's top categories ──────────────────
    placeholders = ','.join('?' * len(top_cats))
    candidate_products = db.execute(f'''
        SELECT p.*,
               COALESCE(s.pop, 0)       AS pop,
               COALESCE(s.avg_rating, 0) AS avg_rating
        FROM   products p
        LEFT JOIN (
            SELECT product_id,
                   COUNT(*)   AS pop,
                   AVG(rating) AS avg_rating
            FROM   interactions
            WHERE  product_id IN (
                SELECT product_id FROM products WHERE category IN ({placeholders})
                LIMIT 2000
            )
            GROUP BY product_id
        ) s ON p.product_id = s.product_id
        WHERE  p.category IN ({placeholders})
        LIMIT  500
    ''', top_cats + top_cats).fetchall()
    db.close()

    scored = []
    for p in candidate_products:
        pid = p['product_id']
        if pid in purchased_ids:
            continue
        score  = category_scores.get(p['category'], 0) * 5
        score += (p['pop'] or 0) * 0.3
        if p['avg_rating']:
            score += float(p['avg_rating']) * 0.5
        if pid not in interacted_ids:
            score += 1.5
        scored.append({**dict(p), 'score': round(score, 3)})

    scored.sort(key=lambda x: x['score'], reverse=True)

    # ── Enrich with match_pct and reason ─────────────────────────────────
    top_results = scored[:limit]
    if not top_results:
        return get_trending(limit)

    max_s    = max(p['score'] for p in top_results) or 1
    top_cat  = top_cats[0] if top_cats else ''

    enriched = []
    for p in top_results:
        d = dict(p)
        score = d['score']
        match_pct = int(65 + (score / max_s) * 33) if max_s > 0 else 70
        cat_raw     = d.get('category', '') or ''
        cat_display = cat_raw.split('|')[0].split('&')[0].strip()
        if top_cat and cat_raw == top_cat:
            reason = f"Based on your interest in {cat_display}"
        elif match_pct >= 90:
            reason = f"Top pick in {cat_display}"
        else:
            reason = f"Popular in {cat_display}"
        d['match_pct'] = match_pct
        d['reason']    = reason
        enriched.append(d)

    return enriched


def _cosine_similarity(vec_a: dict, vec_b: dict) -> float:
    """Cosine similarity between two sparse interaction vectors."""
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dot     = sum(vec_a[k] * vec_b[k] for k in common)
    norm_a  = sqrt(sum(v * v for v in vec_a.values()))
    norm_b  = sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_item_based_recommendations(user_id, limit=8):
    """
    Item-Based Collaborative Filtering.

    Logic:
      1. Build a co-interaction vector for each product:
         product_vec[product_id] = {user_id: weighted_score}
         (which users interacted with this product and how strongly)

      2. For each product the target user has interacted with,
         find products whose co-interaction vectors are most similar
         (cosine similarity) — i.e. "products liked by the same crowd".

      3. Aggregate similarity scores across all seed products,
         weighted by how strongly the target user interacted with each seed.

      4. Exclude purchased products. Return top *limit* by score.

    Why item-based beats user-based here:
      - Products are more stable than users — item vectors change slowly.
      - Scales better: you compare N products not M users.
      - Works even for users with sparse history (only 1-2 interactions).
    """
    db = get_db()

    # Load recent interactions only (cap at 5000 for performance)
    all_rows = db.execute('''
        SELECT user_id, product_id, action, rating
        FROM   interactions
        ORDER  BY id DESC
        LIMIT  5000
    ''').fetchall()

    if not all_rows:
        db.close()
        return get_trending(limit)

    # Build product vectors: {product_id: {user_id: weight}}
    product_vectors = defaultdict(lambda: defaultdict(float))
    user_product_weights = defaultdict(lambda: defaultdict(float))

    for r in all_rows:
        uid = r['user_id']
        pid = r['product_id']
        act = r['action']
        w   = ACTION_WEIGHTS.get(act, 1)
        if act == 'rate' and r['rating']:
            w *= float(r['rating'])
        product_vectors[pid][uid] += w
        user_product_weights[uid][pid] += w

    # Get target user's interaction profile
    target_interactions = user_product_weights.get(user_id)
    if not target_interactions:
        db.close()
        return get_trending(limit)

    # Identify purchased products to exclude
    purchased_ids = {
        r['product_id'] for r in all_rows
        if r['user_id'] == user_id and r['action'] == 'purchase'
    }

    # For each product the user has interacted with (seed),
    # compute similarity to all other products
    item_scores = defaultdict(float)
    seed_products = set(target_interactions.keys())

    for seed_pid, seed_weight in target_interactions.items():
        seed_vec = dict(product_vectors[seed_pid])

        for candidate_pid, candidate_vec in product_vectors.items():
            if candidate_pid == seed_pid:
                continue
            if candidate_pid in purchased_ids:
                continue

            sim = _cosine_similarity(seed_vec, dict(candidate_vec))
            if sim > 0:
                # Weight by how much the user liked the seed product
                item_scores[candidate_pid] += sim * seed_weight

    if not item_scores:
        db.close()
        return get_trending(limit)

    # Get top candidates
    top_candidates = sorted(item_scores, key=item_scores.get, reverse=True)[:50]
    placeholders   = ','.join('?' * len(top_candidates))

    products = db.execute(f'''
        SELECT p.*,
               AVG(i.rating)  AS avg_rating,
               COUNT(i.id)    AS pop
        FROM   products p
        LEFT JOIN interactions i ON p.product_id = i.product_id
        WHERE  p.product_id IN ({placeholders})
        GROUP  BY p.product_id
    ''', top_candidates).fetchall()

    scored = []
    for p in products:
        pid   = p['product_id']
        score = item_scores.get(pid, 0)
        if p['avg_rating']:
            score += float(p['avg_rating']) * 0.3
        scored.append({**dict(p), 'score': round(score, 3)})

    scored.sort(key=lambda x: x['score'], reverse=True)
    db.close()
    return scored[:limit]


def get_collaborative_recommendations(user_id, limit=8):
    """
    User-based collaborative filtering.

    Steps:
      1. Build a weighted interaction vector for every user.
         Weights: purchase=5, wishlist=3, rate×stars (2-10), search=1.5, click=1
      2. Compute cosine similarity between the target user and all others.
      3. Pick the top-20 most similar users (neighbours).
      4. Aggregate their product scores weighted by similarity.
      5. Exclude products the target user has already purchased.
      6. Return top *limit* products sorted by aggregated score.

    Falls back to get_trending() for cold-start users (no history).
    """
    db = get_db()

    # Load recent interactions only (cap at 5000 for performance)
    rows = db.execute('''
        SELECT user_id, product_id, action, rating
        FROM   interactions
        ORDER  BY id DESC
        LIMIT  5000
    ''').fetchall()

    if not rows:
        db.close()
        return get_trending(limit)

    # Build per-user interaction vectors  {user_id: {product_id: weight}}
    user_vectors = defaultdict(lambda: defaultdict(float))
    for r in rows:
        uid  = r['user_id']
        pid  = r['product_id']
        act  = r['action']
        w    = ACTION_WEIGHTS.get(act, 1)
        if act == 'rate' and r['rating']:
            w *= float(r['rating'])
        user_vectors[uid][pid] += w

    target_vec = user_vectors.get(user_id)
    if not target_vec:
        db.close()
        return get_trending(limit)          # cold-start fallback

    purchased_ids = {
        pid for pid, w in user_vectors[user_id].items()
        if any(r['product_id'] == pid and r['action'] == 'purchase' and r['user_id'] == user_id
               for r in rows)
    }

    # Compute similarities with all other users
    similarities = []
    for uid, vec in user_vectors.items():
        if uid == user_id:
            continue
        sim = _cosine_similarity(dict(target_vec), dict(vec))
        if sim > 0:
            similarities.append((uid, sim))

    # Keep top-20 neighbours
    similarities.sort(key=lambda x: x[1], reverse=True)
    neighbours = similarities[:20]

    if not neighbours:
        db.close()
        return get_trending(limit)

    # Aggregate product scores from neighbours
    product_scores = defaultdict(float)
    for uid, sim in neighbours:
        for pid, weight in user_vectors[uid].items():
            product_scores[pid] += sim * weight

    # Exclude products the target user already purchased
    for pid in purchased_ids:
        product_scores.pop(pid, None)

    # Also exclude products the target already interacted with heavily
    # (only keep products with a meaningful signal from neighbours)
    candidate_ids = sorted(product_scores, key=product_scores.get, reverse=True)[:50]

    if not candidate_ids:
        db.close()
        return get_trending(limit)

    placeholders = ','.join('?' * len(candidate_ids))
    products = db.execute(f'''
        SELECT p.*,
               AVG(i.rating)  AS avg_rating,
               COUNT(i.id)    AS pop
        FROM   products p
        LEFT JOIN interactions i ON p.product_id = i.product_id
        WHERE  p.product_id IN ({placeholders})
        GROUP  BY p.product_id
    ''', candidate_ids).fetchall()

    scored = []
    for p in products:
        pid   = p['product_id']
        score = product_scores.get(pid, 0)
        # Small quality boost
        if p['avg_rating']:
            score += float(p['avg_rating']) * 0.3
        scored.append({**dict(p), 'score': round(score, 3)})

    scored.sort(key=lambda x: x['score'], reverse=True)
    db.close()
    return scored[:limit]


def get_trending(limit=8):
    """
    Return the most interacted-with products over the last 7 days.
    Ties are broken by average rating (higher-rated products surface first).
    """
    db = get_db()

    products = db.execute('''
        SELECT  p.*,
                COUNT(i.id)   AS interaction_count,
                AVG(i.rating) AS avg_rating
        FROM    products p
        LEFT JOIN interactions i
                  ON  p.product_id = i.product_id
                  AND i.timestamp >= datetime('now', '-7 days')
        GROUP BY p.product_id
        ORDER BY interaction_count DESC, avg_rating DESC
        LIMIT ?
    ''', (limit,)).fetchall()

    db.close()
    return [dict(p) for p in products]


def get_search_recommendations(user_id, query, limit=8, product_ids=None):
    """
    Return products strictly matching query by name or category only.
    If product_ids is provided, use those directly (avoids a second LIKE scan).
    """
    db          = get_db()
    query_lower = query.lower()

    purchased_rows = db.execute('''
        SELECT DISTINCT product_id FROM interactions
        WHERE user_id = ? AND action = 'purchase'
    ''', (user_id,)).fetchall()
    purchased_ids = {r['product_id'] for r in purchased_rows}

    if product_ids:
        if not product_ids:
            db.close()
            return []
        placeholders = ','.join('?' * len(product_ids))
        matching = db.execute(f'''
            SELECT p.*,
                   AVG(i.rating) AS avg_rating,
                   COUNT(i.id)   AS pop
            FROM   products p
            LEFT JOIN interactions i ON p.product_id = i.product_id
            WHERE  p.product_id IN ({placeholders})
            GROUP  BY p.product_id
        ''', product_ids).fetchall()
    else:
        pattern  = f'%{query}%'
        matching = db.execute('''
            SELECT p.*,
                   AVG(i.rating) AS avg_rating,
                   COUNT(i.id)   AS pop
            FROM   products p
            LEFT JOIN interactions i ON p.product_id = i.product_id
            WHERE  p.name LIKE ? OR p.category LIKE ?
            GROUP  BY p.product_id
        ''', (pattern, pattern)).fetchall()

    if not matching:
        db.close()
        return []

    scored = []
    for p in matching:
        pid = p['product_id']
        if pid in purchased_ids:
            continue
        name = (p['name'] or '').lower()
        tier   = 0 if query_lower in name else 1
        score  = (1 - tier) * 10.0
        score += (p['pop'] or 0) * 0.2
        if p['avg_rating']:
            score += float(p['avg_rating']) * 0.5
        scored.append({**dict(p), 'score': round(score, 3)})

    scored.sort(key=lambda x: x['score'], reverse=True)
    db.close()
    return scored[:limit]


def get_search_trending(query, limit=8, product_ids=None):
    """Sort matched products by interaction count. If product_ids provided, use those directly."""
    db          = get_db()
    query_lower = query.lower()

    if product_ids:
        placeholders = ','.join('?' * len(product_ids))
        products = db.execute(f'''
            SELECT  p.*,
                    COUNT(i.id)   AS interaction_count,
                    AVG(i.rating) AS avg_rating
            FROM    products p
            LEFT JOIN interactions i ON p.product_id = i.product_id
            WHERE   p.product_id IN ({placeholders})
            GROUP BY p.product_id
        ''', product_ids).fetchall()
    else:
        pattern  = f'%{query}%'
        products = db.execute('''
            SELECT  p.*,
                    COUNT(i.id)   AS interaction_count,
                    AVG(i.rating) AS avg_rating
            FROM    products p
            LEFT JOIN interactions i ON p.product_id = i.product_id
            WHERE   (p.name LIKE ? OR p.category LIKE ?)
            GROUP BY p.product_id
        ''', (pattern, pattern)).fetchall()

    def trend_score(p):
        name = (p['name'] or '').lower()
        tier = 0 if query_lower in name else 1
        score  = (1 - tier) * 10
        score += (p['interaction_count'] or 0) * 0.5
        if p['avg_rating']:
            score += float(p['avg_rating']) * 0.3
        return score

    result = sorted([dict(p) for p in products], key=trend_score, reverse=True)
    db.close()
    return result[:limit]


def get_search_top_rated(query, limit=8, product_ids=None):
    """Sort matched products by rating. If product_ids provided, use those directly."""
    db          = get_db()
    query_lower = query.lower()

    if product_ids:
        placeholders = ','.join('?' * len(product_ids))
        products = db.execute(f'''
            SELECT  p.*,
                    AVG(CASE WHEN i.rating IS NOT NULL THEN i.rating END) AS avg_rating,
                    COUNT(CASE WHEN i.rating IS NOT NULL THEN 1 END)      AS rating_count
            FROM    products p
            LEFT JOIN interactions i ON p.product_id = i.product_id
            WHERE   p.product_id IN ({placeholders})
            GROUP BY p.product_id
        ''', product_ids).fetchall()
    else:
        pattern  = f'%{query}%'
        products = db.execute('''
            SELECT  p.*,
                    AVG(CASE WHEN i.rating IS NOT NULL THEN i.rating END) AS avg_rating,
                    COUNT(CASE WHEN i.rating IS NOT NULL THEN 1 END)      AS rating_count
            FROM    products p
            LEFT JOIN interactions i ON p.product_id = i.product_id
            WHERE   (p.name LIKE ? OR p.category LIKE ?)
            GROUP BY p.product_id
        ''', (pattern, pattern)).fetchall()

    def rating_score(p):
        name = (p['name'] or '').lower()
        tier = 0 if query_lower in name else 1
        has_rating = 1 if (p['avg_rating'] is not None) else 0
        score  = has_rating * 100
        score += (1 - tier) * 10
        if p['avg_rating']:
            score += float(p['avg_rating']) * 2
            score += (p['rating_count'] or 0) * 0.1
        return score

    result = sorted([dict(p) for p in products], key=rating_score, reverse=True)
    db.close()
    return result[:limit]


def get_top_rated(limit=8):
    """
    Return products with the highest average star rating.
    Only products with at least one rating are included.
    Ties broken by rating count (more votes = more credible score).
    """
    db = get_db()

    products = db.execute('''
        SELECT  p.*,
                AVG(i.rating)   AS avg_rating,
                COUNT(i.rating) AS rating_count
        FROM    products p
        JOIN    interactions i ON p.product_id = i.product_id
        WHERE   i.rating IS NOT NULL
        GROUP BY p.product_id
        HAVING  rating_count >= 1
        ORDER BY avg_rating DESC, rating_count DESC
        LIMIT ?
    ''', (limit,)).fetchall()

    db.close()
    return [dict(p) for p in products]


# ── MOOD CATEGORY KEYWORDS ─────────────────────────────────────────────────
MOOD_CATEGORY_KEYWORDS = {
    'gifting':    ['Toys', 'Jewellery', 'Beauty', 'Watches', 'Bags', 'Books', 'Music', 'Gift'],
    'self-treat': ['Electronics', 'Beauty', 'Health', 'Fashion', 'Clothing', 'Shoes', 'Skincare'],
    'urgent':     ['Health', 'Grocery', 'Electronics', 'Home', 'Kitchen', 'Office'],
    'exploring':  ['Books', 'Sports', 'Music', 'Toys', 'Art', 'Garden', 'Craft', 'Fitness'],
}


def get_budget_picks(max_price, limit=8):
    """
    Return best-rated products whose price is <= max_price.
    Results are diversified across categories so the user sees variety.
    """
    db = get_db()

    products = db.execute('''
        SELECT p.*,
               AVG(i.rating) AS avg_rating,
               COUNT(i.id)   AS pop
        FROM   products p
        LEFT JOIN interactions i ON p.product_id = i.product_id
        WHERE  p.price > 0 AND p.price <= ?
        GROUP  BY p.product_id
        ORDER  BY avg_rating DESC, pop DESC
        LIMIT  ?
    ''', (max_price, limit * 5)).fetchall()
    db.close()

    # Diversify by category first
    seen_cats, result = set(), []
    for p in products:
        d   = dict(p)
        cat = d.get('category', '')
        if cat not in seen_cats:
            seen_cats.add(cat)
            result.append(d)
        if len(result) >= limit:
            break

    # Fill remaining without diversity constraint
    if len(result) < limit:
        existing_ids = {p['product_id'] for p in result}
        for p in products:
            d = dict(p)
            if d['product_id'] not in existing_ids:
                result.append(d)
            if len(result) >= limit:
                break

    return result[:limit]


def get_surprise_recommendations(user_id, limit=8):
    """
    Return top-rated products from categories the user has NEVER interacted with.
    If the user has seen all categories, fall back to least-interacted categories.
    """
    import random

    db = get_db()

    # Categories the user has already interacted with
    seen_rows = db.execute('''
        SELECT DISTINCT p.category
        FROM   interactions i
        JOIN   products p ON i.product_id = p.product_id
        WHERE  i.user_id = ?
    ''', (user_id,)).fetchall()
    seen_cats = {r['category'] for r in seen_rows}

    # All distinct categories in the product catalog
    all_cat_rows = db.execute(
        'SELECT DISTINCT category FROM products WHERE category IS NOT NULL'
    ).fetchall()
    all_cats = [r['category'] for r in all_cat_rows]

    unseen = [c for c in all_cats if c not in seen_cats]
    if not unseen:
        unseen = all_cats          # fallback: user has seen everything

    random.shuffle(unseen)
    selected_cats = unseen[:limit]

    result = []
    for cat in selected_cats:
        row = db.execute('''
            SELECT p.*,
                   AVG(i.rating) AS avg_rating,
                   COUNT(i.id)   AS pop
            FROM   products p
            LEFT JOIN interactions i ON p.product_id = i.product_id
            WHERE  p.category = ?
            GROUP  BY p.product_id
            ORDER  BY avg_rating DESC, pop DESC
            LIMIT  1
        ''', (cat,)).fetchone()
        if row:
            result.append(dict(row))

    db.close()
    return result


def get_mood_picks(mood, limit=8):
    """
    Return top-rated products matching the chosen mood/occasion.
    Each mood maps to a list of category keywords that are LIKE-searched.
    """
    keywords = MOOD_CATEGORY_KEYWORDS.get(mood, [])
    if not keywords:
        return get_trending(limit)

    db      = get_db()
    result  = []
    seen_ids = set()

    for kw in keywords:
        rows = db.execute('''
            SELECT p.*,
                   AVG(i.rating) AS avg_rating,
                   COUNT(i.id)   AS pop
            FROM   products p
            LEFT JOIN interactions i ON p.product_id = i.product_id
            WHERE  p.category LIKE ?
            GROUP  BY p.product_id
            ORDER  BY avg_rating DESC, pop DESC
            LIMIT  3
        ''', (f'%{kw}%',)).fetchall()

        for row in rows:
            if row['product_id'] not in seen_ids:
                seen_ids.add(row['product_id'])
                result.append(dict(row))
        if len(result) >= limit:
            break

    db.close()
    return result[:limit]
