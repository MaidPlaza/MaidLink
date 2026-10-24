let _send: ((text: string) => void) | null = null;

export function bindCommandSender(send: ((text: string) => void) | null): void {
  _send = send;
}

export function sendCommand(text: string): void {
  if (_send) {
    _send(text);
  } else {
    console.warn(`[commandBus] sender не привязан — команда «${text}» не отправлена`);
  }
}
