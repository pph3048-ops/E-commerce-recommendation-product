import { useState, useEffect, useCallback, useRef } from 'react';
import Navbar from './components/Navbar';
import Hero from './components/Hero';
import Section from './components/Section';
import SearchSection from './components/SearchSection';
import RateModal from './components/RateModal';
import ToastContainer from './components/ToastContainer';
import LandingPage from './components/LandingPage';
import ProductDetailModal from './components/ProductDetailModal';
import ProductCard from './components/ProductCard';
import CheckoutModal from './components/CheckoutModal';
import FlashSalesBanner from './components/FlashSalesBanner';
import OrderHistory from './components/OrderHistory';
import * as api from './api';

const EMPTY_SECTION = { data: [], loading: true };

export default function App() {
  const [user, setUser] = useState(null);
  const [authError, setAuthError] = useState(false);
  const [wishlistIds, setWishlistIds] = useState(new Set());
  const [purchasedIds, setPurchasedIds] = useState(new Set());

  const [searchActive, setSearchActive] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchRecs, setSearchRecs] = useState([]);
  const [searchFallback, setSearchFallback] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);

  const [recommendations, setRecommendations] = useState(EMPTY_SECTION);
  const [trending, setTrending] = useState(EMPTY_SECTION);
  const [topRated, setTopRated] = useState(EMPTY_SECTION);
  const [wishlist, setWishlist] = useState(EMPTY_SECTION);
  const [cart, setCart] = useState(EMPTY_SECTION);
  const [heroStats, setHeroStats] = useState({ purchased: 0, wishlisted: 0 });

  const [rateModal, setRateModal] = useState({ open: false, productId: null, productName: '' });
  const [toasts, setToasts] = useState([]);
  const toastIdRef = useRef(0);
  const [activeTab, setActiveTab] = useState('home');

  const [detailProductId, setDetailProductId]   = useState(null);
  const [recentlyViewed, setRecentlyViewed]      = useState(EMPTY_SECTION);
  const [becauseYouBought, setBecauseYouBought]  = useState({ data: [], seed: null, loading: true });

  // ── New feature states ──────────────────────────────────────────────────
  const [budgetInput,  setBudgetInput]  = useState('');
  const [budgetPicks,  setBudgetPicks]  = useState({ data: [], loading: false, searched: false });
  const [surprisePicks, setSurprisePicks] = useState({ data: [], loading: false });
  const [activeMood,   setActiveMood]   = useState(null);
  const [moodPicks,    setMoodPicks]    = useState({ data: [], loading: false });

  // ── Checkout / Orders / Flash-Sales state ─────────────────────────────
  const [showCheckout,   setShowCheckout]   = useState(false);
  const [orders,         setOrders]         = useState([]);
  const [ordersLoading,  setOrdersLoading]  = useState(false);
  const [flashSales,     setFlashSales]     = useState([]);
  const [flashDismissed, setFlashDismissed] = useState(false);

  // ── Social proof / loyalty / price alerts ────────────────────────────
  const [socialProof,    setSocialProof]    = useState({});
  const [loyaltyPoints,  setLoyaltyPoints]  = useState(0);
  const spTimerRef = useRef(null);

  const budgetResultRef  = useRef(null);
  const moodResultRef    = useRef(null);
  const surpriseResultRef = useRef(null);
  const [activePanel, setActivePanel] = useState(null); // 'mood' | 'budget' | 'surprise'

  const togglePanel = (name) => setActivePanel(p => p === name ? null : name);

  useEffect(() => {
    api.getMe()
      .then(setUser)
      .catch(() => setAuthError(true));
  }, []);

  useEffect(() => {
    if (!user) return;
    loadUserState(user.user_id);
    loadAllSections(user.user_id);
    loadPersonalSections(user.user_id);
    loadOrders();
    loadFlashSales();
    // Price drop alerts — show toast for each wishlisted item on sale
    api.getPriceAlerts().then(alerts => {
      if (Array.isArray(alerts)) {
        alerts.slice(0, 3).forEach((a, i) =>
          setTimeout(() => showToast(
            `💸 Price Drop! ${a.name.slice(0,30)}… now ₹${Number(a.sale_price).toLocaleString('en-IN')} (-${a.discount_pct}%)`,
            'success'
          ), i * 1200)
        );
      }
    }).catch(() => {});
    // Loyalty balance
    api.getLoyaltyBalance().then(d => setLoyaltyPoints(d.points || 0)).catch(() => {});
  }, [user]);

  const loadUserState = useCallback(async (uid) => {
    const [wl, pu] = await Promise.all([
      api.getWishlist(uid),
      api.getPurchases(uid),
    ]);
    setWishlistIds(new Set(wl.map(p => p.product_id)));
    setPurchasedIds(new Set(pu.map(p => p.product_id)));
    setHeroStats({ purchased: pu.length, wishlisted: wl.length });
  }, []);

  // Must be defined BEFORE loadAllSections (which lists it in its dependency array)
  const fetchSocialProof = useCallback((products) => {
    clearTimeout(spTimerRef.current);
    spTimerRef.current = setTimeout(async () => {
      const ids = (products || []).map(p => p.product_id).filter(Boolean).slice(0, 20);
      if (!ids.length) return;
      try {
        const data = await api.getSocialProof(ids);
        setSocialProof(prev => ({ ...prev, ...data }));
      } catch {}
    }, 400);
  }, []);

  const loadPersonalSections = useCallback(async (uid) => {
    setRecentlyViewed(EMPTY_SECTION);
    setBecauseYouBought({ data: [], seed: null, loading: true });
    const [rv, byb] = await Promise.all([
      api.getRecentlyViewed(uid),
      api.getBecauseYouBought(uid),
    ]);
    setRecentlyViewed({ data: rv, loading: false });
    setBecauseYouBought({ data: byb.recommendations || [], seed: byb.seed || null, loading: false });
  }, []);

  const handleBudgetSearch = useCallback(async () => {
    const val = parseFloat(budgetInput);
    if (!val || val <= 0) return;
    setBudgetPicks({ data: [], loading: true, searched: true });
    try {
      const data = await api.getBudgetPicks(val);
      setBudgetPicks({ data, loading: false, searched: true });
      setTimeout(() => budgetResultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
    } catch {
      setBudgetPicks({ data: [], loading: false, searched: true });
    }
  }, [budgetInput]);

  const handleSurprise = useCallback(async () => {
    if (!user) return;
    setSurprisePicks({ data: [], loading: true });
    try {
      const data = await api.getSurprise(user.user_id);
      setSurprisePicks({ data, loading: false });
      setTimeout(() => surpriseResultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
    } catch {
      setSurprisePicks({ data: [], loading: false });
    }
  }, [user]);

  const handleMood = useCallback(async (mood) => {
    setActiveMood(mood);
    setMoodPicks({ data: [], loading: true });
    try {
      const data = await api.getMoodPicks(mood);
      setMoodPicks({ data, loading: false });
      setTimeout(() => moodResultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
    } catch {
      setMoodPicks({ data: [], loading: false });
    }
  }, []);

  const loadAllSections = useCallback(async (uid) => {
    setRecommendations(EMPTY_SECTION);
    setTrending(EMPTY_SECTION);
    setTopRated(EMPTY_SECTION);
    setWishlist(EMPTY_SECTION);
    setCart(EMPTY_SECTION);
    const [recs, trend, top, wl, cartData] = await Promise.all([
      api.getRecommendations(uid),
      api.getTrending(),
      api.getTopRated(),
      api.getWishlist(uid),
      api.getCart(uid),
    ]);
    setRecommendations({ data: recs, loading: false });
    setTrending({ data: trend, loading: false });
    setTopRated({ data: top, loading: false });
    setWishlist({ data: wl, loading: false });
    setCart({ data: cartData, loading: false });
    fetchSocialProof([...recs, ...trend, ...top]);
  }, [fetchSocialProof]);

  const loadOrders = useCallback(async () => {
    setOrdersLoading(true);
    try {
      const data = await api.getOrders();
      setOrders(Array.isArray(data) ? data : []);
    } catch { setOrders([]); } finally { setOrdersLoading(false); }
  }, []);

  const loadFlashSales = useCallback(async () => {
    try {
      const data = await api.getFlashSales();
      setFlashSales(Array.isArray(data) ? data : []);
    } catch { setFlashSales([]); }
  }, []);

  const showToast = useCallback((message, type = '') => {
    const id = ++toastIdRef.current;
    setToasts(t => [...t, { id, message, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 3000);
  }, []);

  const performSearch = useCallback(async (query) => {
    setSearchActive(true);
    setSearchQuery(query);
    setSearchLoading(true);
    setSearchResults([]);
    setSearchRecs([]);
    // Clear stale data from any previous search immediately
    setRecommendations(EMPTY_SECTION);
    setTrending(EMPTY_SECTION);
    setTopRated(EMPTY_SECTION);
    try {
      const data = await api.searchProducts(query);
      setSearchResults(data.results || []);
      setSearchRecs(data.recommendations || []);
      setSearchFallback(data.fallback || false);
      setRecommendations({ data: data.recommendations || [], loading: false });
      setTrending({ data: data.trending || [], loading: false });
      setTopRated({ data: data.top_rated || [], loading: false });
      fetchSocialProof([...(data.results || []), ...(data.recommendations || [])]);
    } finally {
      setSearchLoading(false);
    }
  }, [user]);

  const clearSearch = useCallback(() => {
    setSearchActive(false);
    setSearchQuery('');
    setSearchResults([]);
    setSearchRecs([]);
    if (user) loadAllSections(user.user_id);
  }, [user, loadAllSections]);

  const handleWishlist = useCallback(async (pid) => {
    if (!user) return;
    const isWishlisted = wishlistIds.has(pid);
    setWishlistIds(prev => {
      const next = new Set(prev);
      isWishlisted ? next.delete(pid) : next.add(pid);
      return next;
    });
    // Also optimistically update the wishlist section immediately
    if (isWishlisted) {
      setWishlist(prev => ({ ...prev, data: prev.data.filter(p => p.product_id !== pid) }));
    }
    if (!isWishlisted) {
      await api.recordInteraction(pid, 'wishlist');
      showToast('Added to wishlist!');
    } else {
      await api.removeWishlist(user.user_id, pid);
      showToast('Removed from wishlist');
    }
    const [wl, pu] = await Promise.all([
      api.getWishlist(user.user_id),
      api.getPurchases(user.user_id),
    ]);
    setWishlist({ data: wl, loading: false });
    setHeroStats({ purchased: pu.length, wishlisted: wl.length });
    api.getRecommendations(user.user_id).then(d =>
      setRecommendations({ data: d, loading: false })
    );
  }, [user, wishlistIds, showToast]);

  const handleBuy = useCallback(async (pid) => {
    if (!user || purchasedIds.has(pid)) return;
    setPurchasedIds(prev => new Set([...prev, pid]));
    // Record click first so it appears in Recently Viewed
    await api.recordInteraction(pid, 'click');
    await api.recordInteraction(pid, 'purchase');
    showToast('Added to cart!', 'cart');
    // Only refresh cart and stats — don't reload all sections (avoids tab navigation side-effects)
    const [pu, wl] = await Promise.all([
      api.getPurchases(user.user_id),
      api.getWishlist(user.user_id),
    ]);
    setPurchasedIds(new Set(pu.map(p => p.product_id)));
    setCart({ data: pu, loading: false });
    setHeroStats({ purchased: pu.length, wishlisted: wl.length });
    // Refresh recently viewed so the bought item appears there
    api.getRecentlyViewed(user.user_id).then(rv => setRecentlyViewed({ data: rv, loading: false }));
  }, [user, purchasedIds, showToast]);

  const handleRemoveCart = useCallback(async (pid) => {
    if (!user) return;
    setPurchasedIds(prev => { const n = new Set(prev); n.delete(pid); return n; });
    setCart(prev => ({ ...prev, data: prev.data.filter(p => p.product_id !== pid) }));
    await api.removeCart(user.user_id, pid);
    showToast('Removed from cart');
    const [pu, wl] = await Promise.all([
      api.getPurchases(user.user_id),
      api.getWishlist(user.user_id),
    ]);
    setPurchasedIds(new Set(pu.map(p => p.product_id)));
    setCart({ data: pu, loading: false });
    setHeroStats({ purchased: pu.length, wishlisted: wl.length });
  }, [user, showToast]);

  const handleOpenRate = useCallback((pid, name) => {
    setRateModal({ open: true, productId: pid, productName: name });
  }, []);

  const handleSubmitRating = useCallback(async (stars) => {
    const pid = rateModal.productId;
    setRateModal({ open: false, productId: null, productName: '' });
    await api.recordInteraction(pid, 'rate', stars);
    showToast('Rated ' + stars + ' stars — thanks!');
    if (user) {
      if (searchActive && searchQuery) {
        // Refresh search-based sections so the rated product surfaces in Top Rated
        const data = await api.searchProducts(searchQuery);
        setRecommendations({ data: data.recommendations || [], loading: false });
        setTrending({ data: data.trending || [], loading: false });
        setTopRated({ data: data.top_rated || [], loading: false });
      } else {
        const [top, recs] = await Promise.all([
          api.getTopRated(),
          api.getRecommendations(user.user_id),
        ]);
        setTopRated({ data: top, loading: false });
        setRecommendations({ data: recs, loading: false });
      }
    }
  }, [user, rateModal.productId, showToast, searchActive, searchQuery]);

  const handleClick = useCallback(async (pid) => {
    await api.recordInteraction(pid, 'click');
    setDetailProductId(pid);
    if (user) api.getRecentlyViewed(user.user_id).then(rv => setRecentlyViewed({ data: rv, loading: false }));
  }, [user]);

  if (authError) {
    return <LandingPage onLogin={(user) => { setUser(user); setAuthError(false); }} />;
  }

  if (!user) {
    return (
      <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center' }}>
        <div className="loading-skeleton" style={{ width: 240, height: 36, borderRadius: 8 }} />
      </div>
    );
  }

  const handleLogout = () => {
    setUser(null);
    setAuthError(true);
  };

  const cardProps = {
    wishlistIds,
    purchasedIds,
    onWishlist: handleWishlist,
    onBuy: handleBuy,
    onRemoveCart: handleRemoveCart,
    onRate: handleOpenRate,
    onClick: handleClick,
    socialProof,
  };

  return (
    <>
      <Navbar
        userName={user.user_name}
        onSearch={performSearch}
        onLogout={handleLogout}
        activeTab={activeTab}
        onTabChange={(tab) => setActiveTab(tab)}
        wishlistCount={wishlist.data.length}
        cartCount={cart.data.length}
        ordersCount={orders.length}
      />

      {!searchActive && activeTab === 'home' && <Hero userName={user.user_name} stats={heroStats} loyaltyPoints={loyaltyPoints} />}
      {searchActive && activeTab === 'home' && <Hero userName={user.user_name} stats={heroStats} loyaltyPoints={loyaltyPoints} />}

      <main className="main-content">
        {searchActive ? (
          <>
            {/* Search results only on home tab */}
            {activeTab === 'home' && (
              <SearchSection
                query={searchQuery}
                results={searchResults}
                fallback={searchFallback}
                loading={searchLoading}
                cardProps={cardProps}
                onClear={clearSearch}
              />
            )}
            {activeTab === 'trending' && (
              <Section
                icon="🔥"
                title="Trending Now"
                subtitle={`Trending products matching "${searchQuery}"`}
                badge={trending.data.length}
                products={trending.data}
                loading={trending.loading}
                emptyMsg={`No trending products found for "${searchQuery}".`}
                cardProps={cardProps}
              />
            )}
            {activeTab === 'toprated' && (
              <Section
                icon="⭐"
                title="Top Rated"
                subtitle={`Top rated products matching "${searchQuery}"`}
                badge={topRated.data.length}
                products={topRated.data}
                loading={topRated.loading}
                emptyMsg={`No rated products found for "${searchQuery}".`}
                cardProps={cardProps}
              />
            )}
            {activeTab === 'wishlist' && (
              <Section
                icon="❤️"
                title="My Wishlist"
                subtitle="Products you have saved for later"
                badge={wishlist.data.length}
                products={wishlist.data}
                loading={wishlist.loading}
                emptyMsg="Your wishlist is empty. Add products you love!"
                cardProps={cardProps}
              />
            )}
            {activeTab === 'cart' && (
              <>
                <Section
                  icon="🛒"
                  title="My Cart"
                  subtitle="Products you've added to cart"
                  badge={cart.data.length}
                  products={cart.data}
                  loading={cart.loading}
                  emptyMsg="Your cart is empty. Add products to get started!"
                  cardProps={cardProps}
                />
                {cart.data.length > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'center', padding: '0.5rem 0 2.5rem' }}>
                    <button
                      onClick={() => setShowCheckout(true)}
                      style={{
                        padding: '0.9rem 2.8rem', fontSize: '1.05rem', fontWeight: 800,
                        borderRadius: 14, border: 'none', cursor: 'pointer', color: '#fff',
                        background: 'linear-gradient(135deg, #6c63ff, #9c5aff)',
                        boxShadow: '0 6px 20px rgba(108,99,255,0.4)',
                      }}
                    >
                      🛒 Proceed to Checkout&nbsp;&nbsp;({cart.data.length} item{cart.data.length !== 1 ? 's' : ''})
                    </button>
                  </div>
                )}
              </>
            )}
            {activeTab === 'orders' && (
              <OrderHistory orders={orders} loading={ordersLoading} onRefresh={loadOrders} showToast={showToast} />
            )}
          </>
        ) : activeTab === 'home' ? (
          <div className="home-layout">

            {/* ══════════ LEFT SIDEBAR — SmartHub Accordion ══════════ */}
            <aside className="smarthub-accordion-wrap" style={{ position: 'sticky', top: 72, marginBottom: 0 }}>
              <div className="smarthub-accordion-header">
                <span>🧠 SmartHub</span>
                <span className="smarthub-accordion-sub">Exclusive features</span>
              </div>

              {/* ── Mood panel ── */}
              <div className="sh-panel">
                <button className={`sh-panel-heading${activePanel === 'mood' ? ' open' : ''}`} onClick={() => togglePanel('mood')}>
                  <span>🎭 Mood Shopping</span>
                  <span className="sh-chevron">{activePanel === 'mood' ? '▲' : '▼'}</span>
                </button>
                {activePanel === 'mood' && (
                  <div className="sh-panel-body">
                    <p className="sh-panel-desc">Pick your vibe</p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      {[
                        { key: 'gifting',    label: '🎁 Gifting' },
                        { key: 'self-treat', label: '🛍️ Self-Treat' },
                        { key: 'urgent',     label: '⚡ Urgent' },
                        { key: 'exploring',  label: '🔭 Explore' },
                      ].map(m => (
                        <button key={m.key} onClick={() => handleMood(m.key)} className={`smarthub-mood-btn${activeMood === m.key ? ' active' : ''}`}>
                          {m.label}
                        </button>
                      ))}
                    </div>
                    {activeMood && (
                      <button onClick={() => { setActiveMood(null); setMoodPicks({ data: [], loading: false }); }} className="smarthub-clear-btn">✕ Clear</button>
                    )}
                  </div>
                )}
              </div>

              {/* ── Budget panel ── */}
              <div className="sh-panel">
                <button className={`sh-panel-heading${activePanel === 'budget' ? ' open' : ''}`} onClick={() => togglePanel('budget')}>
                  <span>💰 Budget Picks</span>
                  <span className="sh-chevron">{activePanel === 'budget' ? '▲' : '▼'}</span>
                </button>
                {activePanel === 'budget' && (
                  <div className="sh-panel-body">
                    <p className="sh-panel-desc">Best-rated within your limit</p>
                    <div style={{ position: 'relative', marginBottom: '0.5rem' }}>
                      <span style={{ position: 'absolute', left: '0.6rem', top: '50%', transform: 'translateY(-50%)', color: '#9ca3af', fontSize: '0.82rem', pointerEvents: 'none' }}>₹</span>
                      <input type="number" min="1" placeholder="Max price" value={budgetInput}
                        onChange={e => setBudgetInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleBudgetSearch()}
                        className="smarthub-input" />
                    </div>
                    <button onClick={handleBudgetSearch} className="smarthub-action-btn">Find Deals</button>
                    {budgetPicks.searched && (
                      <button onClick={() => { setBudgetInput(''); setBudgetPicks({ data: [], loading: false, searched: false }); }} className="smarthub-clear-btn">✕ Clear</button>
                    )}
                  </div>
                )}
              </div>

              {/* ── Surprise panel ── */}
              <div className="sh-panel">
                <button className={`sh-panel-heading${activePanel === 'surprise' ? ' open' : ''}`} onClick={() => togglePanel('surprise')}>
                  <span>🎲 Surprise Me</span>
                  <span className="sh-chevron">{activePanel === 'surprise' ? '▲' : '▼'}</span>
                </button>
                {activePanel === 'surprise' && (
                  <div className="sh-panel-body">
                    <p className="sh-panel-desc">Discover new categories</p>
                    <button onClick={handleSurprise} disabled={surprisePicks.loading} className="smarthub-surprise-btn">
                      {surprisePicks.loading ? '🔄 Finding...' : '🎲 Surprise Me!'}
                    </button>
                    {surprisePicks.data.length > 0 && (
                      <button onClick={() => setSurprisePicks({ data: [], loading: false })} className="smarthub-clear-btn">✕ Clear</button>
                    )}
                  </div>
                )}
              </div>

              {/* ── Recommended For You ── */}
              <div className="sh-panel" style={{ borderTop: '2px solid #ede9fe' }}>
                <div className="smarthub-accordion-header" style={{ fontSize: '0.85rem', padding: '0.65rem 1rem', background: 'linear-gradient(135deg,#f5f3ff,#ede9fe)', color: '#4f46e5' }}>
                  ✨ Recommended For You
                </div>
                {recommendations.loading ? (
                  <div style={{ padding: '0.75rem 1rem' }}>
                    {[1,2,3].map(i => <div key={i} className="loading-skeleton" style={{ height: 60, borderRadius: 8, marginBottom: '0.5rem' }} />)}
                  </div>
                ) : recommendations.data.length === 0 ? (
                  <p style={{ padding: '0.75rem 1rem', fontSize: '0.78rem', color: '#9ca3af', margin: 0 }}>Start browsing to get picks!</p>
                ) : (
                  <div style={{ maxHeight: 420, overflowY: 'auto', padding: '0.5rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {recommendations.data.slice(0, 8).map(p => (
                      <div key={p.product_id} onClick={() => { api.recordInteraction(p.product_id, 'click'); setDetailProductId(p.product_id); }}
                        style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', cursor: 'pointer', padding: '0.4rem', borderRadius: 10, transition: 'background .15s' }}
                        onMouseEnter={e => e.currentTarget.style.background='#f5f3ff'}
                        onMouseLeave={e => e.currentTarget.style.background='transparent'}>
                        {p.image && <img src={p.image} alt={p.name} style={{ width: 44, height: 44, objectFit: 'contain', borderRadius: 8, background: '#f8f9fa', flexShrink: 0 }} onError={e => e.currentTarget.style.display='none'} />}
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#111827', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</div>
                          <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', marginTop: '0.15rem' }}>
                            {p.price > 0 && <span style={{ fontSize: '0.72rem', color: '#6c63ff', fontWeight: 700 }}>₹{Number(p.price).toLocaleString('en-IN')}</span>}
                            {p.match_pct && <span style={{ fontSize: '0.68rem', background: p.match_pct >= 90 ? '#dcfce7' : '#f5f3ff', color: p.match_pct >= 90 ? '#16a34a' : '#6c63ff', borderRadius: 99, padding: '0 0.35rem', fontWeight: 700 }}>{p.match_pct}%</span>}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </aside>

            {/* ══════════ RIGHT MAIN ══════════ */}
            <div className="home-main">

              {/* Flash Sales Banner */}
              {flashSales.length > 0 && !flashDismissed && (
                <FlashSalesBanner
                  products={flashSales}
                  wishlistIds={wishlistIds}
                  purchasedIds={purchasedIds}
                  onBuy={handleBuy}
                  onWishlist={handleWishlist}
                  onDismiss={() => setFlashDismissed(true)}
                />
              )}

              {/* Budget results */}
              {(budgetPicks.searched || budgetPicks.loading) && (
                <section ref={budgetResultRef} className="smarthub-result-section" style={{ background: '#fff', borderRadius: 16, padding: '1.5rem', marginBottom: '1.5rem', boxShadow: '0 2px 12px rgba(0,0,0,0.07)', border: '1px solid #f3f4f6' }}>
                  <h3 style={{ margin: '0 0 0.25rem', fontSize: '1rem', fontWeight: 800 }}>💰 Best Picks Under ₹{parseFloat(budgetInput || 0).toLocaleString('en-IN')}</h3>
                  <p style={{ margin: '0 0 1rem', fontSize: '0.8rem', color: '#6b7280' }}>Top-rated products within your budget</p>
                  {budgetPicks.loading ? <p style={{ color: '#6c63ff', fontWeight: 600, fontSize: '0.88rem' }}>Finding best deals...</p>
                  : budgetPicks.data.length === 0 ? <p style={{ color: '#9ca3af', fontSize: '0.88rem' }}>No products found. Try a higher budget.</p>
                  : <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '1rem' }}>
                      {budgetPicks.data.map(p => (
                        <ProductCard key={p.product_id} product={p} {...cardProps} />
                      ))}
                    </div>}
                </section>
              )}

              {/* Mood results */}
              {activeMood && (
                <section ref={moodResultRef} className="smarthub-result-section" style={{ background: '#fff', borderRadius: 16, padding: '1.5rem', marginBottom: '1.5rem', boxShadow: '0 2px 12px rgba(0,0,0,0.07)', border: '1px solid #f3f4f6' }}>
                  <h3 style={{ margin: '0 0 0.25rem', fontSize: '1rem', fontWeight: 800 }}>
                    {activeMood === 'gifting' ? '🎁 Gifting' : activeMood === 'self-treat' ? '🛍️ Self-Treat' : activeMood === 'urgent' ? '⚡ Urgent Need' : '🔭 Exploring'} Picks
                  </h3>
                  <p style={{ margin: '0 0 1rem', fontSize: '0.8rem', color: '#6b7280' }}>Curated for your "{activeMood}" mood</p>
                  {moodPicks.loading ? <p style={{ color: '#6c63ff', fontWeight: 600, fontSize: '0.88rem' }}>Loading picks...</p>
                  : moodPicks.data.length === 0 ? <p style={{ color: '#9ca3af', fontSize: '0.88rem' }}>No picks found for this mood.</p>
                  : <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '1rem' }}>
                      {moodPicks.data.map(p => (
                        <ProductCard key={p.product_id} product={p} {...cardProps} />
                      ))}
                    </div>}
                </section>
              )}

              {/* Surprise results */}
              {surprisePicks.data.length > 0 && (
                <section ref={surpriseResultRef} className="smarthub-result-section" style={{ background: '#fff', borderRadius: 16, padding: '1.5rem', marginBottom: '1.5rem', boxShadow: '0 2px 12px rgba(0,0,0,0.07)', border: '1px solid #f3f4f6' }}>
                  <h3 style={{ margin: '0 0 0.25rem', fontSize: '1rem', fontWeight: 800 }}>🎲 Surprise Picks</h3>
                  <p style={{ margin: '0 0 1rem', fontSize: '0.8rem', color: '#6b7280' }}>Top products from categories you've never browsed</p>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '1rem' }}>
                    {surprisePicks.data.map(p => (
                      <ProductCard key={p.product_id} product={p} {...cardProps} />
                    ))}
                  </div>
                </section>
              )}

              {becauseYouBought.data.length > 0 && (
                <Section
                  icon="💡"
                  title={`Because you bought: ${becauseYouBought.seed?.name || 'your last item'}`}
                  subtitle="Customers who bought this also bought…"
                  products={becauseYouBought.data}
                  loading={becauseYouBought.loading}
                  emptyMsg=""
                  cardProps={cardProps}
                />
              )}
            </div>
          </div>
        ) : activeTab === 'trending' ? (
          <Section
            icon="🔥"
            title="Trending Now"
            subtitle="Most popular in the last 7 days"
            badge={trending.data.length}
            products={trending.data}
            loading={trending.loading}
            emptyMsg="No trending data yet. Check back soon!"
            cardProps={cardProps}
            showFilters
          />
        ) : activeTab === 'toprated' ? (
          <Section
            icon="⭐"
            title="Top Rated"
            subtitle="Highest average star ratings"
            badge={topRated.data.length}
            products={topRated.data}
            loading={topRated.loading}
            emptyMsg="No ratings yet. Rate a product to see the leaderboard!"
            cardProps={cardProps}
            showFilters
          />
        ) : activeTab === 'wishlist' ? (
          <Section
            icon="❤️"
            title="My Wishlist"
            subtitle="Products you have saved for later"
            badge={wishlist.data.length}
            products={wishlist.data}
            loading={wishlist.loading}
            emptyMsg="Your wishlist is empty. Add products you love!"
            cardProps={cardProps}
          />
        ) : activeTab === 'cart' ? (
          <>
            <Section
              icon="🛒"
              title="My Cart"
              subtitle="Products you've added to cart"
              badge={cart.data.length}
              products={cart.data}
              loading={cart.loading}
              emptyMsg="Your cart is empty. Add products to get started!"
              cardProps={cardProps}
            />
            {cart.data.length > 0 && (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '0.5rem 0 2.5rem' }}>
                <button
                  onClick={() => setShowCheckout(true)}
                  style={{
                    padding: '0.9rem 2.8rem', fontSize: '1.05rem', fontWeight: 800,
                    borderRadius: 14, border: 'none', cursor: 'pointer', color: '#fff',
                    background: 'linear-gradient(135deg, #6c63ff, #9c5aff)',
                    boxShadow: '0 6px 20px rgba(108,99,255,0.4)',
                    transition: 'transform .15s, box-shadow .15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 10px 28px rgba(108,99,255,0.5)'; }}
                  onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)';    e.currentTarget.style.boxShadow = '0 6px 20px rgba(108,99,255,0.4)'; }}
                >
                  🛒 Proceed to Checkout  ({cart.data.length} item{cart.data.length !== 1 ? 's' : ''})
                </button>
              </div>
            )}
          </>
        ) : activeTab === 'orders' ? (
          <OrderHistory orders={orders} loading={ordersLoading} onRefresh={loadOrders} showToast={showToast} />
        ) : null}
      </main>

      {/* ══ Amazon-style Recently Viewed strip ══ */}
      {recentlyViewed.data.length > 0 && (
        <div className="rv-strip">
          <div className="rv-strip-label">🕐 Recently Viewed</div>
          <div className="rv-strip-scroll">
            {recentlyViewed.data.map(p => (
              <div key={p.product_id} className="rv-strip-item" onClick={() => { api.recordInteraction(p.product_id, 'click'); setDetailProductId(p.product_id); }}>
                {p.image
                  ? <img src={p.image} alt={p.name} className="rv-strip-img" onError={e => { e.currentTarget.style.display='none'; e.currentTarget.nextSibling.style.display='flex'; }} />
                  : null}
                <div className="rv-strip-img rv-strip-img--fallback" style={{ display: p.image ? 'none' : 'flex' }}>🛍️</div>
                <div className="rv-strip-name">{p.name}</div>
                {p.price > 0 && <div className="rv-strip-price">₹{Number(p.price).toLocaleString('en-IN')}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      <footer className="footer">
        <p>
          E-commerce Recommendation Engine &nbsp;|&nbsp;
          Built with Flask + React &nbsp;|&nbsp;
          Logged in as <strong>{user.user_name}</strong>
        </p>
      </footer>

      <RateModal
        open={rateModal.open}
        productName={rateModal.productName}
        onSubmit={handleSubmitRating}
        onClose={() => setRateModal({ open: false, productId: null, productName: '' })}
      />

      {detailProductId && (
        <ProductDetailModal
          productId={detailProductId}
          wishlistIds={wishlistIds}
          purchasedIds={purchasedIds}
          onWishlist={handleWishlist}
          onBuy={handleBuy}
          onRemoveCart={handleRemoveCart}
          onRate={handleOpenRate}
          onClose={() => setDetailProductId(null)}
        />
      )}

      {showCheckout && (
        <CheckoutModal
          cartItems={cart.data}
          onClose={() => setShowCheckout(false)}
          loyaltyPoints={loyaltyPoints}
          onOrderPlaced={async () => {
            setShowCheckout(false);
            setActiveTab('orders');
            const [pu, wl] = await Promise.all([
              api.getPurchases(user.user_id),
              api.getWishlist(user.user_id),
            ]);
            setPurchasedIds(new Set(pu.map(p => p.product_id)));
            setCart({ data: pu, loading: false });
            setHeroStats({ purchased: pu.length, wishlisted: wl.length });
            loadOrders();
            api.getLoyaltyBalance().then(d => setLoyaltyPoints(d.points || 0)).catch(() => {});
          }}
          onViewOrders={() => { setShowCheckout(false); setActiveTab('orders'); }}
          showToast={showToast}
        />
      )}

      <ToastContainer toasts={toasts} />
    </>
  );
}
