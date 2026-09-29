"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Turn = { role: "user" | "assistant"; content: string };

/**
 * Scoped assistant for one screening. The backend pins the system prompt to
 * that result's grade and advice, so this stays an explanation aid — it
 * won't answer unrelated medical questions or soften a referral.
 */
export function Chat({ screeningId }: { screeningId: number }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question || busy) return;

    const history = turns;
    setTurns([...history, { role: "user", content: question }]);
    setInput("");
    setBusy(true);

    try {
      const { answer } = await api.chat(screeningId, question, history);
      setTurns((t) => [...t, { role: "assistant", content: answer }]);
    } catch (err) {
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content: err instanceof ApiError ? err.message : "The assistant is unavailable.",
        },
      ]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => {
        logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
      });
    }
  }

  return (
    <div>
      {turns.length > 0 && (
        <div ref={logRef} className="mb-3 max-h-64 space-y-2.5 overflow-y-auto pr-1">
          {turns.map((t, i) => (
            <div
              key={i}
              className={`max-w-[88%] rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                t.role === "user"
                  ? "ml-auto bg-cyan/15 text-ink"
                  : "mr-auto border border-line-soft bg-abyss/70 text-ink-dim"
              }`}
            >
              {t.content}
            </div>
          ))}
          {busy && (
            <div className="mr-auto flex gap-1.5 rounded-xl border border-line-soft bg-abyss/70 px-3.5 py-3">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan"
                  style={{ animationDelay: `${i * 120}ms` }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <form onSubmit={ask} className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this result…"
          className="flex-1 rounded-xl border border-line bg-abyss/80 px-3.5 py-2.5 text-sm outline-none transition-all placeholder:text-ink-faint focus:border-cyan focus:shadow-[0_0_0_3px_#22d3ee22]"
        />
        <Button type="submit" variant="primary" disabled={busy || !input.trim()}>
          Ask
        </Button>
      </form>
      <p className="mt-2 text-[11px] text-ink-faint">
        Answers cover this screening only — not general medical advice.
      </p>
    </div>
  );
}
