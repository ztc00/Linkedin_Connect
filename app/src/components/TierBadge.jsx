import { getTier } from '../utils';

export default function TierBadge({ score }) {
  const tier = getTier(score);
  return <span className={`tier-badge ${tier.cls}`}>{tier.label}</span>;
}
