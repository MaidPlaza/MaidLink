export {};

export type AppComputeState =
  | "ACTIVE_CHAT"
  | "FOREGROUND"
  | "IDLE_FOREGROUND"
  | "BACKGROUND";

export interface MaidLinkBridge {
  readonly platform: NodeJS.Platform;
  readonly version: string;

  readonly apiToken?: string;
  readonly mediaToken?: string;

  minimize: () => void;
  maximize: () => void;
  close: () => void;
  quit: () => void;

  reportChatActivity: (isActive: boolean) => void;

  getAppState: () => Promise<AppComputeState>;

  onAppStateChange: (callback: (state: AppComputeState) => void) => () => void;

  showNotification: (title: string, body: string,
                     opts?: { kind?: "reminder" | "message"; icon?: string }) => void;

  getBounds: () => { x: number; y: number; width: number; height: number } | null;
  resize: (bounds: { x: number; y: number; width: number; height: number }) => void;
  captureScreenshot: () => Promise<string | null>;
  readThemeConfig: (id: string) => Promise<Record<string, string> | null>;

  getPathForFile: (file: File) => string;
}

declare global {
  interface Window {
    maidlink?: MaidLinkBridge;
  }
}
