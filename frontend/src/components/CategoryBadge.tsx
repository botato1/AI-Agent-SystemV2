interface CategoryBadgeProps {
  name: string;
  color: string;
  className?: string;
}

export default function CategoryBadge({ name, color, className }: CategoryBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 truncate rounded-full border px-2 py-0.5 text-xs font-semibold ${
        className ?? ""
      }`}
      style={{ borderColor: `${color}4D`, backgroundColor: `${color}1A`, color }}
    >
      <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full" style={{ backgroundColor: color }} />
      <span className="truncate">{name}</span>
    </span>
  );
}
