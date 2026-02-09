import type { PSWState } from "../psw/psw_detector";

export default function PSWIndicator({
  state,
  showHelp,
  onOpenHelp,
}: {
  state: PSWState;
  showHelp: boolean;
  onOpenHelp: () => void;
}) {
  return (
    <div className="pswIndicator" aria-live="polite">
      <span className={`pswStatus pswStatus--${state.toLowerCase()}`}>PSW: {state}</span>
      {showHelp && (
        <button className="pswHelpBadge" onClick={onOpenHelp} type="button">
          Need help?
        </button>
      )}
    </div>
  );
}
