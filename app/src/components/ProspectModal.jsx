import { useEffect, useRef, useState, useCallback } from 'react';
import { getTier, getInitials, getIntel, METRICS } from '../utils';

const CopyIcon = () => (
  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
    <rect x="3" y="3" width="6" height="6" rx="0.5" stroke="currentColor" strokeWidth="1" />
    <path d="M2 7H1.5C1.22 7 1 6.78 1 6.5V1.5C1 1.22 1.22 1 1.5 1H6.5C6.78 1 7 1.22 7 1.5V2" stroke="currentColor" strokeWidth="1" />
  </svg>
);

const ChevronLeft = () => (
  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
    <path d="M7 2L3 5L7 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const ChevronRight = () => (
  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
    <path d="M3 2L7 5L3 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function ProspectModal({ prospects, allProspects, activeIdx, onClose, onNav }) {
  const [copied, setCopied] = useState(false);
  const [animated, setAnimated] = useState(false);
  const cardRef = useRef(null);

  const p = prospects[activeIdx];
  const tier = getTier(p.score);
  const globalIdx = allProspects.indexOf(p);
  const intel = getIntel(p);

  // Animate bars on mount and index change
  useEffect(() => {
    setAnimated(false);
    setCopied(false);
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => setAnimated(true));
    });
    if (cardRef.current) cardRef.current.scrollTop = 0;
    return () => cancelAnimationFrame(raf);
  }, [activeIdx]);

  // Keyboard nav
  const handleKey = useCallback((e) => {
    if (e.key === 'Escape') onClose();
    if (e.key === 'ArrowRight' && activeIdx < prospects.length - 1) onNav(1);
    if (e.key === 'ArrowLeft' && activeIdx > 0) onNav(-1);
  }, [activeIdx, prospects.length, onClose, onNav]);

  useEffect(() => {
    document.addEventListener('keydown', handleKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [handleKey]);

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  const copyMsg = async () => {
    await navigator.clipboard.writeText(p.message);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="modal-overlay" onClick={handleOverlayClick}>
      <div className="modal-card" ref={cardRef}>
        {/* Sticky header with nav */}
        <div className="modal-close">
          <span className="modal-close-label">Prospect Detail</span>
          <div className="modal-close-nav">
            <button
              className="modal-nav-btn"
              onClick={() => onNav(-1)}
              disabled={activeIdx === 0}
            >
              <ChevronLeft />
            </button>
            <span className="modal-counter">
              {activeIdx + 1} / {prospects.length}
            </span>
            <button
              className="modal-nav-btn"
              onClick={() => onNav(1)}
              disabled={activeIdx === prospects.length - 1}
            >
              <ChevronRight />
            </button>
            <button className="close-x" onClick={onClose}>&#10005;</button>
          </div>
        </div>

        {/* Card body */}
        <div className="card-top">
          <div className="avatar-block">
            <div className="avatar">{getInitials(p.name)}</div>
            <div className="rank-info">
              <div className="rank-num">#<span>{globalIdx + 1}</span></div>
              {p.firm_match && <div className="firm-tag">{p.firm_match}</div>}
            </div>
          </div>
          <div className="score-block">
            <div className="score-number">
              {p.score}<span className="score-denom">/100</span>
            </div>
            <div className="score-lbl">Score</div>
          </div>
        </div>

        {/* Tier track */}
        <div className="tier-track">
          <div
            className="tier-fill"
            style={{
              width: animated ? `${p.score}%` : '0%',
              background: tier.color,
            }}
          />
        </div>
        <div className="tier-row">
          <span className={`tier-badge ${tier.cls}`}>{tier.label}</span>
          {p.email && <span className="email-tag">EMAIL ✓</span>}
        </div>

        {/* Name block */}
        <div className="name-block">
          <div className="prospect-name">{p.name}</div>
          <div className="prospect-title">{p.title}</div>
          <div className="prospect-meta">
            <span>{p.company}</span>
            <span className="meta-dot">&middot;</span>
            <span>{p.location}</span>
          </div>
        </div>

        <div className="divider" />

        {/* Signal Breakdown */}
        <div className="metrics">
          <div className="section-title">Signal Breakdown</div>
          {METRICS.map((m) => {
            const pct = Math.round((p.breakdown[m.field] / m.max) * 100);
            return (
              <div className="metric-row" key={m.field}>
                <div className="metric-key">{m.key}</div>
                <div className="metric-track">
                  <div
                    className="metric-fill"
                    style={{ width: animated ? `${pct}%` : '0%' }}
                  />
                </div>
                <div className="metric-val">{p.breakdown[m.field]}</div>
              </div>
            );
          })}
        </div>

        <div className="divider" />

        {/* Intel */}
        <div className="intel">
          <div className="section-title">Intel</div>
          <div className="intel-text">
            {intel.map((line, i) => (
              <span key={i}>{line}{i < intel.length - 1 && <br />}</span>
            ))}
          </div>
        </div>

        {p.message && (
          <>
            <div className="divider" />
            <div className="outreach">
              <div className="section-title">Outreach</div>
              <div className="outreach-box">
                <div className="outreach-text">{p.message}</div>
                <button
                  className={`copy-btn${copied ? ' copied' : ''}`}
                  onClick={copyMsg}
                >
                  {copied ? (
                    <>&#10003;&nbsp; Copied</>
                  ) : (
                    <><CopyIcon /> Copy Message</>
                  )}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
