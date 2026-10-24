import { authHeaders, wsProtocols } from "@/lib/auth";

const API_BASE = "http://localhost:8001";
const WS_BASE = "ws://localhost:8001";

export interface CharacterResponse {
  name: string;
  core_identity: string;
  mood: string;
  action: string;
  avatar_portrait: string;
  avatar_chat: string;
  accent_color: string;
  subtitle: string;
  short_description: string;
}

export interface Statement {
  id: string;
  section?: string;
  text: string;
  source: string;
}

export interface Thought {
  text: string;
  kind: string;
  relevance: number;
}

export interface GachaState {
  tickets: number;
  cap: number;
  unlocked: number;
  total: number;
  pool: number;
  last_daily?: string;
  spheres?: number;
  rare_in?: number;
  legendary_in?: number;
  per_day?: number;
  sphere_in?: number;
  sphere_every?: number;
  achievements?: { earned: number; total: number; tickets_earned: number };
  error?: string;
}
export interface GachaAchievementRow {
  id: string; title: string; hint: string; tickets: number; earned: boolean; at?: number | null;
}
export interface GachaAchievements {
  daily: { per_day: number; cap: number; sphere_every?: number };
  tutorial: GachaAchievementRow[];
  relations: Array<{ axis: string; label: string;
    levels: Array<GachaAchievementRow & { level: number; roman: string }> }>;
  hidden: GachaAchievementRow[];
  hidden_total: number;
  earned: number;
  total: number;
  tickets_earned: number;
  error?: string;
}
export interface GestureItem { id: string; label: string; title: string; zone: string; token: string }
export interface GesturesPayload { open: string; close: string; prefix: string; gestures: GestureItem[] }
export interface GachaItem {
  tag: string;
  label: string;
  category: string;
  category_label: string;
  rarity: "common" | "rare" | "legendary";
  rarity_label: string;
  nsfw?: boolean;
  color?: string;
  color_label?: string;
  colored_tag?: string;
  new_item?: boolean;
  colors_before?: string[];
  pattern?: string;
  pattern_label?: string;
  patterns_before?: string[];
  special?: string;
  hint?: string;
  spheres?: number;
  targets?: string[];
  pity?: string;
  bonus_sphere?: GachaItem;
}
export type GachaPullResult = GachaState & { ok?: boolean; item?: GachaItem };

export interface ModelPresetFit {
  model: string;
  model_label: string;
  available: boolean;
  vision: boolean;
  experimental: boolean;
  ctx: number;
  hist: number;
  expected_tps?: number | null;
  weights_mib: number;
  kv_mib: number;
  overhead_mib: number;
  need_mib: number;
  fit: "full" | "partial" | "poor" | "none";
  note: string;
  spill_mib: number;
  reasoning_mode?: string;
  downloadable?: boolean;
  download_size?: number;
  download?: { status: string; downloaded: number; total: number; error: string };
}
export interface ModelPreset extends Partial<ModelPresetFit> {
  key: string;
  label: string;
  summary: string;
  speed?: number;
  current?: ModelPresetFit;
}
export interface ModelPresetsResponse {
  current: string;
  machine: { gpu: string; gpu_available: boolean; vram_mib: number; vram_free_mib: number; ram_mib: number };
  presets: ModelPreset[];
}

export interface CardTraining {
  version: string;
  level: number;
  step: number;
  letter?: string;
  label: string;
  status: "ok" | "step_behind" | "level_behind" | "newer" | string;
  required?: string;
  required_label?: string;
  message?: string;
  history?: Array<{ from: string; to: string; at: string; trainer?: string;
                    app_version?: string; notes?: string }>;
}

export interface CardEntriesSection {
  unlocked: boolean;
  tier_required: string;
  label_required: string;
  items: Array<{
    id?: string; text: string; kind?: string;
    created_at?: number; relevance?: number; importance?: number;
  }>;
}

export interface GalleryItem {
  id: string;
  url: string;
  thumb_url: string;
  source?: string;
  intent?: string;
  rating?: string;
  added_at?: number;
  created_at?: number;
  width?: number;
  height?: number;
}

export interface IdentityResponse {
  self_statements: Statement[];
  relationships: Statement[];
  thoughts: Thought[];
  master_summary: string;
  last_session: string;
  last_mood: string;
  accumulated_importance: number;
  mood_state?: string;
  mood_intensity?: number;
  mood_effective?: [string, number];
  reaction_state?: string;
  mood_live?: string;
  reaction_intensity?: number;
  reaction_reason?: string;
  axes?: Record<string, number>;
  tier?: string;
  relationship_axes?: Record<string, { value: number; text: string }>;
  active_traits?: Array<{
    trait_id: string;
    text: string;
    kind: string;
    activated_at?: number;
    source_event?: string;
  }>;
  eligible_vulns_not_active?: Array<{ id: string; text: string }>;
  eligible_strengths_not_active?: Array<{ id: string; text: string }>;
}

export interface MemoryRecord {
  type: string;
  title: string;
  details: Record<string, unknown>;
  importance: number;
}

export interface MemoryResponse {
  records: MemoryRecord[];
  total: number;
}

export interface ChatStats {
  tokens?: number;
  tps?: number;
  ttft?: number;
  total?: number;
  gen?: number;
  prep_mood?: number;
  prep_recall?: number;
  ctx_tokens?: number;
  ctx_budget?: number;
  hist_tokens?: number;
  hist_budget?: number;
}

export type ModelLifecycleState = "UNLOADED" | "LOADING" | "LOADED" | "UNLOADING";

export type NotificationKind = "reminder" | "message";
export type NotificationOptions = { kind?: NotificationKind; icon?: string };

export type ServerMessage =
  | { type: "thinking"; text: string }
  | { type: "response"; text: string; id_mood?: number }
  | { type: "response_chunk"; text: string }
  | { type: "response_stream_reset" }
  | { type: "response_split"; text: string; id_mood?: number }
  | { type: "stats"; tokens?: number; tps?: number; ttft?: number; total?: number;
      gen?: number; prep_mood?: number; prep_recall?: number;
      ctx_tokens?: number; ctx_budget?: number;
      hist_tokens?: number; hist_budget?: number }
  | { type: "tool_call"; name: string; result: string }
  | { type: "detection"; matched: string[]; candidates: string[] }
  | { type: "system"; text: string }
  | { type: "image"; url: string; prompt?: string; gen_seconds?: number;
      media?: string }
  | { type: "video_embed"; video_id: string; url?: string }
  | { type: "app_status"; code?: string; text?: string }
  | { type: "session_ended"; reason: string; summary?: string; mood?: string }
  | { type: "model_state"; state: ModelLifecycleState }
  | { type: "notification"; title: string; body: string;
      kind?: NotificationKind; icon?: string }
  | {
      type: "reminder_card";
      record_id: string;
      kind: "one_shot" | "pre_event";
      title: string;
      event_at_iso?: string;
      fallback_text?: string;
    }
  | { type: "reminder_acknowledged"; record_id: string }
  | {
      type: "persona_status";
      state: string | null;
      reason: string;
    }
  | {
      type: "portrait_updated";
      character_id: string;
      url: string;
    }
  | { type: "gacha_changed" }
  | { type: "debug"; tag: string; data?: unknown }
  | { type: "done" }
  | { type: "error"; text: string };

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export interface CharacterListItem {
  id: string;
  baseline_id?: string;
  instance_id?: string | null;
  gender?: string;
  name: string;
  core_identity: string;
  subtitle: string;
  short_description: string;
  avatar_portrait: string;
  avatar_chat: string;
  accent_color: string;
  number?: number | null;
  generation?: string;
  first_meeting_at?: number | null;
  training?: CardTraining;
  active: boolean;
  is_protected?: boolean;
  is_unlocked?: boolean;
}

export interface WardrobeOutfit {
  id: string;
  name: string;
  rating: string;
  prepared: boolean;
  queued: boolean;
  preparing: boolean;
  done: number;
  total: number;
  current: boolean;
  protected: boolean;
}

export interface WardrobeCurrentOutfit { id: string; name: string; default: boolean }

export type WardrobeStyling = GachaState & {
  worn_count: number;
  categories: Array<{
    key: string; label: string; locked: number;
    items: Array<{
      tag: string; label: string; category: string; rarity: string; rarity_label: string;
      worn: boolean; worn_as: string; source: "default" | "gacha" | "legacy";
    }>;
  }>;
};

export const api = {
  character: () => fetchJson<CharacterResponse>("/api/character"),
  characters: () => fetchJson<{ characters: CharacterListItem[] }>("/api/characters"),
  selectCharacter: (id: string, secret?: string) =>
    postJson<{ status?: string; name?: string; error?: string;
               locked?: boolean; wrong_password?: boolean }>(
      `/api/characters/${id}/select`,
      secret ? { secret } : undefined,
    ),
  protectCharacter: (id: string, password: string) =>
    postJson<{ ok: boolean; error?: string; recovery_code?: string }>(
      `/api/characters/${id}/protect`, { password }),
  unprotectCharacter: (id: string, secret: string) =>
    postJson<{ ok: boolean; error?: string; wrong_password?: boolean }>(
      `/api/characters/${id}/unprotect`, { secret }),
  changeCharacterPassword: (id: string, oldSecret: string, newPassword: string) =>
    postJson<{ ok: boolean; error?: string; wrong_password?: boolean }>(
      `/api/characters/${id}/password`,
      { old_secret: oldSecret, new_password: newPassword }),
  importCharacter: (path: string) =>
    postJson<{ ok: boolean; error?: string; id?: string; baseline_id?: string; name?: string }>(
      "/api/characters/import",
      { path },
    ),
  openCharactersFolder: () =>
    postJson<{ ok: boolean; error?: string; path?: string }>("/api/characters/open-folder", {}),
  attachDocument: (path: string, quiet = false) =>
    postJson<{ ok: boolean; error?: string; name?: string; mode?: "full" | "rag";
               tokens?: number; pages?: number; chunks?: number }>(
      "/api/document",
      { path, quiet },
    ),
  identity: () => fetchJson<IdentityResponse>("/api/identity"),
  memory: () => fetchJson<MemoryResponse>("/api/memory/records"),
  prompt: () => fetchJson<{ prompt: string; tokens_approx: number }>("/api/prompt"),
  setRelationshipAxes: (axes: Record<string, number>) =>
    postJson<{ changed: Record<string, number>; tier: string; axes: Record<string, number> }>(
      "/api/debug/set_relationship_axes",
      axes,
    ),
  loops: () =>
    fetchJson<{
      open_loops: Array<{
        title: string;
        kind?: string;
        subject?: string;
        salience?: number;
        my_opinion?: string;
      }>;
    }>("/api/debug/loops"),
  profile: () =>
    fetchJson<{ summary: string; preferences: string[]; rules: string[] }>(
      "/api/debug/profile",
    ),
  drawingStyles: () =>
    fetchJson<{
      active: string;
      character_override: string | null;
      renderer_id: string;
      styles: Array<{
        id: string;
        name: string;
        description: string;
        renderer_id: string;
        tags: string[];
        source: string;
      }>;
    }>("/api/debug/drawing/styles"),
  deleteDrawingStyle: (styleId: string) =>
    postJson<{ ok?: boolean; removed?: string; error?: string }>(
      "/api/debug/drawing/delete-style", { style_id: styleId }),
  getSettings: () =>
    fetchJson<Record<string, boolean | number | string>>("/api/settings"),
  updateSettings: (patch: Record<string, boolean | number | string>) =>
    postJson<Record<string, boolean | number | string>>("/api/settings", patch),
  models: () =>
    fetchJson<{
      current: string;
      models: Array<{
        key: string;
        label: string;
        available: boolean;
        ctx_steps?: Array<{ ctx: number; hist: number }>;
        ctx_current?: number;
        ctx_default?: number;
        downloadable?: boolean;
        download_size?: number;
        download?: { status: string; downloaded: number; total: number; error: string };
      }>;
    }>("/api/models"),
  downloadModel: (choice: string) =>
    postJson<{ queued?: string[]; note?: string; error?: string }>(
      "/api/models/download",
      { choice },
    ),
  characterTheme: () =>
    fetchJson<{ theme: Record<string, string> | null }>("/api/character/theme"),
  characterUiStructure: (id: string, dark = false) =>
    fetchJson<{ structure: Record<string, unknown> | null }>(
      `/api/characters/${encodeURIComponent(id)}/ui/structure${dark ? "?dark=1" : ""}`,
    ),
  characterInfo: () =>
    fetchJson<{
      id?: string; name?: string; version?: string; lore?: string;
      relations?: Record<string, { lastProgress: number; newProgress: number; tier: string; label: string }>;
      ctx_fill?: number; error?: string;
      stats?: {
        days: number; first_meeting_at?: number | null; since?: number | null;
        sessions: number; messages: number; messages_user: number;
        messages_assistant: number; images: number;
        longest_messages?: number; longest_minutes?: number; talk_minutes?: number;
        streak_days?: number; best_streak_days?: number;
        proactive_sent?: number; proactive_answered?: number;
        moods_top?: Array<[string, number]>;
      };
      thoughts?: CardEntriesSection;
      diary?: CardEntriesSection;
      training?: CardTraining | null;
      character_tab?: {
        unlocked: boolean; tier_required: string; label_required: string;
        goal_rate?: number; goal_stage?: number | null; goal_stage_label?: string;
        goal_override?: boolean;
        axes: Array<{ key: string; label: string; left: string; right: string; value: number;
                      norm?: number; band_lo?: number; band_hi?: number;
                      goal?: number; goal_label?: string;
                      wish_down?: string; wish_up?: string;
                      hint_down?: string; hint_up?: string }>;
        traits: Array<{ id: string; text: string; description?: string; kind: string;
                        innate?: boolean; special?: boolean;
                        activated_at?: number; source_event?: string }>;
      };
    }>("/api/character/info"),
  characterInfoSeen: () => postJson<{ ok?: boolean }>("/api/character/info/seen", {}),
  setAxisGoal: (axis: string, dir: number) =>
    postJson<{ axis?: string; goal?: number; goal_label?: string; changed?: boolean;
               goals?: Record<string, number>; cleared?: string[]; error?: string }>(
      "/api/character/axis_goal", { axis, dir }),
  gallery: () =>
    fetchJson<{ items: GalleryItem[]; count: number; max: number; error?: string }>("/api/gallery"),
  galleryAdd: (url: string) =>
    postJson<{ ok?: boolean; item?: GalleryItem; error?: string }>("/api/gallery/add", { url }),
  galleryRemove: (id: string) =>
    postJson<{ ok?: boolean; error?: string }>("/api/gallery/remove", { id }),
  gacha: () => fetchJson<GachaState>("/api/gacha"),
  gachaPull: () => postJson<GachaPullResult>("/api/gacha/pull", {}),
  gachaSphere: (tag: string, color: string, pattern = "") =>
    postJson<{ ok?: boolean; tag?: string; color?: string; pattern?: string; spheres?: number;
               styling?: any; error?: string }>("/api/gacha/sphere", { tag, color, pattern }),
  gachaAchievements: () => fetchJson<GachaAchievements>("/api/gacha/achievements"),
  gestures: () => fetchJson<GesturesPayload>("/api/gestures"),
  switchModel: (choice: string) =>
    postJson<{ ok?: boolean; current?: string; label?: string; note?: string; error?: string }>(
      "/api/model",
      { choice },
    ),
  modelPresets: () => fetchJson<ModelPresetsResponse>("/api/models/presets"),
  applyModelPreset: (preset: string) =>
    postJson<{ ok?: boolean; current?: string; label?: string; model_label?: string; restart?: boolean; error?: string }>(
      "/api/model/preset",
      { preset },
    ),
  setModelCtx: (ctx: number, choice?: string) =>
    postJson<{ ok?: boolean; choice?: string; ctx?: number; hist?: number; note?: string; error?: string }>(
      "/api/model/ctx",
      choice ? { ctx, choice } : { ctx },
    ),
  polishGrammar: (text: string, messages?: Array<{ role: string; content: string }>) =>
    postJson<{ original: string; corrected: string; error?: string }>(
      "/api/debug/grammar",
      { text, messages },
    ),
  capabilities: () =>
    fetchJson<{ drawing: boolean; vision: boolean }>("/api/capabilities"),
  wardrobe: () =>
    fetchJson<{
      outfits: WardrobeOutfit[]; preparing: string | null;
      current_outfit: WardrobeCurrentOutfit | null; styling: WardrobeStyling | null;
    }>("/api/wardrobe"),
  prepareOutfit: (outfit_id: string) =>
    postJson<{ status?: string; error?: string; busy_with?: string } & Partial<WardrobeOutfit>>(
      "/api/wardrobe/prepare",
      { outfit_id },
    ),
  regenerateOutfit: (outfit_id: string) =>
    postJson<{ status?: string; error?: string; busy_with?: string; worn_reset?: boolean } & Partial<WardrobeOutfit>>(
      "/api/wardrobe/regenerate",
      { outfit_id },
    ),
  migrationStatus: () =>
    fetchJson<{ migrating: boolean; done: number; total: number }>("/api/migration"),
  setupStatus: () =>
    fetchJson<{
      needs_setup: boolean;
      agreement_ok?: boolean;
      terms_version?: string;
      gpu: { has_gpu: boolean; name: string; vram_gb: number };
      recommended_quant: string;
      choice?: string;
      presets?: Array<{
        key: string; label: string; hint: string; size: number; missing_size: number;
        vision: boolean; vram_gb: number; current: boolean;
      }>;
      models: Array<{
        key: string; role: string; quant: string;
        filename: string; size: number; present: boolean; has_url: boolean;
      }>;
      missing: string[];
      downloading: boolean;
      progress: Array<{
        key: string; status: string; downloaded: number; total: number; error: string;
      }>;
    }>("/api/setup/status"),
  charactersMock: (count: number) =>
    postJson<{ count: number }>("/api/characters/mock", { count }),
  setupMock: (on: boolean, vram?: number, termsOnly?: boolean) =>
    postJson<{ on: boolean; vram: number }>("/api/setup/mock", { on, vram, terms_only: !!termsOnly }),
  setupStart: (preset?: string) =>
    postJson<{ started?: boolean; queued?: string[]; choice?: string; error?: string }>(
      "/api/setup/start", preset ? { preset } : {}),
  setupAgreement: () =>
    postJson<{ ok?: boolean; version?: string; error?: string }>(
      "/api/setup/agreement", { adult: true }),
  imagegenStatus: () =>
    fetchJson<{
      installed: boolean;
      drawing_available: boolean;
      components: Array<{ key: string; title: string; license: string; agpl: boolean; present: boolean }>;
      missing: string[];
      agpl_components: string[];
      installing: boolean;
      progress: Array<{ key: string; status: string; downloaded: number; total: number; error: string }>;
    }>("/api/imagegen/status"),
  imagegenInstall: (agplConsent: boolean) =>
    postJson<{ started: boolean; error?: string; queued?: string[]; agpl_components?: string[] }>(
      "/api/imagegen/install",
      { agpl_consent: agplConsent },
    ),
  imagegenInstallNonAgpl: () =>
    postJson<{ started: boolean; queued?: string[] }>(
      "/api/imagegen/install",
      { non_agpl_only: true },
    ),
  imagegenCheckpoint: (path: string) =>
    postJson<{
      ok: boolean; error?: string; copying?: boolean;
      pipeline?: { id: string; name: string; workflow: string };
    }>(
      "/api/imagegen/checkpoint",
      { path },
    ),
  addons: () =>
    fetchJson<{ addons: Array<{ id: string; name: string; description: string; enabled: boolean; capabilities: string[] }> }>(
      "/api/addons",
    ),
  setAddon: (id: string, enabled: boolean) =>
    postJson<{ ok: boolean; addon: string; enabled: boolean }>(`/api/addons/${id}`, { enabled }),
  installAddon: (path: string) =>
    postJson<{ ok: boolean; error?: string; addon?: { id: string; name: string; description: string } }>(
      "/api/addons/install",
      { path },
    ),
};

export type ChatCallbacks = {
  onThinking?: (text: string) => void;
  onResponse?: (text: string, id_mood?: number) => void;
  onResponseChunk?: (text: string) => void;
  onStreamReset?: () => void;
  onResponseSplit?: (text: string, id_mood?: number) => void;
  onStats?: (stats: ChatStats) => void;
  onToolCall?: (name: string, result: string) => void;
  onDetection?: (matched: string[], candidates: string[]) => void;
  onSystem?: (text: string) => void;
  onImage?: (url: string, prompt?: string, gen_seconds?: number,
             media?: string) => void;
  onVideoEmbed?: (videoId: string, url?: string) => void;
  onAppStatus?: (text: string, code?: string) => void;
  onSessionEnded?: (reason: string, summary?: string, mood?: string) => void;
  onModelState?: (state: ModelLifecycleState) => void;
  onNotification?: (title: string, body: string, opts?: NotificationOptions) => void;
  onReminderCard?: (card: {
    record_id: string;
    kind: "one_shot" | "pre_event";
    title: string;
    event_at_iso?: string;
    fallback_text?: string;
  }) => void;
  onReminderAcknowledged?: (record_id: string) => void;
  onPersonaStatus?: (state: string | null, reason: string) => void;
  onPortraitUpdated?: (character_id: string, url: string) => void;
  onGachaChanged?: () => void;
  onDebug?: (tag: string, data?: unknown) => void;
  onDone?: () => void;
  onError?: (text: string) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
};

export class ChatSocket {
  private ws: WebSocket | null = null;
  private callbacks: ChatCallbacks;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(callbacks: ChatCallbacks) {
    this.callbacks = callbacks;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.ws = new WebSocket(`${WS_BASE}/api/chat`, wsProtocols());

    this.ws.onopen = () => {
      this.callbacks.onConnect?.();
    };

    this.ws.onmessage = (event) => {
      try {
        const msg: ServerMessage = JSON.parse(event.data);
        switch (msg.type) {
          case "thinking":
            this.callbacks.onThinking?.(msg.text);
            break;
          case "response":
            this.callbacks.onResponse?.(msg.text, msg.id_mood);
            break;
          case "response_chunk":
            this.callbacks.onResponseChunk?.(msg.text);
            break;
          case "response_stream_reset":
            this.callbacks.onStreamReset?.();
            break;
          case "response_split":
            this.callbacks.onResponseSplit?.(msg.text, msg.id_mood);
            break;
          case "stats":
            this.callbacks.onStats?.({ tokens: msg.tokens, tps: msg.tps, ttft: msg.ttft, total: msg.total,
                                       gen: msg.gen, prep_mood: msg.prep_mood,
                                       prep_recall: msg.prep_recall,
                                       ctx_tokens: msg.ctx_tokens, ctx_budget: msg.ctx_budget,
                                       hist_tokens: msg.hist_tokens, hist_budget: msg.hist_budget });
            break;
          case "tool_call":
            this.callbacks.onToolCall?.(msg.name, msg.result);
            break;
          case "detection":
            this.callbacks.onDetection?.(msg.matched, msg.candidates);
            break;
          case "system":
            this.callbacks.onSystem?.(msg.text);
            break;
          case "image":
            this.callbacks.onImage?.(msg.url, msg.prompt, msg.gen_seconds, msg.media);
            break;
          case "video_embed":
            this.callbacks.onVideoEmbed?.(msg.video_id, msg.url);
            break;
          case "app_status":
            this.callbacks.onAppStatus?.(msg.text || "", msg.code);
            break;
          case "session_ended":
            this.callbacks.onSessionEnded?.(msg.reason, msg.summary, msg.mood);
            break;
          case "model_state":
            this.callbacks.onModelState?.(msg.state);
            break;
          case "notification":
            this.callbacks.onNotification?.(msg.title, msg.body,
                                            { kind: msg.kind, icon: msg.icon });
            break;
          case "reminder_card":
            this.callbacks.onReminderCard?.({
              record_id: msg.record_id,
              kind: msg.kind,
              title: msg.title,
              event_at_iso: msg.event_at_iso,
              fallback_text: msg.fallback_text,
            });
            break;
          case "reminder_acknowledged":
            this.callbacks.onReminderAcknowledged?.(msg.record_id);
            break;
          case "persona_status":
            this.callbacks.onPersonaStatus?.(msg.state, msg.reason);
            break;
          case "portrait_updated":
            this.callbacks.onPortraitUpdated?.(msg.character_id, msg.url);
            break;
          case "gacha_changed":
            this.callbacks.onGachaChanged?.();
            break;
          case "debug":
            this.callbacks.onDebug?.(msg.tag, msg.data);
            break;
          case "done":
            this.callbacks.onDone?.();
            break;
          case "error":
            this.callbacks.onError?.(msg.text);
            break;
        }
      } catch {
      }
    };

    this.ws.onclose = () => {
      this.callbacks.onDisconnect?.();
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };

    this.ws.onerror = () => {
    };
  }

  send(text: string, image?: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      const msg: { type: string; text: string; image?: string } = { type: "message", text };
      if (image) msg.image = image;
      this.ws.send(JSON.stringify(msg));
    }
  }

  keystroke() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "keystroke" }));
    }
  }

  typing() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "typing" }));
    }
  }

  acknowledgeReminder(record_id: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: "acknowledge_reminder",
        record_id,
      }));
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  get connected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
