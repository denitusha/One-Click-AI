import { useState, useCallback } from "react";

interface IntentInputProps {
  onSubmit: (intent: string) => void;
  disabled?: boolean;
}

const EXAMPLE_INTENT =
  "Build a high-performance electric vehicle prototype with carbon fiber body panels, titanium fasteners, ceramic brake calipers, aluminum engine block, and turbocharger assembly. Deliver to Stuttgart factory by Q2 2026.";

/** Input field for submitting procurement intent to kick off the cascade. */
export default function IntentInput({ onSubmit, disabled }: IntentInputProps) {
  const [value, setValue] = useState("");

  const handleSubmit = useCallback(() => {
    const text = value.trim() || EXAMPLE_INTENT;
    onSubmit(text);
  }, [value, onSubmit]);

  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        className="flex-1 rounded-lg border border-slate-600 bg-slate-800/80 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition-colors focus:border-sky-500 focus:ring-1 focus:ring-sky-500/30"
        placeholder={EXAMPLE_INTENT}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && !disabled && handleSubmit()}
        disabled={disabled}
      />
      <button
        onClick={handleSubmit}
        disabled={disabled}
        className="flex shrink-0 items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 active:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
        Run Cascade
      </button>
    </div>
  );
}
