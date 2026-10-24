export const REASONING_MODE_OPTIONS = [
  { value: "deep", label: "Глубокий (всегда думает)" },
  { value: "auto", label: "Авто (по сложности реплики)" },
  { value: "fast", label: "Быстрый (без размышлений)" },
];

export const REASONING_MODE_SHORT: Record<string, string> = {
  deep: "думает",
  auto: "авто",
  fast: "быстрый",
};
