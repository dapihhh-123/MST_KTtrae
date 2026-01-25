import { useState, useRef, useEffect } from "react";
import type { Breakout } from "../types";

type BreakoutPosition = { top: number; visible: boolean };

export default function BreakoutOverlay(props: {
  breakouts: Breakout[];
  positions: Record<string, BreakoutPosition>;
  activeId: string | null;
  onClose: (id: string) => void;
  onFocus: (id: string) => void;
  onSend: (id: string, msg: any) => void;
  onPositionChange: (id: string, x: number, y: number) => void;
}) {
  return (
    <div className="breakoutLayer">
      {props.breakouts.map((b) => {
        if (!b.open) return null;
        const pos = props.positions[b.id];
        const baseTop = pos?.visible ? pos.top : 20;
        const isActive = props.activeId === b.id;

        return (
          <BreakoutCard
            key={b.id}
            breakout={b}
            isActive={isActive}
            baseTop={baseTop}
            onClose={() => props.onClose(b.id)}
            onFocus={() => props.onFocus(b.id)}
            onSend={(msg) => props.onSend(b.id, msg)}
            onPositionChange={(x, y) => props.onPositionChange(b.id, x, y)}
          />
        );
      })}
    </div>
  );
}

function BreakoutCard(props: {
  breakout: Breakout;
  isActive: boolean;
  baseTop: number;
  onClose: () => void;
  onFocus: () => void;
  onSend: (msg: any) => void;
  onPositionChange: (x: number, y: number) => void;
}) {
  const [input, setInput] = useState("");
  
  // Draggable state (Scheme A)
  // Use props.breakout.position as initial state if available
  const [pos, setPos] = useState(props.breakout.position || { x: 0, y: 0 });
  
  // Sync state with props if props change (e.g. restoration)
  useEffect(() => {
    if (props.breakout.position) {
      setPos(props.breakout.position);
    }
  }, [props.breakout.position]);

  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });

  // Initial position: Fixed right-bottom (safest as per docs)
  // We use transform for dragging to avoid layout thrashing
  // Base position is handled by CSS (right: 16px, bottom: 16px) or inline styles.
  // Let's use inline styles for the base position to be sure.

  const handleMouseDown = (e: React.MouseEvent) => {
    // Only allow drag from header
    if ((e.target as HTMLElement).closest('.controls')) return; // don't drag when clicking close
    
    setIsDragging(true);
    dragStart.current = { x: e.clientX - pos.x, y: e.clientY - pos.y };
    
    const moveHandler = (ev: MouseEvent) => {
      setPos({
        x: ev.clientX - dragStart.current.x,
        y: ev.clientY - dragStart.current.y
      });
    };
    
    const upHandler = (ev: MouseEvent) => {
      setIsDragging(false);
      window.removeEventListener('mousemove', moveHandler);
      window.removeEventListener('mouseup', upHandler);
      
      // Persist the final position
      const finalX = ev.clientX - dragStart.current.x;
      const finalY = ev.clientY - dragStart.current.y;
      props.onPositionChange(finalX, finalY);
    };
    
    window.addEventListener('mousemove', moveHandler);
    window.addEventListener('mouseup', upHandler);
  };

  const handleSend = () => {
    if (!input.trim()) return;
    props.onSend({
      id: `msg_${Date.now()}`,
      role: "user",
      content: input,
      createdAt: Date.now()
    });
    setInput("");
  };

  return (
    <div
      className={`breakoutPanel ${props.isActive ? "active" : ""}`}
      style={{
        position: 'absolute',
        right: '20px',
        top: `${Math.max(12, props.baseTop)}px`,
        transform: `translate(${pos.x}px, ${pos.y}px)`,
        zIndex: props.isActive ? 50 : 40,
        opacity: 1, // Ensure visibility
        cursor: isDragging ? 'grabbing' : 'auto'
      }}
      onClick={props.onFocus}
    >
      <div 
        className="breakoutHeader"
        onMouseDown={handleMouseDown}
        style={{ cursor: 'grab' }}
      >
        <div className="title">{props.breakout.title} <span style={{opacity:0.5, fontWeight:'normal'}}>#{props.breakout.anchorStartLine}</span></div>
        <div className="controls">
          <button 
             className="btn small ghost"
             style={{padding: '2px 6px', minHeight: 'auto'}} 
             onClick={(e) => { e.stopPropagation(); props.onClose(); }}
          >
            ×
          </button>
        </div>
      </div>
      <div className="breakoutBody">
        {props.breakout.messages.map((msg) => (
          <div key={msg.id} className={`msg ${msg.role}`} style={{padding: '4px 0'}}>
            <div className="bubble" style={{
                background: msg.role === 'assistant' ? 'rgba(255,255,255,0.05)' : 'rgba(124,92,255,0.2)',
                padding: '6px 10px',
                borderRadius: '8px',
                fontSize: '13px'
            }}>{msg.content}</div>
          </div>
        ))}
      </div>
      <div className="breakoutComposer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this code..."
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              handleSend();
            }
          }}
        />
      </div>
    </div>
  );
}
