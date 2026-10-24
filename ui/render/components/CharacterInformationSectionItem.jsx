import React, { useState, useId } from 'react'

export default function CharacterInformationSectionItem({ title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  const patternId = `char-info-line-dash-${useId().replace(/:/g, '')}`

  return (
    <div className="character-information-list-item-container">
      <div
        className={`character-information-list-item-container-header${open ? ' is-open' : ''}`}
        onClick={() => setOpen((v) => !v)}
      >
        <svg className="character-information-list-item-container-header-toggle-icon" width="15" height="15" viewBox="0 0 15 15" xmlns="http://www.w3.org/2000/svg">
          <path d="M9.5 5.5H15V9.5H9.5V15H5.5V9.5H0V5.5H5.5V0H9.5V5.5Z" />
        </svg>

        <span className="character-information-list-item-container-header-name">
          {title}
        </span>

        <svg className="character-information-list-item-line" width="8" height="11" viewBox="0 0 8 11" xmlns="http://www.w3.org/2000/svg">
          <path d="M1 9.5L1 8.5L8.52207e-08 8.5L0 9.5L1 9.5ZM5 9.5L5 8.5L3 8.5L3 9.5L5 9.5ZM8 9.5L8 8.5L7 8.5L7 9.5L8 9.5Z" />
          <path d="M0 5H8V6H0V5Z" />
        </svg>

        <svg className="character-information-list-item-line is-pattern" width="100%" height="11" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id={patternId} width="8" height="11" patternUnits="userSpaceOnUse">
              <path d="M1 9.5L1 8.5L8.52207e-08 8.5L0 9.5L1 9.5ZM5 9.5L5 8.5L3 8.5L3 9.5L5 9.5ZM8 9.5L8 8.5L7 8.5L7 9.5L8 9.5Z" />
              <path d="M0 5H8V6H0V5Z" />
            </pattern>
          </defs>
          <rect width="100%" height="11" fill={`url(#${patternId})`}/>
        </svg>

        <svg className="character-information-list-item-line" width="11" height="11" viewBox="0 0 11 11" xmlns="http://www.w3.org/2000/svg">
          <path d="M7.4375 9.5L7.4375 8.5L8.5 8.5L8.5 9.5L7.4375 9.5ZM3.1875 9.5L3.1875 8.5L5.3125 8.5L5.3125 9.5L3.1875 9.5ZM0 9.5L8.52207e-08 8.5L1.0625 8.5L1.0625 9.5L0 9.5Z" />
          <path d="M11 11L1.91602 6H0V5H1.90234L11 0V11Z" />
        </svg>
      </div>

      <div className={`character-information-list-item-content${open ? ' is-open' : ''}`}>
        {children}
      </div>
    </div>
  )
}
