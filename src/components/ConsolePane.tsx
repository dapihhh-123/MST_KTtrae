
import type { ConsoleEntry } from "../types";

export default function ConsolePane(props: {
  entries: ConsoleEntry[];
  onClear: () => void;
}) {
  return (
    <div className="consolePane">
      <div className="consoleHeader">
        <div>PROGRAM OUTPUT</div>
        <button className="smallBtn" onClick={props.onClear}>Clear</button>
      </div>
      <div className="consoleList">
        {props.entries.length === 0 ? (
          <div className="consoleLine info">To run code, click “RUN”.</div>
        ) : (
          props.entries.map((e) => (
            <div key={e.id} className={`consoleLine ${e.kind}`}>
              {e.text}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
