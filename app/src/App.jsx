import { useState, useEffect, useMemo } from 'react';
import ProspectList from './components/ProspectList';
import ProspectModal from './components/ProspectModal';
import AskNetwork from './components/AskNetwork';

const FILTERS = [
  { key: 'all',   label: 'All' },
  { key: 'hot',   label: '\uD83D\uDD34 Hot' },
  { key: 'warm',  label: '\uD83D\uDFE0 Warm Up' },
  { key: 'cold',  label: '\uD83D\uDD35 Cold' },
  { key: 'email', label: '✉️ Email Only' },
  { key: 'message', label: '💬 Has Message' },
];

export default function App() {
  const [prospects, setProspects] = useState([]);
  const [filter, setFilter] = useState('all');
  const [modalIdx, setModalIdx] = useState(null);
  const [tab, setTab] = useState('ranked'); // 'ranked' | 'ask'

  useEffect(() => {
    fetch('/prospects.json')
      .then((r) => r.json())
      .then((data) => setProspects(data.prospects || []))
      .catch((err) => console.error('Failed to load prospects:', err));
  }, []);

  const filtered = useMemo(() => {
    return prospects.filter((p) => {
      if (filter === 'hot')   return p.score >= 50;
      if (filter === 'warm')  return p.score >= 35 && p.score < 50;
      if (filter === 'cold')  return p.score < 35;
      if (filter === 'email') return !!p.email;
      if (filter === 'message') return !!p.message;
      return true;
    });
  }, [prospects, filter]);

  const stats = useMemo(() => ({
    total: prospects.length,
    hot:   prospects.filter((p) => p.score >= 50).length,
    warm:  prospects.filter((p) => p.score >= 35 && p.score < 50).length,
    cold:  prospects.filter((p) => p.score < 35).length,
    email: prospects.filter((p) => p.email).length,
  }), [prospects]);

  const handleNav = (dir) => {
    setModalIdx((prev) => {
      const next = prev + dir;
      if (next < 0 || next >= filtered.length) return prev;
      return next;
    });
  };

  if (!prospects.length) {
    return (
      <div className="homepage" style={{ textAlign: 'center', paddingTop: '120px' }}>
        <div className="page-label">Loading...</div>
      </div>
    );
  }

  return (
    <div className="homepage">
      <div className="page-header">
        <div className="page-label">Prospect Intelligence Report</div>
        <div className="page-title">Your Ranked Shortlist</div>
        <div className="page-sub">Click any prospect to open their outreach card</div>
      </div>

      <div className="tab-bar">
        <button
          className={`tab-btn${tab === 'ranked' ? ' active' : ''}`}
          onClick={() => setTab('ranked')}
        >
          Ranked List
        </button>
        <button
          className={`tab-btn${tab === 'ask' ? ' active' : ''}`}
          onClick={() => setTab('ask')}
        >
          Ask My Network
        </button>
      </div>

      {tab === 'ranked' && (
        <>
          <div className="stats-row">
            <div className="stat-pill">
              <span className="stat-pill-num">{stats.total}</span>
              <span className="stat-pill-label">Prospects</span>
            </div>
            <div className="stat-pill">
              <span className="stat-pill-num" style={{ color: 'var(--red)' }}>{stats.hot}</span>
              <span className="stat-pill-label">Hot &ge;50</span>
            </div>
            <div className="stat-pill">
              <span className="stat-pill-num" style={{ color: 'var(--orange)' }}>{stats.warm}</span>
              <span className="stat-pill-label">Warm Up</span>
            </div>
            <div className="stat-pill">
              <span className="stat-pill-num" style={{ color: 'var(--text-muted)' }}>{stats.cold}</span>
              <span className="stat-pill-label">Cold</span>
            </div>
            <div className="stat-pill">
              <span className="stat-pill-num" style={{ color: 'var(--green)' }}>{stats.email}</span>
              <span className="stat-pill-label">Email ✓</span>
            </div>
          </div>

          <div className="filter-bar">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                className={`filter-btn${filter === f.key ? ' active' : ''}`}
                onClick={() => setFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>

          <ProspectList
            prospects={filtered}
            allProspects={prospects}
            onSelect={(i) => setModalIdx(i)}
          />

          {modalIdx !== null && (
            <ProspectModal
              prospects={filtered}
              allProspects={prospects}
              activeIdx={modalIdx}
              onClose={() => setModalIdx(null)}
              onNav={handleNav}
            />
          )}
        </>
      )}

      {tab === 'ask' && <AskNetwork />}
    </div>
  );
}
