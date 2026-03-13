import ProspectRow from './ProspectRow';

export default function ProspectList({ prospects, allProspects, onSelect }) {
  return (
    <>
      <div className="table-head">
        <div className="th">#</div>
        <div className="th">Name</div>
        <div className="th">Company</div>
        <div className="th">Tier</div>
        <div className="th right">Score</div>
      </div>
      <div className="prospect-list">
        {prospects.map((p, i) => {
          const globalIdx = allProspects.indexOf(p);
          return (
            <ProspectRow
              key={`${p.name}-${globalIdx}`}
              prospect={p}
              rank={globalIdx + 1}
              onClick={() => onSelect(i)}
            />
          );
        })}
      </div>
    </>
  );
}
