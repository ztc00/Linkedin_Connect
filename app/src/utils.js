const MBB_FIRMS = ['mckinsey', 'bcg', 'bain', 'boston consulting'];

export function getTier(score) {
  if (score >= 50) return { label: 'HOT',     cls: 'tier-hot',  color: 'var(--red)',    tierCls: 'hot' };
  if (score >= 35) return { label: 'WARM UP', cls: 'tier-warm', color: 'var(--orange)', tierCls: 'warm' };
  return                   { label: 'COLD',    cls: 'tier-cold', color: 'var(--blue)',   tierCls: 'cold' };
}

export function getInitials(name) {
  return name.split(' ').filter(w => w.length > 0).map(w => w[0]).join('').substring(0, 2).toUpperCase();
}

export function getIntel(p) {
  const lines = [];
  const companyLower = (p.company || '').toLowerCase();
  const isMBB = MBB_FIRMS.some(f => companyLower.includes(f));
  const senior = /partner|director|vp|vice president|principal|managing/i.test(p.title);
  const mid = /manager|lead|head|engagement|recruiter/i.test(p.title);

  lines.push(isMBB ? 'MBB firm — high-value network contact' : `${p.company || 'Unknown company'} — industry contact`);
  lines.push(senior ? `${p.title} — decision-maker level` : mid ? `${p.title} — operational influence` : `${p.title} — peer-level entry point`);
  lines.push(p.email ? 'Direct email on file · outreach enabled' : 'No email · LinkedIn DM recommended');
  if (p.connected_on) {
    lines.push(`Connected ${p.connected_on}`);
  }
  return lines;
}

export const METRICS = [
  { key: 'Authority',  field: 'authority', max: 20 },
  { key: 'Scale',      field: 'scale',     max: 20 },
  { key: 'Proximity',  field: 'proximity', max: 20 },
  { key: 'Warmth',     field: 'warmth',    max: 20 },
  { key: 'Activity',   field: 'activity',  max: 20 },
];
