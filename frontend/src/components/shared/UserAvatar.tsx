import { cn } from "@/lib/utils";

const tones = {
  navy: "bg-navy text-white",
  gold: "bg-gold text-navy",
  emerald: "bg-emerald-600 text-white",
  plum: "bg-purple-700 text-white",
};

export function UserAvatar({
  initials,
  className,
  tone = "navy",
}: {
  initials: string;
  className?: string;
  tone?: keyof typeof tones | undefined;
}) {
  return (
    <span
      className={cn(
        "grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs font-semibold ring-2 ring-gold/40",
        tones[tone],
        className,
      )}
    >
      {initials}
    </span>
  );
}
