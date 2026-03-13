import { useState, useRef } from 'react';

export default function AskNetwork() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(null);
  const inputRef = useRef(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const res = await fetch('http://localhost:8000/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      setResults(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const copyMessage = (msg, idx) => {
    navigator.clipboard.writeText(msg);
    setCopied(idx);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="ask-network">
      <div className="ask-header">
        <div className="ask-label">Ask My Network</div>
        <div className="ask-sub">
          Describe who you're looking for — Claude will search your connections, rank them, and write outreach messages.
        </div>
      </div>

      <form className="ask-form" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          className="ask-input"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. &quot;who works in consulting in New York&quot;"
          disabled={loading}
        />
        <button className="ask-btn" type="submit" disabled={loading || !query.trim()}>
          {loading ? (
            <span className="ask-spinner" />
          ) : (
            'Search'
          )}
        </button>
      </form>

      {loading && (
        <div className="ask-loading">
          <div className="ask-loading-bar">
            <div className="ask-loading-fill" />
          </div>
          <div className="ask-loading-text">
            Filtering connections and ranking with Claude...
          </div>
        </div>
      )}

      {error && (
        <div className="ask-error">
          Something went wrong: {error}
        </div>
      )}

      {results && results.results && (
        <div className="ask-results">
          <div className="ask-results-meta">
            {results.results.length} results from {results.total_connections} connections
            <span className="ask-results-dot">·</span>
            {results.prefiltered} pre-filtered
          </div>

          {results.results.length === 0 && (
            <div className="ask-empty">
              No relevant connections found for this query. Try different keywords.
            </div>
          )}

          {results.results.map((r, i) => (
            <div className="ask-card" key={i}>
              <div className="ask-card-header">
                <div className="ask-card-rank">#{i + 1}</div>
                <div className="ask-card-info">
                  <a
                    className="ask-card-name"
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {r.name}
                  </a>
                  <div className="ask-card-role">
                    {r.position}{r.company ? ` · ${r.company}` : ''}
                  </div>
                </div>
                <div className="ask-card-score">
                  <span className="ask-card-score-num">{r.relevance_score}</span>
                  <span className="ask-card-score-label">/100</span>
                </div>
              </div>

              <div className="ask-card-reason">{r.reason}</div>

              {r.message && (
                <div className="ask-card-message">
                  <div className="ask-card-message-label">Outreach Message</div>
                  <div className="ask-card-message-text">{r.message}</div>
                  <button
                    className={`ask-copy-btn${copied === i ? ' copied' : ''}`}
                    onClick={() => copyMessage(r.message, i)}
                  >
                    {copied === i ? 'Copied' : 'Copy Message'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
