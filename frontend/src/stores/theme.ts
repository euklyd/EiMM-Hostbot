import { defineStore } from "pinia";
import { ref } from "vue";

export type Theme = "discord" | "light" | "sheets";

export interface ThemeMeta {
  id: Theme;
  label: string;
  /** Color shown in the sidebar swatch picker */
  swatch: string;
}

export const THEMES: ThemeMeta[] = [
  { id: "discord", label: "Discord", swatch: "#2b2d31" },
  { id: "light",   label: "Light",   swatch: "#e8eaed" },
  { id: "sheets",  label: "Sheets",  swatch: "#188038" },
];

export const useThemeStore = defineStore("theme", () => {
  const saved = (localStorage.getItem("theme") as Theme | null) ?? "discord";
  const theme = ref<Theme>(saved);

  function setTheme(t: Theme) {
    theme.value = t;
    localStorage.setItem("theme", t);
    document.documentElement.setAttribute("data-theme", t);
  }

  return { theme, setTheme };
});
