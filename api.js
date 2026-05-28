export async function getMe() {
  const res = await fetch('/api/me');
  if (!res.ok) throw new Error('Not authenticated');
  return res.json();
}

export async function logout() {
  await fetch('/api/logout', { method: 'POST' });
}

export async function getWishlist(userId) {
  const res = await fetch('/wishlist/' + userId);
  return res.json();
}

export async function removeWishlist(userId, productId) {
  await fetch(`/wishlist/${userId}/${productId}`, { method: 'DELETE' });
}

export async function removeCart(userId, productId) {
  await fetch(`/cart/${userId}/${productId}`, { method: 'DELETE' });
}

export async function getPurchases(userId) {
  const res = await fetch('/user_purchases/' + userId);
  return res.json();
}

export async function getCart(userId) {
  const res = await fetch('/user_purchases/' + userId);
  return res.json();
}

export async function getRecommendations(userId) {
  const res = await fetch('/recommend/' + userId);
  return res.json();
}

export async function getTrending() {
  const res = await fetch('/trending');
  return res.json();
}

export async function getTopRated() {
  const res = await fetch('/top-rated');
  return res.json();
}

export async function searchProducts(query) {
  const res = await fetch('/search?q=' + encodeURIComponent(query));
  return res.json();
}

export async function getProduct(productId) {
  const res = await fetch('/product/' + productId);
  return res.json();
}

export async function getRecentlyViewed(userId) {
  const res = await fetch('/recently-viewed/' + userId);
  return res.json();
}

export async function getBecauseYouBought(userId) {
  const res = await fetch('/because-you-bought/' + userId);
  return res.json();
}

export async function recordInteraction(productId, action, rating) {
  const body = { product_id: productId, action };
  if (rating !== undefined) body.rating = rating;
  await fetch('/interact', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function getBudgetPicks(maxPrice) {
  const res = await fetch('/budget-picks?max=' + encodeURIComponent(maxPrice));
  return res.json();
}

export async function getSurprise(userId) {
  const res = await fetch('/surprise/' + userId);
  return res.json();
}

export async function getMoodPicks(mood) {
  const res = await fetch('/mood-picks?mood=' + encodeURIComponent(mood));
  return res.json();
}

// ── Coupon & Checkout ──────────────────────────────────────────────────────

export async function validateCoupon(code, total) {
  const res = await fetch('/api/coupon/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, total }),
  });
  return res.json();
}

export async function placeOrder(data) {
  const res = await fetch('/api/checkout/place-order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function getOrders() {
  const res = await fetch('/api/orders');
  return res.json();
}

export async function getOrder(orderId) {
  const res = await fetch('/api/orders/' + orderId);
  return res.json();
}

export async function getFlashSales() {
  const res = await fetch('/api/flash-sales');
  return res.json();
}

export async function getSearchSuggestions(q) {
  const res = await fetch('/api/search/suggestions?q=' + encodeURIComponent(q));
  return res.json();
}

export async function getPriceAlerts() {
  const res = await fetch('/api/price-alerts');
  return res.json();
}

export async function getSocialProof(productIds) {
  const res = await fetch('/api/social-proof', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_ids: productIds }),
  });
  return res.json();
}

export async function cancelOrder(orderId) {
  const res = await fetch(`/api/orders/${orderId}/cancel`, { method: 'POST' });
  return res.json();
}

export async function returnOrder(orderId) {
  const res = await fetch(`/api/orders/${orderId}/return`, { method: 'POST' });
  return res.json();
}

export async function getLoyaltyBalance() {
  const res = await fetch('/api/loyalty/balance');
  return res.json();
}

export async function redeemLoyalty(points) {
  const res = await fetch('/api/loyalty/redeem', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ points }),
  });
  return res.json();
}

export async function createRazorpayOrder(amount) {
  const res = await fetch('/api/payment/create-order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount }),
  });
  return res.json();
}

export async function verifyRazorpayPayment(data) {
  const res = await fetch('/api/payment/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}
