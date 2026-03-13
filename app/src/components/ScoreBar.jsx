export default function ScoreBar({ score }) {
  return (
    <div className="row-score">
      <div className="score-bar-wrap">
        <div className="score-bar-fill" style={{ width: `${score}%` }} />
      </div>
      <div className="score-num">{score}</div>
    </div>
  );
}
