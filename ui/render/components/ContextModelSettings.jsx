import React from 'react'
import ChatSettings from './settings/ChatSettings'

export default function ContextModelSettings() {
  return (
    <div className='context-model-settings-main-container' >
      <ChatSettings open home="context-model" />
    </div>
  )
}