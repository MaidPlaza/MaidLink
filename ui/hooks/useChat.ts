import { useState, useEffect, useCallback, useRef } from "react";
import { api, ChatSocket, type ChatStats, type GachaItem, type ModelLifecycleState } from "@/lib/api";
import { bindCommandSender } from "@/lib/commandBus";
import { resolveUrl } from "@/lib/url";
import { sounds } from "@/lib/sounds";
import moodList from "@/electron/configs/moodList.json";

const MOOD_ID_BY_NAME = new Map<string, number>(
  (moodList as Array<{ id_mood: number; name_mood: string }>).map(
    (m) => [m.name_mood.toLowerCase(), m.id_mood],
  ),
);

export interface ChatMessage {
  id: string;
  role: "user" | "character" | "system" | "divider" | "reminder_card" | "gacha_card";
  content: string;
  timestamp: Date;
  thinking?: string;
  stats?: ChatStats;
  image?: string;
  imageGenSeconds?: number;
  mediaKind?: string;
  youtubeId?: string;
  fileName?: string;
  reason?: string;
  summary?: string;
  mood?: string;
  id_mood?: number;
  streaming?: boolean;
  reminderRecordId?: string;
  reminderKind?: "one_shot" | "pre_event";
  reminderEventAtIso?: string;
  reminderFallback?: string;
  reminderAcknowledged?: boolean;
  gacha?: GachaItem & { unlocked?: number; total?: number };
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentThinking, setCurrentThinking] = useState<string | null>(null);
  const [modelState, setModelState] = useState<ModelLifecycleState | null>(null);
  const [personaStatus, setPersonaStatus] = useState<{ state: string; reason: string } | null>(null);
  const [appStatus, setAppStatus] = useState('');
  const [portraitVersion, setPortraitVersion] = useState(0);
  const [gachaVersion, setGachaVersion] = useState(0);
  const [contextWindow, setContextWindow] = useState(0);

  const socketRef = useRef<ChatSocket | null>(null);
  const pendingThinkingRef = useRef<string | null>(null);
  const messageIdRef = useRef(0);
  const streamingIdRef = useRef<string | null>(null);
  const streamTargetRef = useRef("");
  const streamShownRef = useRef(0);
  const streamDoneRef = useRef(false);
  const streamTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopTypewriter = () => {
    if (streamTimerRef.current) {
      clearInterval(streamTimerRef.current);
      streamTimerRef.current = null;
    }
    streamTargetRef.current = "";
    streamShownRef.current = 0;
    streamDoneRef.current = false;
  };

  const ensureTypewriter = () => {
    if (streamTimerRef.current) return;
    streamTimerRef.current = setInterval(() => {
      const sid = streamingIdRef.current;
      if (sid == null) {
        stopTypewriter();
        return;
      }
      const target = streamTargetRef.current;
      const shown = streamShownRef.current;
      if (shown >= target.length) {
        if (streamDoneRef.current) {
          streamingIdRef.current = null;
          setMessages((prev) => prev.map((m) =>
            m.id === sid ? { ...m, streaming: undefined } : m));
          stopTypewriter();
        }
        return;
      }
      const backlog = target.length - shown;
      const base = streamDoneRef.current ? 3 : 1;
      const step = base + Math.floor(backlog / 40);
      const next = Math.min(target.length, shown + step);
      streamShownRef.current = next;
      setMessages((prev) => prev.map((m) =>
        m.id === sid ? { ...m, content: target.slice(0, next) } : m));
    }, 24);
  };
  const lastKeystrokeAtRef = useRef<number>(0);
  const lastTypingAtRef = useRef<number>(0);

  const nextId = () => {
    messageIdRef.current += 1;
    return `msg-${messageIdRef.current}`;
  };

  useEffect(() => {
    const socket = new ChatSocket({
      onConnect: () => setIsConnected(true),
      onDisconnect: () => setIsConnected(false),

      onThinking: (text) => {
        console.log("%c[thinking]", "color:#888", text);
        pendingThinkingRef.current = text;
        setCurrentThinking(text);
      },

      onDebug: (tag, data) => {
        if (tag === "grammar" && data && typeof data === "object") {
          const d = data as { before?: string; after?: string };
          console.log("%c[grammar]", "color:#7B79AB;font-weight:bold", d.before, "→", d.after);
        } else {
          console.log(`%c[${tag}]`, "color:#7B79AB;font-weight:bold", data);
        }
      },

      onResponseChunk: (text) => {
        streamTargetRef.current += text;
        if (streamingIdRef.current == null) {
          const nid = nextId();
          streamingIdRef.current = nid;
          streamShownRef.current = 0;
          streamDoneRef.current = false;
          setMessages((prev) => [
            ...prev,
            { id: nid, role: "character", content: "",
              timestamp: new Date(), streaming: true },
          ]);
        }
        ensureTypewriter();
      },

      onStreamReset: () => {
        const sid = streamingIdRef.current;
        streamingIdRef.current = null;
        stopTypewriter();
        if (sid != null) {
          setMessages((prev) => prev.filter((m) => m.id !== sid));
        }
      },

      onResponseSplit: (text, split_id_mood) => {
        const sid = streamingIdRef.current;
        streamingIdRef.current = null;
        stopTypewriter();
        if (sid != null) {
          setMessages((prev) => prev.map((m) =>
            m.id === sid ? { ...m, content: text, streaming: undefined,
                            id_mood: split_id_mood ?? m.id_mood } : m));
        } else {
          setMessages((prev) => [
            ...prev,
            { id: nextId(), role: "character", content: text,
              timestamp: new Date(), id_mood: split_id_mood ?? 0 },
          ]);
        }
      },

      onResponse: (text, id_mood) => {
        const thinking = pendingThinkingRef.current;
        pendingThinkingRef.current = null;
        setCurrentThinking(null);

        const sid = streamingIdRef.current;
        if (sid != null && text.length >= streamShownRef.current) {
          streamTargetRef.current = text;
          streamDoneRef.current = true;
          setMessages((prev) => prev.map((m) =>
            m.id === sid ? { ...m, thinking: thinking || undefined,
                            id_mood: id_mood ?? m.id_mood ?? 0 } : m));
          ensureTypewriter();
        } else {
          streamingIdRef.current = null;
          stopTypewriter();
          setMessages((prev) => {
            if (sid != null && prev.some((m) => m.id === sid)) {
              return prev.map((m) =>
                m.id === sid
                  ? { ...m, content: text, streaming: undefined,
                      thinking: thinking || undefined,
                      id_mood: id_mood ?? m.id_mood ?? 0 }
                  : m);
            }
            return [
              ...prev,
              {
                id: nextId(),
                role: "character",
                content: text,
                timestamp: new Date(),
                thinking: thinking || undefined,
                id_mood: id_mood ?? 0,
              },
            ];
          });
        }

        api
          .identity()
          .then((idn) => {
            const st =
              idn.reaction_state || (idn.mood_effective?.[0] ?? idn.mood_state);
            sounds.playMood(st);
            if (st && st !== "ровное") {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (!last || last.role !== "character" || last.mood) return prev;
                const fallbackId =
                  id_mood == null
                    ? MOOD_ID_BY_NAME.get(st.toLowerCase())
                    : undefined;
                return [...prev.slice(0, -1), {
                  ...last, mood: st,
                  id_mood: last.id_mood || fallbackId || last.id_mood,
                }];
              });
            }
          })
          .catch(() => sounds.playMood(null));
      },

      onStats: (stats) => {
        setMessages((prev) => {
          const depthCap = Math.max(0, prev.length - 8);
          for (let i = prev.length - 1; i >= depthCap; i--) {
            if (prev[i].role === "character") {
              const next = [...prev];
              next[i] = { ...prev[i], stats };
              return next;
            }
          }
          return prev;
        });
        if (stats.hist_tokens != null && stats.hist_budget) {
          setContextWindow(Math.max(0, Math.min(1, stats.hist_tokens / stats.hist_budget)));
        } else if (stats.ctx_tokens != null && stats.ctx_budget) {
          setContextWindow(Math.max(0, Math.min(1, stats.ctx_tokens / stats.ctx_budget)));
        }
      },

      onToolCall: (name, result) => {
        const text = result ? `${name}: ${result}` : name;
        if (!import.meta.env.DEV) console.log(`[tool] ${text}`);
        const content = import.meta.env.DEV ? `🔧 ${text}` : `Вызван инструмент ${name}`;
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "system", content, timestamp: new Date() },
        ]);
      },

      onSystem: (text) => {
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "system", content: text, timestamp: new Date() },
        ]);
      },

      onImage: (url, _prompt, gen_seconds, media) => {
        const fullUrl = resolveUrl(url);
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "character",
            content: "",
            timestamp: new Date(),
            image: fullUrl,
            imageGenSeconds: gen_seconds,
            mediaKind: media,
          },
        ]);
      },

      onAppStatus: (text) => setAppStatus(text || ''),

      onVideoEmbed: (videoId, _url) => {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "character",
            content: "",
            timestamp: new Date(),
            youtubeId: videoId,
          },
        ]);
      },

      onModelState: (state) => {
        setModelState(state);
      },

      onNotification: (title, body, opts) => {
        if (opts?.kind !== "message" && (!document.hasFocus() || document.hidden)) {
          sounds.play("notify");
        }
        window.maidlink?.showNotification(title, body, opts);
      },

      onReminderCard: (card) => {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "reminder_card",
            content: card.title,
            timestamp: new Date(),
            reminderRecordId: card.record_id,
            reminderKind: card.kind,
            reminderEventAtIso: card.event_at_iso,
            reminderFallback: card.fallback_text,
            reminderAcknowledged: false,
          },
        ]);
      },

      onReminderAcknowledged: (recordId) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.role === "reminder_card" && m.reminderRecordId === recordId
              ? { ...m, reminderAcknowledged: true }
              : m
          )
        );
      },

      onPersonaStatus: (state, reason) => {
        setPersonaStatus(state ? { state, reason } : null);
      },

      onPortraitUpdated: (_charId, _url) => {
        setPortraitVersion((v) => v + 1);
      },

      onGachaChanged: () => {
        setGachaVersion((v) => v + 1);
      },

      onSessionEnded: (reason, summary, mood) => {
        console.log("[chat] session ended:", reason);
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "divider",
            content: "Сессия завершена",
            timestamp: new Date(),
            reason,
            summary,
            mood,
          },
        ]);
        setCurrentThinking(null);
        setIsGenerating(false);
      },

      onDone: () => {
        setIsGenerating(false);
      },

      onError: (text) => {
        console.error("Chat error:", text);
        setIsGenerating(false);
      },
    });

    socket.connect();
    socketRef.current = socket;
    bindCommandSender((text) => socket.send(text));

    return () => {
      bindCommandSender(null);
      socket.disconnect();
      stopTypewriter();
    };
  }, []);

  const sendMessage = useCallback(
    (text: string, image?: string, file?: { name: string }) => {
      if ((!text.trim() && !image && !file) || !socketRef.current?.connected) return;

      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "user",
          content: text || (image ? "[изображение]" : "[файл]"),
          timestamp: new Date(),
          image,
          fileName: file?.name,
        },
      ]);

      setIsGenerating(true);
      setCurrentThinking(null);
      socketRef.current.send(text, image);
    },
    [],
  );

  const postFileMessage = useCallback((name: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: nextId(),
        role: "user",
        content: "[файл]",
        timestamp: new Date(),
        fileName: name,
      },
    ]);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  const pushSystem = useCallback((content: string) => {
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "system", content, timestamp: new Date() },
    ]);
  }, []);

  const pushGachaCard = useCallback((item: GachaItem, progress?: { unlocked?: number; total?: number }) => {
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "gacha_card", content: item.label, timestamp: new Date(),
        gacha: { ...item, ...(progress || {}) } },
    ]);
  }, []);

  const notifyKeystroke = useCallback(() => {
    if (!socketRef.current?.connected) return;
    const now = Date.now();
    if (now - lastTypingAtRef.current >= 1_500) {
      lastTypingAtRef.current = now;
      socketRef.current.typing();
    }
    if (modelState === "LOADED" || modelState === "LOADING") return;
    if (now - lastKeystrokeAtRef.current < 30_000) return;
    lastKeystrokeAtRef.current = now;
    socketRef.current.keystroke();
  }, [modelState]);

  const acknowledgeReminder = useCallback((recordId: string) => {
    socketRef.current?.acknowledgeReminder(recordId);
    setMessages((prev) =>
      prev.map((m) =>
        m.role === "reminder_card" && m.reminderRecordId === recordId
          ? { ...m, reminderAcknowledged: true }
          : m
      )
    );
  }, []);

  return {
    messages,
    sendMessage,
    postFileMessage,
    clearMessages,
    pushSystem,
    pushGachaCard,
    notifyKeystroke,
    acknowledgeReminder,
    isConnected,
    isGenerating,
    currentThinking,
    modelState,
    personaStatus,
    appStatus,
    portraitVersion,
    gachaVersion,
    contextWindow,
  };
}
