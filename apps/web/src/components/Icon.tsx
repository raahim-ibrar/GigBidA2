const paths = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  inbox: "M4 4h16l2 12v4H2v-4L4 4z M2 16h6l2 3h4l2-3h6",
  folder: "M3 7V4h6l3 3h9v13H3V7z",
  pipeline: "M4 5h4v14H4z M10 5h4v9h-4z M16 5h4v12h-4z",
  message: "M21 4H3v13h5l4 4v-4h9V4z M7 8h10 M7 12h6",
  activity: "M2 12h4l3-8 6 16 3-8h4",
  chart: "M4 3v17h17 M8 15v-4 M13 15V7 M18 15V4",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3z",
  check: "m5 12 4 4L19 6",
  shield: "m12 2 8 3v6c0 5-8 11-8 11S4 16 4 11V5l8-3z m-4 9 3 3 5-6",
  plus: "M12 5v14 M5 12h14",
} as const;

export type IconName = keyof typeof paths;
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
