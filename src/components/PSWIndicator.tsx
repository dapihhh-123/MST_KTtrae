import type { PSWState } from "../psw/psw_detector";

export default function PSWIndicator({
  state,
  showHelp,
monitorOpen,
onToggleMonitor,
onOpenHelp,
}: {
  state: PSWState;
  showHelp: boolean;
  monitorOpen: boolean;
  onToggleMonitor: () => void;
  onOpenHelp: () => void;
}) {
  return (
    <div className="pswIndicator" aria-live="polite">
      <button
        className={`pswStatusButton ${monitorOpen ? "pswStatusButton--active" : ""}`}
        onClick={onToggleMonitor}
        type="button"
        aria-expanded={monitorOpen}
        aria-label="Toggle PSW monitor panel"
      >
        <span className={`pswStatus pswStatus--${state.toLowerCase()}`}>PSW: {state}</span>
      </button>

      {showHelp && (
        <button className="pswHelpBadge" onClick={onOpenHelp} type="button">
          ?
        </button>
      )}
    </div>
  );
}

          Need help?
        </button>
      )}
    </div>
  );
}
