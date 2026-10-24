import React from 'react'

export default function ChatLoaderBar() {
  return (
    <svg
      className="chat-loader-bar"
      width="280"
      height="40"
      viewBox="0 0 280 40"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Идёт обработка"
    >
      <rect className="chat-loader-bar-body" x="51" y="5" width="223" height="30" />
      <path className="chat-loader-bar-cap" d="M35.5 20 L51 5 L51 35 Z" />

      <path className="chat-loader-bar-chev chat-loader-bar-chev--1" d="M30.5 20 L46 35 L41 35 L25.5 20 L41 5 L46 5 Z" />
      <path className="chat-loader-bar-chev chat-loader-bar-chev--2" d="M20.5 20 L36 35 L31 35 L15.5 20 L31 5 L36 5 Z" />
      <path className="chat-loader-bar-chev chat-loader-bar-chev--3" d="M10.5 20 L26 35 L21 35 L5.5 20 L21 5 L26 5 Z" />
    </svg>
  )
}
