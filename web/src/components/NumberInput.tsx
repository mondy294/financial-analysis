import { useEffect, useState, type CSSProperties } from "react";

type Props = {
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max?: number;
  step?: number | string;
  style?: CSSProperties;
  className?: string;
  title?: string;
  disabled?: boolean;
};

function clamp(n: number, min?: number, max?: number): number {
  if (min != null && n < min) return min;
  if (max != null && n > max) return max;
  return n;
}

/** 可直接键盘输入的数字框；编辑中允许空串，失焦再钳制到 [min,max]。 */
export function NumberInput({
  value,
  onChange,
  min,
  max,
  step = 1,
  style,
  className,
  title,
  disabled,
}: Props) {
  const [text, setText] = useState(String(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setText(String(value));
  }, [value, focused]);

  const commit = (raw: string) => {
    const n = Number(raw);
    const next = Number.isFinite(n) ? clamp(n, min, max) : clamp(value, min, max);
    onChange(next);
    setText(String(next));
  };

  return (
    <input
      type="number"
      inputMode="numeric"
      min={min}
      max={max}
      step={step}
      className={className}
      style={style}
      title={title}
      disabled={disabled}
      value={text}
      onFocus={() => setFocused(true)}
      onChange={(e) => {
        const raw = e.target.value;
        setText(raw);
        if (raw === "" || raw === "-" || raw === ".") return;
        const n = Number(raw);
        if (Number.isFinite(n)) onChange(clamp(n, min, max));
      }}
      onBlur={() => {
        setFocused(false);
        commit(text);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          (e.target as HTMLInputElement).blur();
        }
      }}
    />
  );
}
