"""
app.py  -  SmartShop Flask Application

Routes:
  GET      /login                 -> Redirect to React SPA
  GET      /register              -> Redirect to React SPA
  GET      /logout                -> Logout (clears session)
  GET      /                      -> React SPA (frontend/dist)
  POST     /api/login             -> Login (JSON)
  POST     /api/register          -> Register (JSON)
  POST     /api/logout            -> Logout (JSON)
  GET      /api/me                -> Current user info (JSON)
  GET      /products              -> All products (JSON)
  GET      /search                -> Search products + record interactions (JSON)
  GET      /search-recommend/<u>  -> Recommendations based on search (JSON)
  POST     /interact              -> Record user interaction (JSON)
  GET      /recommend/<user_id>   -> Personalised recommendations (JSON)
  GET      /trending              -> Trending products (JSON)
  GET      /top-rated             -> Top-rated products (JSON)
  GET      /wishlist/<user_id>    -> Wishlist items (JSON)
  GET      /user_purchases/<u>    -> Purchased products (JSON)
"""

import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import (Flask, request, jsonify,
                   session, redirect, url_for, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash

from database import init_db, get_db

# ── Email Configuration ────────────────────────────────────────────────────
# Replace these with your Gmail address and App Password.
# Get an App Password at: myaccount.google.com → Security → App passwords
EMAIL_SENDER   = 'impanasubbanna2004@gmail.com'
EMAIL_PASSWORD = 'mlbhhmlxemvtdczi'
EMAIL_ENABLED  = True
# ──────────────────────────────────────────────────────────────────────────

# ── Dummy Payment (simulated) ────────────────────────────────────────────
# No real payment gateway needed — orders with UPI/Card use a fake pay_id
import uuid as _uuid
# ──────────────────────────────────────────────────────────────────────────
from recommender import (get_recommendations, get_trending,
                         get_top_rated, get_search_recommendations,
                         get_search_trending, get_search_top_rated,
                         get_collaborative_recommendations,
                         get_item_based_recommendations,
                         get_budget_picks, get_surprise_recommendations,
                         get_mood_picks)

app = Flask(__name__)
app.secret_key = 'smartshop_ecommerce_secret_2024'

init_db()

# ── Email helper ────────────────────────────────────────────────────────────
def _send_cart_email(to_email, user_name, product_name, product_price, product_image):
    """Send an HTML cart-confirmation email. Runs in a background thread."""
    if not EMAIL_ENABLED:
        return
    try:
        price_str = ('₹' + f'{float(product_price):,.0f}') if product_price else ''
        img_block = (
            f'<img src="{product_image}" alt="product" '
            f'style="max-width:140px;border-radius:8px;margin-bottom:12px;">'
            if product_image else ''
        )
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:540px;margin:auto;
                    background:#faf9ff;border-radius:12px;overflow:hidden;
                    border:1px solid #ede9fe;">
          <div style="background:#6c63ff;padding:24px 28px;">
            <h2 style="color:#fff;margin:0;font-size:1.3rem;">🛒 Added to Cart!</h2>
          </div>
          <div style="padding:28px;text-align:center;">
            {img_block}
            <p style="font-size:1rem;color:#374151;margin:0 0 6px;">Hi <strong>{user_name}</strong>,</p>
            <p style="font-size:0.95rem;color:#6b7280;margin:0 0 18px;">
              You just added the following item to your cart:
            </p>
            <div style="background:#fff;border-radius:10px;border:1.5px solid #ede9fe;
                        padding:16px 20px;margin-bottom:18px;">
              <p style="font-size:1.05rem;font-weight:700;color:#111827;margin:0 0 6px;">{product_name}</p>
              {f'<p style="font-size:1.2rem;font-weight:900;color:#6c63ff;margin:0;">{price_str}</p>' if price_str else ''}
            </div>
            <p style="font-size:0.82rem;color:#9ca3af;margin:0;">Thanks for shopping with SmartShop!</p>
          </div>
        </div>
        """
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'🛒 Cart Update – {product_name[:50]}'
        msg['From']    = f'SmartShop <{EMAIL_SENDER}>'
        msg['To']      = to_email
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
        print(f'[Email] Cart email sent to {to_email}')
    except Exception as exc:
        print(f'[Email] Failed to send to {to_email}: {exc}')


def _send_order_email(to_email, user_name, order_id, items, total, discount, method):
    """Send an HTML order-confirmation email. Runs in a background thread."""
    if not EMAIL_ENABLED:
        return
    try:
        rows_html = ''.join(
            f'<tr>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;">{i["name"]}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;text-align:center;">{i["quantity"]}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;text-align:right;">₹{i["price"]:,.0f}</td>'
            f'</tr>'
            for i in items
        )
        discount_row = (
            f'<tr><td colspan="2" style="padding:4px 8px;color:#16a34a;font-weight:600;">Coupon Discount</td>'
            f'<td style="padding:4px 8px;text-align:right;color:#16a34a;">-₹{discount:,.0f}</td></tr>'
        ) if discount > 0 else ''
        method_label = {'cod': 'Cash on Delivery', 'upi': 'UPI', 'card': 'Credit/Debit Card'}.get(method, method)
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;
                    background:#faf9ff;border-radius:12px;overflow:hidden;
                    border:1px solid #ede9fe;">
          <div style="background:linear-gradient(135deg,#6c63ff,#9c5aff);padding:24px 28px;">
            <h2 style="color:#fff;margin:0;font-size:1.3rem;">✅ Order Confirmed!</h2>
            <p style="color:#e0d9ff;margin:4px 0 0;font-size:0.88rem;">Order #{order_id}</p>
          </div>
          <div style="padding:28px;">
            <p style="color:#374151;margin:0 0 16px;">Hi <strong>{user_name}</strong>, your order is confirmed!</p>
            <table style="width:100%;border-collapse:collapse;font-size:0.85rem;margin-bottom:16px;">
              <thead>
                <tr style="background:#f5f3ff;">
                  <th style="padding:8px;text-align:left;">Product</th>
                  <th style="padding:8px;text-align:center;">Qty</th>
                  <th style="padding:8px;text-align:right;">Price</th>
                </tr>
              </thead>
              <tbody>
                {rows_html}
                {discount_row}
                <tr style="background:#f5f3ff;font-weight:800;">
                  <td colspan="2" style="padding:8px;">Total</td>
                  <td style="padding:8px;text-align:right;color:#6c63ff;">₹{total:,.0f}</td>
                </tr>
              </tbody>
            </table>
            <p style="font-size:0.82rem;color:#6b7280;margin:0 0 6px;">
              💳 Payment: <strong>{method_label}</strong>
            </p>
            <p style="font-size:0.82rem;color:#6b7280;margin:0 0 20px;">
              📦 Estimated Delivery: <strong>3–5 Business Days</strong>
            </p>
            <p style="font-size:0.75rem;color:#9ca3af;margin:0;">
              Thank you for shopping with SmartShop!
            </p>
          </div>
        </div>
        """
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'✅ Order #{order_id} Confirmed – SmartShop'
        msg['From']    = f'SmartShop <{EMAIL_SENDER}>'
        msg['To']      = to_email
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
        print(f'[Email] Order confirmation sent to {to_email}')
    except Exception as exc:
        print(f'[Email] Order email failed: {exc}')


#  Auth helpers 
def login_required(f):
    """Redirect to / if no session exists."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# 
# AUTH ROUTES
# 

@app.route('/login')
def login():
    return redirect(url_for('index'))


@app.route('/register')
def register():
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ── JSON Auth API (used by React landing page) ─────────────────────────────

@app.route('/api/login', methods=['POST'])
def api_login():
    data     = request.get_json(silent=True) or {}
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')
    if not email or not password:
        return jsonify({'ok': False, 'error': 'Email and password are required.'})
    db   = get_db()
    user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    db.close()
    if user and user['password_hash'] and check_password_hash(user['password_hash'], password):
        session['user_id']   = user['user_id']
        session['user_name'] = user['name']
        return jsonify({'ok': True, 'user': {'user_id': user['user_id'], 'user_name': user['name']}})
    return jsonify({'ok': False, 'error': 'Invalid email or password.'})


@app.route('/api/register', methods=['POST'])
def api_register():
    data     = request.get_json(silent=True) or {}
    name     = data.get('name', '').strip()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')
    if not name or not email or not password:
        return jsonify({'ok': False, 'error': 'All fields are required.'})
    if len(password) < 6:
        return jsonify({'ok': False, 'error': 'Password must be at least 6 characters.'})
    if '@' not in email:
        return jsonify({'ok': False, 'error': 'Please enter a valid email address.'})
    db       = get_db()
    existing = db.execute('SELECT user_id FROM users WHERE email = ?', (email,)).fetchone()
    if existing:
        db.close()
        return jsonify({'ok': False, 'error': 'An account with that email already exists.'})
    pw_hash = generate_password_hash(password)
    cursor  = db.execute('INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
                         (name, email, pw_hash))
    db.commit()
    new_id = cursor.lastrowid
    db.close()
    session['user_id']   = new_id
    session['user_name'] = name
    return jsonify({'ok': True, 'user': {'user_id': new_id, 'user_name': name}})



@app.route('/')
def index():
    response = send_from_directory('frontend/dist', 'index.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return response


@app.route('/assets/<path:filename>')
def react_assets(filename):
    return send_from_directory('frontend/dist/assets', filename)


@app.route('/api/me')
def me():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    db  = get_db()
    row = db.execute('SELECT loyalty_points FROM users WHERE user_id=?',
                     (session['user_id'],)).fetchone()
    db.close()
    pts = row['loyalty_points'] if row and row['loyalty_points'] else 0
    return jsonify({
        'user_id':        session['user_id'],
        'user_name':      session['user_name'],
        'loyalty_points': pts,
    })


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})


# 
# PRODUCT APIs
# 

@app.route('/products')
@login_required
def products():
    db   = get_db()
    rows = db.execute('SELECT * FROM products ORDER BY category, name').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/search')
@login_required
def search():
    """
    Search products by name / description / category.
    Results are sorted by relevance:
      0 - exact name match
      1 - name starts with query
      2 - name contains query
      3 - description / category match only
    The top result is tagged best_match=True when its score <= 2.
    Returns: { results: [...], recommendations: [...] }
    """
    query   = request.args.get('q', '').strip()
    user_id = session['user_id']

    if not query:
        return jsonify({'results': [], 'recommendations': []})

    pattern     = f'%{query}%'
    query_lower = query.lower()
    db          = get_db()

    # Search name + category only — no description broadening
    rows = db.execute('''
        SELECT * FROM products
        WHERE  name     LIKE ?
           OR  category LIKE ?
        LIMIT  60
    ''', (pattern, pattern)).fetchall()

    # Sort by relevance
    def relevance(p):
        name = (p['name'] or '').lower()
        if name == query_lower:
            return 0
        if name.startswith(query_lower):
            return 1
        if query_lower in name:
            return 2
        return 3

    result_list = sorted([dict(r) for r in rows], key=relevance)

    # Tag the top result as best_match if it is a name-level hit
    if result_list and relevance(result_list[0]) <= 2:
        result_list[0]['best_match'] = True

    # Record search interactions for the top matches
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for p in result_list[:5]:
        db.execute(
            'INSERT INTO interactions (user_id, product_id, action, rating, timestamp)'
            ' VALUES (?, ?, ?, ?, ?)',
            (user_id, p['product_id'], 'search', None, ts)
        )
    db.commit()
    db.close()

    # Derive all 3 sections from the same matched products — run in parallel
    matched_ids = [p['product_id'] for p in result_list]

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_recs    = ex.submit(get_search_recommendations, user_id, query, 8, matched_ids)
        f_trend   = ex.submit(get_search_trending,        query, 8, matched_ids)
        f_top     = ex.submit(get_search_top_rated,       query, 8, matched_ids)

    return jsonify({
        'results':         result_list,
        'recommendations': f_recs.result(),
        'trending':        f_trend.result(),
        'top_rated':       f_top.result(),
    })


@app.route('/interact', methods=['POST'])
@login_required
def interact():
    data       = request.get_json(silent=True) or {}
    user_id    = session['user_id']          # use session, not body, for security
    product_id = data.get('product_id')
    action     = data.get('action')
    rating     = data.get('rating')

    if not all([product_id, action]):
        return jsonify({'error': 'product_id and action are required'}), 400

    valid_actions = {'click', 'wishlist', 'rate', 'purchase', 'search'}
    if action not in valid_actions:
        return jsonify({'error': f'action must be one of: {sorted(valid_actions)}'}), 400

    if action == 'rate':
        if rating is None:
            return jsonify({'error': 'rating (1-5) required for rate action'}), 400
        try:
            rating = float(rating)
            if not (1.0 <= rating <= 5.0):
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({'error': 'rating must be 1-5'}), 400
    else:
        rating = None

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db = get_db()
    db.execute(
        'INSERT INTO interactions (user_id, product_id, action, rating, timestamp)'
        ' VALUES (?,?,?,?,?)',
        (user_id, product_id, action, rating, timestamp)
    )
    db.commit()

    db.close()
    return jsonify({'success': True, 'message': f'Action "{action}" recorded'})


@app.route('/recommend/<int:user_id>')
@login_required
def recommend(user_id):
    limit = request.args.get('limit', 8, type=int)
    return jsonify(get_recommendations(user_id, limit=limit))


@app.route('/trending')
@login_required
def trending():
    limit = request.args.get('limit', 8, type=int)
    return jsonify(get_trending(limit=limit))


@app.route('/top-rated')
@login_required
def top_rated():
    limit = request.args.get('limit', 8, type=int)
    return jsonify(get_top_rated(limit=limit))


@app.route('/wishlist/<int:user_id>')
@login_required
def wishlist(user_id):
    db   = get_db()
    rows = db.execute('''
        SELECT DISTINCT p.*, i.timestamp
        FROM   interactions i
        JOIN   products     p ON i.product_id = p.product_id
        WHERE  i.user_id = ? AND i.action = 'wishlist'
        ORDER  BY i.timestamp DESC
    ''', (user_id,)).fetchall()
    db.close()

    seen, result = set(), []
    for r in rows:
        d = dict(r)
        if d['product_id'] not in seen:
            seen.add(d['product_id'])
            result.append(d)
    return jsonify(result)


@app.route('/wishlist/<int:user_id>/<product_id>', methods=['DELETE'])
@login_required
def remove_wishlist(user_id, product_id):
    if session.get('user_id') != user_id:
        return jsonify({'error': 'Forbidden'}), 403
    db = get_db()
    db.execute(
        'DELETE FROM interactions WHERE user_id = ? AND product_id = ? AND action = ?',
        (user_id, product_id, 'wishlist')
    )
    db.commit()
    db.close()
    return jsonify({'success': True})


@app.route('/user_purchases/<int:user_id>')
@login_required
def user_purchases(user_id):
    db   = get_db()
    rows = db.execute('''
        SELECT DISTINCT p.*
        FROM   interactions i
        JOIN   products     p ON i.product_id = p.product_id
        WHERE  i.user_id = ? AND i.action = 'purchase'
        ORDER  BY i.timestamp DESC
    ''', (user_id,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/cart/<int:user_id>/<product_id>', methods=['DELETE'])
@login_required
def remove_cart(user_id, product_id):
    if session.get('user_id') != user_id:
        return jsonify({'error': 'Forbidden'}), 403
    db = get_db()
    db.execute(
        'DELETE FROM interactions WHERE user_id = ? AND product_id = ? AND action = ?',
        (user_id, product_id, 'purchase')
    )
    db.commit()
    db.close()
    return jsonify({'success': True})


@app.route('/product/<int:product_id>')
@login_required
def get_product_detail(product_id):
    db = get_db()
    product = db.execute('SELECT * FROM products WHERE product_id = ?', (product_id,)).fetchone()
    if not product:
        db.close()
        return jsonify({'error': 'Not found'}), 404

    reviews = db.execute('''
        SELECT u.name AS user_name, i.rating, i.timestamp
        FROM   interactions i
        JOIN   users u ON i.user_id = u.user_id
        WHERE  i.product_id = ? AND i.action = 'rate' AND i.rating IS NOT NULL
        ORDER  BY i.timestamp DESC
        LIMIT  20
    ''', (product_id,)).fetchall()

    agg = db.execute('''
        SELECT AVG(rating) AS avg_rating, COUNT(rating) AS rating_count
        FROM   interactions
        WHERE  product_id = ? AND action = 'rate' AND rating IS NOT NULL
    ''', (product_id,)).fetchone()
    db.close()

    result = dict(product)
    result['reviews'] = [dict(r) for r in reviews]
    result['avg_rating'] = round(agg['avg_rating'], 1) if agg['avg_rating'] else None
    result['rating_count'] = agg['rating_count'] or 0
    return jsonify(result)


@app.route('/recently-viewed/<int:user_id>')
@login_required
def recently_viewed(user_id):
    db = get_db()
    rows = db.execute('''
        SELECT p.*, i.timestamp
        FROM   interactions i
        JOIN   products p ON i.product_id = p.product_id
        WHERE  i.user_id = ? AND i.action = 'click'
        ORDER  BY i.timestamp DESC
        LIMIT  40
    ''', (user_id,)).fetchall()
    db.close()
    seen, result = set(), []
    for r in rows:
        d = dict(r)
        if d['product_id'] not in seen:
            seen.add(d['product_id'])
            result.append(d)
            if len(result) >= 8:
                break
    return jsonify(result)


@app.route('/because-you-bought/<int:user_id>')
@login_required
def because_you_bought(user_id):
    recs = get_item_based_recommendations(user_id, limit=8)
    db = get_db()
    seed_row = db.execute('''
        SELECT p.name, p.product_id
        FROM   interactions i
        JOIN   products p ON i.product_id = p.product_id
        WHERE  i.user_id = ? AND i.action = 'purchase'
        ORDER  BY i.timestamp DESC
        LIMIT  1
    ''', (user_id,)).fetchone()
    db.close()
    seed = dict(seed_row) if seed_row else None
    return jsonify({'recommendations': recs, 'seed': seed})


@app.route('/budget-picks')
@login_required
def budget_picks():
    try:
        max_price = float(request.args.get('max', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'max must be a number'}), 400
    if max_price <= 0:
        return jsonify({'error': 'max must be greater than 0'}), 400
    limit = request.args.get('limit', 8, type=int)
    return jsonify(get_budget_picks(max_price, limit=limit))


@app.route('/surprise/<int:user_id>')
@login_required
def surprise(user_id):
    limit = request.args.get('limit', 8, type=int)
    return jsonify(get_surprise_recommendations(user_id, limit=limit))


@app.route('/mood-picks')
@login_required
def mood_picks():
    mood  = request.args.get('mood', '').strip().lower()
    valid = {'gifting', 'self-treat', 'urgent', 'exploring'}
    if mood not in valid:
        return jsonify({'error': f'mood must be one of: {sorted(valid)}'}), 400
    limit = request.args.get('limit', 8, type=int)
    return jsonify(get_mood_picks(mood, limit=limit))


# ══════════════════════════════════════════════════════════════════════════════
#  COUPON VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/coupon/validate', methods=['POST'])
@login_required
def validate_coupon():
    data  = request.get_json(silent=True) or {}
    code  = str(data.get('code', '')).strip().upper()
    total = float(data.get('total', 0))

    if not code:
        return jsonify({'ok': False, 'error': 'Please enter a coupon code.'})

    db  = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    coupon = db.execute(
        '''SELECT * FROM coupons
           WHERE  code = ? AND is_active = 1
             AND  (expires_at IS NULL OR expires_at > ?)
             AND  used_count < max_uses''',
        (code, now)
    ).fetchone()
    db.close()

    if not coupon:
        return jsonify({'ok': False, 'error': 'Invalid or expired coupon code.'})
    if total < coupon['min_order']:
        return jsonify({'ok': False,
                        'error': f'Minimum order of ₹{coupon["min_order"]:,.0f} required.'})

    if coupon['discount_type'] == 'percent':
        discount = round(total * coupon['discount_value'] / 100, 2)
        description = f'{int(coupon["discount_value"])}% off'
    else:
        discount    = min(coupon['discount_value'], total)
        description = f'₹{coupon["discount_value"]:,.0f} off'

    return jsonify({'ok': True, 'discount': discount,
                    'description': description, 'code': coupon['code']})


# ══════════════════════════════════════════════════════════════════════════════
#  CHECKOUT  –  place order (mock/COD/UPI/Card simulation)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/checkout/place-order', methods=['POST'])
@login_required
def place_order():
    data       = request.get_json(silent=True) or {}
    user_id    = session['user_id']
    address    = str(data.get('address', '')).strip()
    coupon     = str(data.get('coupon_code', '')).strip().upper()
    method     = data.get('payment_method', 'cod')
    payment_id = data.get('payment_id', '')
    items      = data.get('items', [])   # [{product_id, quantity}]
    loyalty_pts = int(data.get('loyalty_points', 0) or 0)  # points to redeem

    if not address:
        return jsonify({'ok': False, 'error': 'Shipping address is required.'}), 400
    if not items:
        return jsonify({'ok': False, 'error': 'Cart is empty.'}), 400
    if method not in ('cod', 'upi', 'card'):
        return jsonify({'ok': False, 'error': 'Invalid payment method.'}), 400

    db      = get_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Verify products, prices and stock server-side
    verified, subtotal = [], 0.0
    for item in items:
        pid = item.get('product_id')
        qty = max(1, int(item.get('quantity', 1)))
        row = db.execute(
            'SELECT product_id, name, price, stock FROM products WHERE product_id = ?',
            (pid,)
        ).fetchone()
        if not row:
            db.close()
            return jsonify({'ok': False, 'error': f'Product {pid} not found.'}), 400
        stock = row['stock'] if row['stock'] is not None else 999
        if stock < qty:
            db.close()
            return jsonify({'ok': False,
                            'error': f'"{row["name"]}" is out of stock.'}), 400
        verified.append({'product_id': row['product_id'],
                         'name': row['name'],
                         'price': row['price'],
                         'quantity': qty})
        subtotal += row['price'] * qty

    # Apply coupon
    discount, coupon_code = 0.0, None
    if coupon:
        cp = db.execute(
            '''SELECT * FROM coupons
               WHERE  code = ? AND is_active = 1
                 AND  (expires_at IS NULL OR expires_at > ?)
                 AND  used_count < max_uses''',
            (coupon, now_str)
        ).fetchone()
        if cp and subtotal >= cp['min_order']:
            coupon_code = cp['code']
            if cp['discount_type'] == 'percent':
                discount = round(subtotal * cp['discount_value'] / 100, 2)
            else:
                discount = min(cp['discount_value'], subtotal)
            db.execute('UPDATE coupons SET used_count = used_count + 1 WHERE id = ?',
                       (cp['id'],))

    # Apply loyalty points (10 pts = ₹1)
    loyalty_discount = 0.0
    if loyalty_pts > 0:
        user_pts_row = db.execute('SELECT loyalty_points FROM users WHERE user_id=?', (user_id,)).fetchone()
        available    = user_pts_row['loyalty_points'] if user_pts_row and user_pts_row['loyalty_points'] else 0
        pts_to_use   = min(loyalty_pts, available)
        loyalty_discount = round(pts_to_use / 10, 2)
        if pts_to_use > 0:
            db.execute('UPDATE users SET loyalty_points = loyalty_points - ? WHERE user_id=?',
                       (pts_to_use, user_id))
        discount += loyalty_discount

    total = round(subtotal - discount, 2)

    # Create order record
    cur = db.execute(
        '''INSERT INTO orders
             (user_id, status, total, discount, coupon_code, address,
              payment_method, payment_id, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (user_id, 'placed', total, discount, coupon_code, address,
         method, payment_id, now_str, now_str)
    )
    order_id = cur.lastrowid

    for item in verified:
        db.execute(
            'INSERT INTO order_items (order_id, product_id, quantity, unit_price)'
            ' VALUES (?,?,?,?)',
            (order_id, item['product_id'], item['quantity'], item['price'])
        )
        # Decrement stock (floor at 0)
        db.execute(
            'UPDATE products SET stock = MAX(0, stock - ?) WHERE product_id = ?',
            (item['quantity'], item['product_id'])
        )
        # Clear from cart (purchase interactions) – keep for recommendation history
        db.execute(
            'DELETE FROM interactions'
            ' WHERE user_id=? AND product_id=? AND action=?',
            (user_id, item['product_id'], 'purchase')
        )

    db.commit()

    # Earn loyalty points: 1 point per ₹10 spent
    points_earned = int(total // 10)
    if points_earned > 0:
        db.execute('UPDATE users SET loyalty_points = COALESCE(loyalty_points,0) + ? WHERE user_id = ?',
                   (points_earned, user_id))
        db.commit()

    # Send order confirmation email in background
    user_row = db.execute('SELECT name, email FROM users WHERE user_id = ?',
                          (user_id,)).fetchone()
    db.close()

    if user_row and user_row['email']:
        threading.Thread(
            target=_send_order_email,
            args=(user_row['email'], user_row['name'], order_id,
                  verified, total, discount, method),
            daemon=True
        ).start()

    return jsonify({'ok': True, 'order_id': order_id,
                    'total': total, 'discount': discount,
                    'message': 'Order placed successfully!'})


# ══════════════════════════════════════════════════════════════════════════════
#  ORDER HISTORY
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/orders')
@login_required
def get_orders():
    user_id = session['user_id']
    db = get_db()
    orders = db.execute(
        'SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()
    result = []
    for o in orders:
        od = dict(o)
        items = db.execute(
            '''SELECT oi.*, p.name, p.image, p.category
               FROM   order_items oi
               JOIN   products    p  ON oi.product_id = p.product_id
               WHERE  oi.order_id = ?''',
            (o['order_id'],)
        ).fetchall()
        od['items'] = [dict(i) for i in items]
        result.append(od)
    db.close()
    return jsonify(result)


@app.route('/api/orders/<int:order_id>')
@login_required
def get_order(order_id):
    user_id = session['user_id']
    db = get_db()
    order = db.execute(
        'SELECT * FROM orders WHERE order_id = ? AND user_id = ?',
        (order_id, user_id)
    ).fetchone()
    if not order:
        db.close()
        return jsonify({'error': 'Order not found'}), 404
    items = db.execute(
        '''SELECT oi.*, p.name, p.image, p.category
           FROM   order_items oi
           JOIN   products    p ON oi.product_id = p.product_id
           WHERE  oi.order_id = ?''',
        (order_id,)
    ).fetchall()
    db.close()
    result = dict(order)
    result['items'] = [dict(i) for i in items]
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════════════
#  FLASH SALES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/flash-sales')
@login_required
def flash_sales_api():
    db  = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = db.execute(
        '''SELECT fs.*, p.name, p.image, p.category, p.description, p.stock
           FROM   flash_sales fs
           JOIN   products    p  ON fs.product_id = p.product_id
           WHERE  fs.is_active = 1 AND fs.end_time > ?
           ORDER  BY fs.discount_pct DESC
           LIMIT  12''',
        (now,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════════════════════════
#  DUMMY PAYMENT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/payment/create-order', methods=['POST'])
@login_required
def create_dummy_order():
    """Simulate payment order creation — always succeeds instantly."""
    data   = request.get_json(silent=True) or {}
    amount = data.get('amount', 0)
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Invalid amount.'}), 400

    return jsonify({
        'ok':      True,
        'dummy_order_id': f'dummy_{_uuid.uuid4().hex[:12]}',
        'amount':  int(round(amount * 100)),
        'currency': 'INR',
    })


@app.route('/api/payment/verify', methods=['POST'])
@login_required
def verify_dummy_payment():
    """Simulate payment verification — always succeeds."""
    data       = request.get_json(silent=True) or {}
    payment_id = data.get('payment_id', f'pay_{_uuid.uuid4().hex[:16]}')
    return jsonify({'ok': True, 'payment_id': payment_id})


# ══════════════════════════════════════════════════════════════════════════════
#  SEARCH AUTOCOMPLETE
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/search/suggestions')
@login_required
def search_suggestions():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    db   = get_db()
    rows = db.execute(
        '''SELECT product_id, name, category, price, image
           FROM   products
           WHERE  name LIKE ? OR category LIKE ?
           ORDER  BY name LIMIT 8''',
        (f'{q}%', f'{q}%')
    ).fetchall()
    if len(rows) < 4:                        # broaden to contains
        rows = db.execute(
            '''SELECT product_id, name, category, price, image
               FROM   products
               WHERE  name LIKE ? OR category LIKE ?
               ORDER  BY name LIMIT 8''',
            (f'%{q}%', f'%{q}%')
        ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════════════════════════
#  PRICE DROP ALERTS  (wishlisted items now on flash sale)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/price-alerts')
@login_required
def price_alerts():
    user_id = session['user_id']
    db      = get_db()
    now     = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = db.execute(
        '''SELECT p.product_id, p.name, p.image, p.price AS original_price,
                  fs.sale_price, fs.discount_pct
           FROM   interactions i
           JOIN   products     p  ON i.product_id = p.product_id
           JOIN   flash_sales  fs ON fs.product_id = p.product_id
           WHERE  i.user_id = ? AND i.action = 'wishlist'
             AND  fs.is_active = 1 AND fs.end_time > ?
           GROUP  BY p.product_id''',
        (user_id, now)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════════════════════════
#  SOCIAL PROOF  (sold today + currently viewing)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/social-proof', methods=['POST'])
@login_required
def social_proof():
    data        = request.get_json(silent=True) or {}
    product_ids = data.get('product_ids', [])
    if not product_ids or not isinstance(product_ids, list):
        return jsonify({})
    product_ids = [int(p) for p in product_ids[:20]]   # cap at 20
    db  = get_db()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    yesterday = (datetime.now() - __import__('datetime').timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    sold_rows = db.execute(
        f'''SELECT product_id, COUNT(*) AS cnt
            FROM   interactions
            WHERE  product_id IN ({','.join('?'*len(product_ids))})
              AND  action = 'purchase' AND timestamp >= ?
            GROUP  BY product_id''',
        (*product_ids, yesterday)
    ).fetchall()
    db.close()
    sold_map = {r['product_id']: r['cnt'] for r in sold_rows}
    import random, hashlib
    result = {}
    for pid in product_ids:
        # Deterministic "viewing" count seeded by pid + current hour
        seed = int(hashlib.md5(f'{pid}{datetime.now().hour}'.encode()).hexdigest(), 16)
        viewing = (seed % 18) + 4        # 4-21
        result[pid] = {
            'sold_today': sold_map.get(pid, 0),
            'viewing':    viewing,
        }
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════════════
#  ORDER CANCEL / RETURN
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    user_id = session['user_id']
    db      = get_db()
    order   = db.execute(
        'SELECT * FROM orders WHERE order_id = ? AND user_id = ?',
        (order_id, user_id)
    ).fetchone()
    if not order:
        db.close(); return jsonify({'ok': False, 'error': 'Order not found.'}), 404
    if order['status'] not in ('placed', 'processing'):
        db.close(); return jsonify({'ok': False, 'error': 'Only placed or processing orders can be cancelled.'})
    # Allow cancel within 1 hour of placement
    created = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S')
    if (datetime.now() - created).total_seconds() > 3600:
        db.close(); return jsonify({'ok': False, 'error': 'Cancellation window (1 hour) has passed.'})
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute('UPDATE orders SET status=?, updated_at=? WHERE order_id=?',
               ('cancelled', now_str, order_id))
    # Restore stock for each item
    items = db.execute('SELECT product_id, quantity FROM order_items WHERE order_id=?',
                       (order_id,)).fetchall()
    for item in items:
        db.execute('UPDATE products SET stock = stock + ? WHERE product_id = ?',
                   (item['quantity'], item['product_id']))
    # Refund loyalty points if any were earned
    db.execute('UPDATE users SET loyalty_points = MAX(0, loyalty_points - ?) WHERE user_id = ?',
               (int(order['total'] // 10), user_id))
    db.commit(); db.close()
    return jsonify({'ok': True, 'message': 'Order cancelled successfully.'})


@app.route('/api/orders/<int:order_id>/return', methods=['POST'])
@login_required
def return_order(order_id):
    user_id = session['user_id']
    db      = get_db()
    order   = db.execute(
        'SELECT * FROM orders WHERE order_id = ? AND user_id = ?',
        (order_id, user_id)
    ).fetchone()
    if not order:
        db.close(); return jsonify({'ok': False, 'error': 'Order not found.'}), 404
    if order['status'] != 'delivered':
        db.close(); return jsonify({'ok': False, 'error': 'Only delivered orders can be returned.'})
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute('UPDATE orders SET status=?, updated_at=? WHERE order_id=?',
               ('return_requested', now_str, order_id))
    db.commit(); db.close()
    return jsonify({'ok': True, 'message': 'Return request submitted. We\'ll process it within 3–5 days.'})


# ══════════════════════════════════════════════════════════════════════════════
#  LOYALTY POINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/loyalty/balance')
@login_required
def loyalty_balance():
    user_id = session['user_id']
    db      = get_db()
    row     = db.execute('SELECT loyalty_points FROM users WHERE user_id = ?',
                         (user_id,)).fetchone()
    db.close()
    pts = row['loyalty_points'] if row and row['loyalty_points'] else 0
    return jsonify({'points': pts, 'rupee_value': pts // 10})  # 10pts = ₹1


@app.route('/api/loyalty/redeem', methods=['POST'])
@login_required
def redeem_loyalty():
    """Calculate discount from redeeming loyalty points (10 pts = ₹1). Does NOT deduct yet — deduction happens at place-order."""
    user_id = session['user_id']
    data    = request.get_json(silent=True) or {}
    try:
        redeem_pts = int(data.get('points', 0))
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': 'Invalid points value.'}), 400
    if redeem_pts <= 0:
        return jsonify({'ok': False, 'error': 'Points must be greater than 0.'})
    db  = get_db()
    row = db.execute('SELECT loyalty_points FROM users WHERE user_id=?', (user_id,)).fetchone()
    db.close()
    available = row['loyalty_points'] if row and row['loyalty_points'] else 0
    if redeem_pts > available:
        return jsonify({'ok': False, 'error': f'You only have {available} points.'})
    max_pts  = min(redeem_pts, available)
    discount = max_pts / 10          # 10 pts = ₹1
    return jsonify({'ok': True, 'points_used': max_pts, 'discount': round(discount, 2)})



if __name__ == '__main__':
    print('\n   E-commerce Recommendation Engine is starting...')
    print('   Open http://127.0.0.1:5000 in your browser\n')
    app.run(debug=True)