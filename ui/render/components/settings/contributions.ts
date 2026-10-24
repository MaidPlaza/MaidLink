import { registerSettings, hydrateBackendSettings, setSettingValue } from "@/lib/settings";
import { refreshCapabilities } from "@/lib/capabilities";
import { refreshAddons } from "@/lib/addons";
import DrawingSettings from "./DrawingSettings";
import ModelSettings from "./ModelSettings";
import { REASONING_MODE_OPTIONS } from "./modelOptions";
import AddonsSettings from "./AddonsSettings";
import NsfwContent from "./NsfwContent";
import SoundSettings from "./SoundSettings";

registerSettings([
  { id: "appearance.timestamps", section: "Внешний вид", label: "Показывать время сообщений", type: "toggle", default: true, sectionOrder: 0, order: 0 },
  { id: "appearance.stats", section: "Внешний вид", label: "Показывать статистику генерации", type: "toggle", default: true, sectionOrder: 0, order: 1 },
]);

registerSettings([
  { id: "appearance.dark_theme", section: "Настройки темы", label: "Тёмная тема", type: "toggle", default: true, sectionOrder: 0.1, order: 0, lockDuringWave: true },
  { id: "appearance.standard_theme", section: "Настройки темы", label: "Стандартная тема", type: "toggle", default: false, sectionOrder: 0.1, order: 1, lockDuringWave: true },
]);
try {
  const OLD = "maidlink.setting.appearance.character_theme";
  const old = localStorage.getItem(OLD);
  if (old !== null) {
    if (JSON.parse(old) === false) setSettingValue("appearance.standard_theme", true);
    localStorage.removeItem(OLD);
  }
} catch {
}

registerSettings([
  { id: "chat.max_files", section: "Вложения", label: "Файлов в сообщении", type: "range", default: "1", min: 1, max: 3, step: 1, sectionOrder: 0.25 },
]);

registerSettings([
  { id: "sound.controls", section: "Звук", label: "Звук", type: "custom", component: SoundSettings, sectionOrder: 0.5 },
]);

registerSettings([
  { id: "image_gen.enabled", section: "Генерация", label: "Генерация картинок", type: "toggle", default: true, persist: "backend", sectionOrder: 1, order: 0 },
  ...(import.meta.env.DEV
    ? [{ id: "image_gen.keep_generated", section: "Генерация", label: "Хранить все снимки на диске", type: "toggle" as const, default: false, persist: "backend" as const }]
    : []),
  { id: "drawing.vision_critic_enabled", section: "Генерация", label: "Авто-проверка картинок", type: "toggle", default: true, persist: "backend", sectionOrder: 1, order: 2 },
  { id: "drawing.mood_portraits_enabled", section: "Генерация", label: "Портреты по настроению", type: "toggle", default: true, persist: "backend", sectionOrder: 1, order: 3 },
  { id: "session.proactive_enabled", section: "Сессия", label: "Может писать первой", type: "toggle", default: true, persist: "backend", sectionOrder: 2, order: 1 },
  { id: "session.idle_timeout_minutes", section: "Сессия", label: "Авто-закрытие сессии", type: "select", default: "15", persist: "backend", sectionOrder: 2, order: 0,
    options: [
      { value: "5", label: "5 мин" },
      { value: "10", label: "10 мин" },
      { value: "15", label: "15 мин" },
      { value: "30", label: "30 мин" },
      { value: "60", label: "60 мин" },
      { value: "0", label: "Никогда" },
    ] },
]);

registerSettings([
  { id: "drawing.style", section: "Рисование", label: "Модуль рисования", type: "custom", component: DrawingSettings, sectionOrder: 1 },
]);

registerSettings([
  { id: "llm.model", section: "Модель", home: "context-model", label: "Пресет и модель", type: "custom", component: ModelSettings, sectionOrder: 3, order: 0 },
  { id: "llm.reasoning_mode", section: "Модель", home: "context-model", label: "Режим рассуждений", type: "select", default: "fast", persist: "backend", sectionOrder: 3, order: 1, hidden: true,
    options: REASONING_MODE_OPTIONS },
]);
registerSettings([
  { id: "llm.vram_free_mib", section: "Видеопамять", home: "context-model", label: "Оставлять свободной после загрузки, МиБ", type: "range", default: "1024", min: 512, max: 4096, step: 256, persist: "backend", sectionOrder: 3.5 },
]);

registerSettings([
  { id: "addons.manager", section: "Аддоны", label: "Аддоны", type: "custom", component: AddonsSettings, sectionOrder: 7 },
]);
registerSettings([
  { id: "drawing.max_rating", section: "NSFW (18+)", label: "Откровенный контент", type: "custom", component: NsfwContent, persist: "backend", addon: "nsfw", sectionOrder: 8 },
]);

hydrateBackendSettings();

refreshCapabilities();

refreshAddons();
