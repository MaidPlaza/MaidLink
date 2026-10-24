import clickWav from "../assets/sounds/click.wav";
import msgNeutralWav from "../assets/sounds/msg_neutral.wav";
import msgWarmWav from "../assets/sounds/msg_warm.wav";
import msgPleasedWav from "../assets/sounds/msg_pleased.wav";
import msgInspiredWav from "../assets/sounds/msg_inspired.wav";
import msgPlayfulWav from "../assets/sounds/msg_playful.wav";
import msgSadWav from "../assets/sounds/msg_sad.wav";
import msgHurtWav from "../assets/sounds/msg_hurt.wav";
import msgAnxiousWav from "../assets/sounds/msg_anxious.wav";
import msgEmbarrassedWav from "../assets/sounds/msg_embarrassed.wav";
import msgIrritatedWav from "../assets/sounds/msg_irritated.wav";
import msgSurprisedWav from "../assets/sounds/msg_surprised.wav";
import msgStartledWav from "../assets/sounds/msg_startled.wav";
import msgLaughWav from "../assets/sounds/msg_laugh.wav";
import notifyWav from "../assets/sounds/notify.wav";

export type SoundName =
  | "click"
  | "msg_neutral"
  | "msg_warm"
  | "msg_pleased"
  | "msg_inspired"
  | "msg_playful"
  | "msg_sad"
  | "msg_hurt"
  | "msg_anxious"
  | "msg_embarrassed"
  | "msg_irritated"
  | "msg_surprised"
  | "msg_startled"
  | "msg_laugh"
  | "notify";

const FILES: Record<SoundName, string> = {
  click: clickWav,
  msg_neutral: msgNeutralWav,
  msg_warm: msgWarmWav,
  msg_pleased: msgPleasedWav,
  msg_inspired: msgInspiredWav,
  msg_playful: msgPlayfulWav,
  msg_sad: msgSadWav,
  msg_hurt: msgHurtWav,
  msg_anxious: msgAnxiousWav,
  msg_embarrassed: msgEmbarrassedWav,
  msg_irritated: msgIrritatedWav,
  msg_surprised: msgSurprisedWav,
  msg_startled: msgStartledWav,
  msg_laugh: msgLaughWav,
  notify: notifyWav,
};

export const MOOD_SOUND: Record<string, SoundName> = {
  "ровное": "msg_neutral",
  "довольное": "msg_pleased",
  "растроганное": "msg_warm",
  "воодушевлённое": "msg_inspired",
  "игривое": "msg_playful",
  "грустное": "msg_sad",
  "обиженное": "msg_hurt",
  "встревоженное": "msg_anxious",
  "смущённое": "msg_embarrassed",
  "раздражённое": "msg_irritated",
  "удивление": "msg_surprised",
  "испуг": "msg_startled",
  "смех": "msg_laugh",
};

const VOLUME_KEY = "maidlink.sound.volume";
const ENABLED_KEY = "maidlink.sound.enabled";

const CLICKABLE = 'button, [role="button"], .character-card, .chip-activation-region';

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

class SoundManager {
  private pool = new Map<SoundName, HTMLAudioElement>();
  private _volume: number;
  private _enabled: boolean;

  constructor() {
    const v = Number(localStorage.getItem(VOLUME_KEY));
    this._volume = Number.isFinite(v) && v > 0 ? clamp01(v) : 1.0;
    this._enabled = localStorage.getItem(ENABLED_KEY) !== "0";
  }

  get volume(): number {
    return this._volume;
  }

  setVolume(v: number): void {
    this._volume = clamp01(v);
    localStorage.setItem(VOLUME_KEY, String(this._volume));
  }

  get enabled(): boolean {
    return this._enabled;
  }

  setEnabled(on: boolean): void {
    this._enabled = on;
    localStorage.setItem(ENABLED_KEY, on ? "1" : "0");
  }

  preloadAll(): void {
    (Object.keys(FILES) as SoundName[]).forEach((n) => this.el(n));
  }

  private el(name: SoundName): HTMLAudioElement {
    let a = this.pool.get(name);
    if (!a) {
      a = new Audio(FILES[name]);
      a.preload = "auto";
      this.pool.set(name, a);
    }
    return a;
  }

  play(name: SoundName, opts: { humanize?: number; gain?: number } = {}): void {
    if (!this._enabled || this._volume <= 0) return;
    let a = this.el(name);
    if (!a.paused && !a.ended) a = a.cloneNode(true) as HTMLAudioElement;
    const { humanize = 0, gain = 1 } = opts;
    (a as HTMLAudioElement & { preservesPitch: boolean }).preservesPitch = false;
    a.playbackRate = humanize ? 1 + (Math.random() * 2 - 1) * humanize : 1;
    const jitter = humanize ? 1 + (Math.random() * 2 - 1) * 0.1 : 1;
    a.volume = clamp01(this._volume * gain * jitter);
    a.currentTime = 0;
    void a.play().catch(() => {});
  }

  playMood(mood?: string | null): void {
    this.play(MOOD_SOUND[mood ?? ""] ?? "msg_neutral", { humanize: 0.03 });
  }

  installGlobal(): () => void {
    const warm = () => this.preloadAll();
    const onClick = (e: MouseEvent) => {
      const t = e.target as Element | null;
      if (t?.closest?.(CLICKABLE)) this.play("click", { humanize: 0.02 });
    };
    document.addEventListener("pointerdown", warm, { capture: true, once: true });
    document.addEventListener("click", onClick, { capture: true });
    return () => {
      document.removeEventListener("pointerdown", warm, { capture: true });
      document.removeEventListener("click", onClick, { capture: true });
    };
  }
}

export const sounds = new SoundManager();
