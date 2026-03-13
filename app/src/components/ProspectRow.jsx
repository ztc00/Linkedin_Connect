import { getTier } from '../utils';
import TierBadge from './TierBadge';
import ScoreBar from './ScoreBar';

export default function ProspectRow({ prospect, rank, onClick }) {
  const tier = getTier(prospect.score);

  return (
    <div
      className={`prospect-row ${tier.tierCls}`}
      onClick={onClick}
      title="Click to open outreach card"
    >
      <div className="row-rank">{rank}</div>
      <div className="row-info">
        <div className="row-name">
          {prospect.name}
          {prospect.email && <span className="email-dot" title="Email on file" />}
        </div>
        <div className="row-sub">{prospect.title}</div>
      </div>
      <div className="row-company">
        <div className="row-company-name">{prospect.company}</div>
        <div className="row-location">{prospect.location}</div>
      </div>
      <div className="row-tier">
        <TierBadge score={prospect.score} />
      </div>
      <ScoreBar score={prospect.score} />
      <span className="row-arrow">&rsaquo;</span>
    </div>
  );
}
