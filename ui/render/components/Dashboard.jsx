import React from 'react'
import dashboardFrame from '../../assets/decorations/dashboard_frame.svg'
import CharaterPreviewWindow from './CharaterPreviewWindow'

const GRID_CONFIG = { cols: 6, rows: 4 }

function Marker({ r, c, maxR, maxC }) {
  const top    = r > 0
  const bottom = r < maxR
  const left   = c > 0
  const right  = c < maxC
  return (
    <div className="gm">
      <div className="gm-sq" />
      {top    && <div className="gm-t" />}
      {bottom && <div className="gm-b" />}
      {left   && <div className="gm-l" />}
      {right  && <div className="gm-r" />}
    </div>
  )
}

export default function Dashboard({ character, activeChar, identity, portraitUrl, onOpenChat, onPlayPattern, onPlayWave, dashboardVisible, expandMode }) {
  const { cols, rows } = GRID_CONFIG
  const items = []

  for (let r = 0; r <= rows; r++) {
    const mrow = []
    for (let c = 0; c <= cols; c++) {
      mrow.push(<Marker key={`m${c}`} r={r} c={c} maxR={rows} maxC={cols} />)
      if (c < cols) mrow.push(<div key={`hd${c}`} className="g-hdash" />)
    }
    items.push(<div key={`mr${r}`} className="g-mrow">{mrow}</div>)

    if (r < rows) {
      const lrow = []
      for (let c = 0; c <= cols; c++) {
        lrow.push(
          <div key={`vw${c}`} className="g-vdash-wrap">
            <div className="g-vdash" />
          </div>
        )
        if (c < cols) lrow.push(<div key={`cl${c}`} className="g-cell" />)
      }
      items.push(<div key={`lr${r}`} className="g-lrow">{lrow}</div>)
    }
  }

  return (
    <div className="dashboard">
      <div className={`dashboard-content${dashboardVisible ? ' dashboard-content--visible' : ''}`}>
          <div  className='dashboard-background no-select'>
              <svg className="dashboard-background-svg" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <defs>
                    <pattern id="dashboardBgPattern" width="46" height="46" patternUnits="userSpaceOnUse">
                        <path d="M1 45H8V46H0V38H1V45Z" />
                        <path d="M20 46H14V45.5H20V46Z"/>
                        <path d="M32 46H26V45.5H32V46Z" />
                        <path d="M46 46H38V45H45V38H46V46Z"/>
                        <path d="M0.5 32H0V26H0.5V32Z"/>
                        <path d="M46 26V32H45.5V26H46Z" />
                        <path d="M0.5 20H0V14H0.5V20Z" />
                        <path d="M46 20H45.5V14H46V20Z" />
                        <path d="M8 1H1V8H0V0H8V1Z" />
                        <path d="M46 8H45V1H38V0H46V8Z" />
                        <path d="M20 0.5H14V0H20V0.5Z"/>
                        <path d="M32 0.5H26V0H32V0.5Z" />
                    </pattern>
                  </defs>
                <rect width="100%" height="100%" fill="url(#dashboardBgPattern)"/>
              </svg>
          </div>
      </div>
           <CharaterPreviewWindow
             character={character}
             activeChar={activeChar}
             identity={identity}
             portraitUrl={portraitUrl}
             expandMode={expandMode}
           />

      <div className={`dashboard-content${dashboardVisible ? ' dashboard-content--visible' : ''}`}>
        <div  className='dashboard-chip-container'>


        </div>






      </div>

    </div>
  )
}
