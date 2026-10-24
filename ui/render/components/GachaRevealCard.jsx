import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { watchVisibility } from '@/lib/offscreen'

const PHASES = ['grow', 'ticket', 'flash', 'spin', 'settle', 'morph', 'reveal', 'done']
const PHASE_MS = { grow: 300, ticket: 2600, flash: 400, spin: 2400, settle: 450, morph: 450, reveal: 750 }

const RARITIES = ['common', 'rare', 'legendary']
const RARITY_WEIGHTS = { common: 5, rare: 3, legendary: 2 }
const REEL_SIZE = 10
const REEL_LOOPS = 3
const REEL_WIN_SLOT = 6
const REEL_WIN = (REEL_LOOPS - 1) * REEL_SIZE + REEL_WIN_SLOT
const REEL_DOT = 18
const REEL_STEP = 26
const REEL_WINDOW = 68

const revealedCards = new Set()
export function isGachaRevealed(id) {
  return revealedCards.has(id)
}

function prefersReducedMotion() {
  return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function buildReel(rarity) {
  const total = RARITIES.reduce((s, r) => s + RARITY_WEIGHTS[r], 0)
  const pick = () => {
    let x = Math.random() * total
    for (const r of RARITIES) {
      x -= RARITY_WEIGHTS[r]
      if (x < 0) return r
    }
    return RARITIES[0]
  }
  const base = Array.from({ length: REEL_SIZE }, pick)
  base[REEL_WIN_SLOT] = rarity
  return Array.from({ length: REEL_SIZE * REEL_LOOPS }, (_, i) => base[i % REEL_SIZE])
}

export default function GachaRevealCard({ id, item, onRevealed }) {
  const g = item || {}
  const rarity = RARITIES.includes(g.rarity) ? g.rarity : 'common'
  const [animated] = useState(() => !revealedCards.has(id) && !prefersReducedMotion())
  const [phase, setPhase] = useState(animated ? 'grow' : 'done')
  const [reel] = useState(() => buildReel(rarity))
  const uid = 'gr' + useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const onRevealedRef = useRef(onRevealed)
  useEffect(() => { onRevealedRef.current = onRevealed })

  useEffect(() => {
    if (phase === 'done') {
      if (!revealedCards.has(id)) {
        revealedCards.add(id)
        onRevealedRef.current?.(id)
      }
      return
    }
    const t = setTimeout(() => setPhase(PHASES[PHASES.indexOf(phase) + 1]), PHASE_MS[phase])
    return () => clearTimeout(t)
  }, [phase, id])

  const at = (p) => PHASES.indexOf(phase) >= PHASES.indexOf(p)
  const reelFrom = REEL_WINDOW / 2 - REEL_DOT / 2
  const reelTo = REEL_WINDOW / 2 - (REEL_WIN * REEL_STEP + REEL_DOT / 2)
  const style = {
    '--gr-grow-ms': `${PHASE_MS.grow}ms`,
    '--gr-ticket-ms': `${PHASE_MS.ticket}ms`,
    '--gr-flash-ms': `${PHASE_MS.flash}ms`,
    '--gr-spin-ms': `${PHASE_MS.spin}ms`,
    '--gr-settle-ms': `${PHASE_MS.settle}ms`,
    '--gr-morph-ms': `${PHASE_MS.morph}ms`,
    '--gr-dot': `${REEL_DOT}px`,
    '--gr-gap': `${REEL_STEP - REEL_DOT}px`,
    '--gr-window': `${REEL_WINDOW}px`,
    '--gr-reel-from': `${reelFrom}px`,
    '--gr-reel-to': `${reelTo}px`,
  }
  const cls = [
    'chat-gacha-reveal', `is-${rarity}`, `is-phase-${phase}`,
    !animated && 'is-static',
    at('spin') && 'is-white',
    at('settle') && 'is-settled',
    at('morph') && 'is-morphed',
  ].filter(Boolean).join(' ')
  const progress = g.total ? `${g.unlocked ?? 0} из ${g.total}` : ''

  return (
    <div className={cls} style={style} role="group" aria-label={`Билет удачи: ${g.label || ''}`}>
      <div className="gr-box">
        {phase === 'ticket' && <TicketInsert uid={uid} />}
        {phase === 'flash' && <div className="gr-flash" />}
        {at('spin') && !at('reveal') && (
          <div className="gr-reel-window">
            <div className="gr-reel">
              {reel.map((r, i) => (
                <span key={i} className={`gr-dot is-${r}${i === REEL_WIN ? ' is-win' : ''}`} />
              ))}
            </div>
          </div>
        )}
      </div>
      {at('reveal') && <GachaResult uid={uid} g={g} progress={progress} />}
    </div>
  )
}

function TicketInsert({ uid }) {
  return (
    <svg className="gr-ticket" width="50" height="50" viewBox="0 0 50 50" fill="none"
         strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <defs>
        <clipPath id={`${uid}-slot`}>
          <rect x="0" y="0" width="50" height="30" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${uid}-slot)`}>
        <g className="gr-ticket-slip">
          <path d="M18.5 3H22A3 3 0 0 0 28 3H31.5Q33 3 33 4.5V25.5Q33 27 31.5 27H28A3 3 0 0 0 22 27H18.5Q17 27 17 25.5V4.5Q17 3 18.5 3Z" />
          <path d="M18.5 9H31.5M18.5 21H31.5" strokeLinecap="butt" strokeDasharray="2 1.667" />
          <rect x="21" y="11.5" width="8" height="7" rx="1.5" />
        </g>
      </g>
      <g className="gr-ticket-device">
        <rect x="8" y="30" width="34" height="17" rx="3" />
        <path d="M14 30H36" strokeWidth="3" />
      </g>
    </svg>
  )
}

function GachaResult({ uid, g, progress }) {
  return (
    <div className="gr-result">
      <svg className="gr-art" width="322" height="111" viewBox="0 0 322 111" fill="none" aria-hidden="true">
        <defs>
          <pattern id={`${uid}-pat`} x="58" y="47" width="31.975" height="31.8984" patternUnits="userSpaceOnUse">
            <g className="gr-pattern-tile">
              <rect x="15.2631" y="0.8984" width="15.9873" height="1.5947" />
              <rect x="18.8607" y="4.0879" width="12.3897" height="1.5957" />
              <rect x="5.6709" y="2.4931" width="1.5986" height="4.7852" />
              <rect x="4.0723" y="4.0879" width="4.7959" height="1.5957" />
              <rect x="15.2631" y="7.2783" width="15.9873" height="1.5947" />
              <rect x="15.2631" y="10.4677" width="7.9941" height="1.5957" />
              <circle cx="2.0732" cy="12.0634" r="1.199" />
              <circle cx="6.0703" cy="12.0634" r="1.199" />
              <circle cx="2.0732" cy="16.0507" r="1.199" />
              <circle cx="6.0703" cy="16.0507" r="1.199" />
              <circle cx="10.0674" cy="16.0507" r="1.199" />
              <circle cx="14.0645" cy="16.0507" r="1.199" />
              <circle cx="2.0732" cy="20.038" r="1.199" />
              <circle cx="6.0703" cy="20.038" r="1.199" />
              <circle cx="10.0674" cy="20.038" r="1.199" />
              <path d="M21.2592 18.0439A1.998 1.998 0 0 1 25.2552 18.0439Z" />
              <path d="M29.2523 18.0439A1.998 1.998 0 0 1 25.2563 18.0439Z" />
              <path d="M4.8721 29.2089A1.998 1.998 0 0 1 8.8681 29.2089Z" />
              <path d="M12.8652 29.2089A1.998 1.998 0 0 1 8.8692 29.2089Z" />
              <path d="M20.8588 23.2275H24.8559L22.8578 31.2021Z" />
              <path d="M24.8559 23.2275H28.8529L26.8539 31.2021Z" />
              <rect x="15.2631" y="24.4238" width="1.5986" height="1.5947" />
              <rect x="12.0654" y="24.4238" width="1.5986" height="1.5947" />
              <rect x="13.665" y="22.8291" width="1.5986" height="1.5947" />
              <rect x="15.2631" y="21.2343" width="1.5986" height="1.5947" />
            </g>
          </pattern>
          <path id={`${uid}-blob`} d="M47.247 107.374C49.4398 107.661 51.6496 106.981 53.3104 105.509C54.9963 104.013 55.951 101.861 55.9279 99.601C55.9167 98.3151 55.8403 96.9711 55.6988 95.5508C56.5621 94.9258 57.3463 94.311 58.0783 93.6831C60.0377 92.0042 61.0271 89.4756 60.7242 86.9195C60.4213 84.3612 58.8636 82.1303 56.5588 80.9533C55.2586 80.287 53.8536 79.7135 52.219 79.1867C51.9374 78.3194 51.6062 77.3896 51.1984 76.4467C49.5125 71.8818 46.2772 70.8157 44.4882 70.5816C44.4489 70.5765 44.4034 70.5714 44.3641 70.5664C42.13 70.3069 39.8879 71.0521 38.2515 72.5724C38.103 72.7086 37.9598 72.8512 37.8284 72.9913C36.9605 73.8946 36.086 74.9892 35.1493 76.3622C35.0867 76.454 35.0243 76.5458 34.9617 76.6367C34.9393 76.6367 34.9174 76.6367 34.895 76.6367C33.6776 76.6356 32.6427 76.6682 31.6443 76.7376C28.9327 76.9245 26.4998 78.5628 25.3004 81.013C24.0892 83.4922 24.293 86.4534 25.8336 88.7408C26.3204 89.4657 26.823 90.1581 27.3328 90.8266C27.2287 91.0768 27.1259 91.3311 27.0248 91.5877C26.9726 91.7127 26.9027 91.8601 26.8311 92.0176C26.1607 93.4815 25.1471 95.6925 25.3661 98.3755C25.6682 101.968 28.4764 104.901 32.0441 105.367C32.8294 105.47 33.7237 105.442 34.5013 105.291C36.4801 104.897 38.3576 104.303 40.1405 103.629C40.4353 103.855 40.7301 104.075 41.031 104.291C42.0626 105.03 43.3226 105.888 44.8247 106.636C45.5894 107.016 46.4052 107.263 47.247 107.374Z" />
          <g id={`${uid}-badge`}>
            <use href={`#${uid}-blob`} className="gr-badge-shadow" transform="translate(1.7 3.1)" />
            <use href={`#${uid}-blob`} className="gr-badge-body" />
            <use href={`#${uid}-blob`} className="gr-badge-outline" />
            <path className="gr-badge-star" d="M32.1554 84.0415C33.0688 83.9769 33.9807 83.9567 34.8952 83.9567C35.9997 83.9567 38.0771 84.4573 39.0322 83.8333C39.4028 83.591 39.7934 82.642 40.0346 82.2565C40.408 81.657 40.8008 81.0711 41.1986 80.4888C41.8 79.6083 42.4474 78.7525 43.1853 77.9821C43.1974 77.97 43.2094 77.9608 43.2226 77.9507C43.2923 77.8729 43.3973 77.8235 43.5326 77.8387C44.0304 77.8962 44.2623 78.8632 44.4229 79.2296C44.9743 80.4824 45.3739 81.8061 45.7644 83.1145C45.9413 83.71 46.0643 84.5388 46.4248 85.0568C46.7527 85.5291 48.2116 85.6343 48.7357 85.7817C50.2844 86.2197 51.7924 86.7369 53.2268 87.4714C53.4843 87.6028 53.5348 87.9239 53.3108 88.1175C52.5435 88.7736 51.7438 89.3784 50.9181 89.9568C49.8512 90.7039 47.7101 91.3965 47.9563 92.9005C48.3249 95.1377 48.5824 97.4018 48.6023 99.6701C48.6054 99.9307 48.3699 100.211 48.0835 100.069C47.0983 99.5792 46.1897 98.9694 45.2972 98.3295C44.7388 97.9297 44.2008 97.5027 43.6635 97.0756C42.9366 96.4942 41.7678 94.998 40.6736 95.4784C38.2445 96.5453 35.7058 97.5762 33.093 98.0951C32.9001 98.1335 32.6842 97.9699 32.6679 97.7742C32.5831 96.7424 33.4675 95.2119 33.839 94.2702C34.1852 93.3918 34.5698 92.5286 34.9575 91.6695C35.128 91.293 36.0014 89.8687 35.8964 89.7426C34.5132 88.0929 33.1099 86.4313 31.9098 84.6425C31.7635 84.425 31.8543 84.0617 32.1554 84.0415Z" />
          </g>
        </defs>

        <g className="gr-part gr-part--panel">
          <path className="gr-grid" d="M82 97.5V85M82 30V38.5M82 38.5H296.5M82 38.5V85M82 85H39M82 85H296.5M137 85L136 30M137 85V97.5M188.5 85V97.5M188.5 85V30M235 85V30V95.5M270 85V30V95.5" />
          <path className="gr-panel" d="M39 16H234V76C234 78.7614 231.761 81 229 81H39V16Z" />
          <path d="M39 16H234V76C234 78.7614 231.761 81 229 81H39V16Z" fill={`url(#${uid}-pat)`} />
        </g>

        <g className="gr-part gr-part--progress">
          <rect className="gr-accent" x="181" y="88" width="130" height="20" rx="5" />
          <rect className="gr-on-accent" x="188" y="95" width="5" height="5" />
          <rect className="gr-on-accent" x="198" y="95" width="5" height="5" />
          <rect className="gr-on-accent" x="288" y="95" width="5" height="5" />
          <rect className="gr-on-accent" x="298" y="95" width="5" height="5" />
          <path className="gr-on-accent-line" d="M207 97.5H220M284 97.5H271" />
        </g>

        <g className="gr-part gr-part--variant">
          <rect className="gr-accent" x="219" width="30" height="30" rx="5" />
          <rect className="gr-accent gr-square-frame" x="221" y="2" width="26" height="26" rx="3" />
          <VariantMark uid={uid} g={g} />
        </g>

        <g className="gr-part gr-part--ticket">
          <rect className="gr-accent" x="254" width="30" height="30" rx="5" />
          <rect className="gr-accent gr-square-frame" x="256" y="2" width="26" height="26" rx="3" />
          <path className="gr-on-accent" transform="translate(35 0)" d="M229.645 20.3956L229.082 21.014L230.936 22.8678C231.776 23.7075 233.142 23.7075 233.982 22.8679L242.866 13.9836C243.706 13.144 243.706 11.7779 242.866 10.9382L241.058 9.12989L240.45 9.58534C240.268 9.72188 240.009 9.70345 239.848 9.54258C239.687 9.38172 239.669 9.12311 239.805 8.94114L240.261 8.3331L238.452 6.52446C237.613 5.68493 236.247 5.68493 235.407 6.52453L226.523 15.4089C225.683 16.2485 225.683 17.6146 226.523 18.4541L228.377 20.3084L228.995 19.7451C229.178 19.5792 229.457 19.5855 229.631 19.7595C229.805 19.9336 229.811 20.2131 229.645 20.3956ZM228.421 18.8128L227.293 17.6841C226.878 17.2692 226.878 16.5939 227.293 16.1789L236.177 7.29452C236.592 6.87955 237.267 6.87955 237.682 7.29445L238.831 8.44354C238.488 9.04133 238.581 9.81552 239.078 10.3126C239.575 10.8095 240.349 10.9026 240.947 10.5593L242.096 11.7082C242.511 12.1233 242.511 12.7986 242.096 13.2136L233.212 22.0979C232.797 22.5129 232.121 22.5129 231.706 22.0978L230.578 20.9693C231.001 20.3613 230.938 19.527 230.401 18.9896C229.863 18.4522 229.029 18.3893 228.421 18.8128ZM235.895 10.0394L236.083 9.85156L235.273 9.04142L235.085 9.22924L234.962 9.35203L234.774 9.53985L235.585 10.35L235.772 10.1622L235.895 10.0394ZM237.319 11.4613L237.507 11.2734L236.697 10.4633L236.509 10.6511L236.386 10.7739L236.198 10.9617L237.008 11.7719L237.196 11.5841L237.319 11.4613ZM238.741 12.8753L238.929 12.6875L238.119 11.8772L237.931 12.065L237.808 12.1878L237.62 12.3756L238.431 13.1859L238.619 12.9981L238.741 12.8753ZM240.166 14.305L240.354 14.1172L239.543 13.307L239.356 13.4948L239.233 13.6176L239.045 13.8055L239.855 14.6156L240.043 14.4278L240.166 14.305ZM235.788 14.2626L234.733 16.334L236.376 17.9778L234.08 17.6141L233.025 19.6855L232.661 17.3894L230.365 17.0257L232.436 15.9703L232.073 13.6741L233.717 15.318L235.788 14.2626Z" />
        </g>

        <g className="gr-part gr-part--title">
          <path className="gr-soft gr-star-frame" d="M5 0.5H29.5V29.5H5C2.51472 29.5 0.5 27.4853 0.5 25V5C0.5 2.59234 2.39083 0.626322 4.76855 0.505859L5 0.5Z" />
          <path className="gr-accent" d="M15 6L17.0206 12.2188H23.5595L18.2694 16.0623L20.2901 22.2812L15 18.4377L9.70993 22.2812L11.7306 16.0623L6.44049 12.2188H12.9794L15 6Z" />
          <path className="gr-accent" d="M30 0H209C211.761 0 214 2.23858 214 5V25C214 27.7614 211.761 30 209 30H30V0Z" />
        </g>

        <g className="gr-part gr-part--badge-a">
          <use href={`#${uid}-badge`} />
        </g>

        <g className="gr-part gr-part--rarity">
          <rect className="gr-rarity-pill" x="193.5" y="42.5" width="107" height="21" rx="6.5" />
        </g>

        <g transform="translate(259 -39)">
          <g className="gr-part gr-part--badge-b">
            <use href={`#${uid}-badge`} />
          </g>
        </g>
      </svg>

      <ScrollText className="gr-text gr-text--title gr-part gr-part--title">{g.label}</ScrollText>
      <div className="gr-text gr-text--tags gr-part gr-part--tags">
        {g.category_label && <ScrollText># {g.category_label}</ScrollText>}
        {g.special
          ? g.hint && <ScrollText>{g.hint}</ScrollText>
          : (g.colored_tag || g.tag) && <ScrollText># {g.colored_tag || g.tag}</ScrollText>}
      </div>
      <div className="gr-text gr-text--rarity gr-part gr-part--rarity">{g.rarity_label}</div>
      {progress && <div className="gr-text gr-text--progress gr-part gr-part--progress">{progress}</div>}
    </div>
  )
}

const VARIANT_LINES = {
  striped: 'M223 7H245M223 11H245M223 15H245M223 19H245M223 23H245',
  'vertical-striped': 'M226 4V26M230 4V26M234 4V26M238 4V26M242 4V26',
  ribbed: 'M224.5 4V26M227 4V26M229.5 4V26M232 4V26M234.5 4V26M237 4V26M239.5 4V26M242 4V26M244.5 4V26',
  plaid: 'M223 9H245M223 15H245M223 21H245M228 4V26M234 4V26M240 4V26',
}
const STAR = 'M15 6L17.0206 12.2188H23.5595L18.2694 16.0623L20.2901 22.2812L15 18.4377L9.70993 22.2812L11.7306 16.0623L6.44049 12.2188H12.9794L15 6Z'
function PatternMark({ pattern }) {
  if (VARIANT_LINES[pattern]) {
    return <path className={`gr-variant-line is-${pattern.replace(/\s/g, '-')}`} d={VARIANT_LINES[pattern]} />
  }
  switch (pattern) {
    case 'polka dot':
      return (
        <g className="gr-variant-ink">
          {[[227, 8], [234, 8], [241, 8], [230.5, 15], [237.5, 15], [227, 22], [234, 22], [241, 22]]
            .map(([cx, cy]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="1.7" />)}
        </g>
      )
    case 'star print':
      return <path className="gr-variant-ink" transform="translate(219 0.5)" d={STAR} />
    case 'strawberry print':
      return (
        <g>
          <path className="gr-variant-ink" d="M234 24C228.5 19.5 227.5 13.8 231 12C232.4 11.3 233.4 11.6 234 12.2C234.6 11.6 235.6 11.3 237 12C240.5 13.8 239.5 19.5 234 24Z" />
          <path className="gr-variant-line" d="M230.5 10.5L234 8.5L237.5 10.5M234 8.5V6.5" />
        </g>
      )
    case 'bear print':
      return (
        <g className="gr-variant-ink">
          <circle cx="229.6" cy="10.6" r="2.4" />
          <circle cx="238.4" cy="10.6" r="2.4" />
          <circle cx="234" cy="16.5" r="5.8" />
        </g>
      )
    case 'cat print':
      return <path className="gr-variant-ink" d="M228 14.5L228.8 7.5L232.3 10.8H235.7L239.2 7.5L240 14.5C240 21 228 21 228 14.5Z" />
    case 'leopard print':
      return (
        <g className="gr-variant-line">
          {[[227.5, 8.5], [238.5, 7.5], [233, 14.5], [242.5, 15.5], [227.5, 21], [238, 22]]
            .map(([cx, cy]) => <ellipse key={`${cx}-${cy}`} cx={cx} cy={cy} rx="2.3" ry="1.7" />)}
        </g>
      )
    case 'floral print':
      return (
        <g>
          <g className="gr-variant-ink">
            {[0, 72, 144, 216, 288].map((a) => (
              <circle key={a} cx={234 + 4.2 * Math.sin((a * Math.PI) / 180)}
                      cy={15 - 4.2 * Math.cos((a * Math.PI) / 180)} r="2.9" />
            ))}
          </g>
          <circle className="gr-accent" cx="234" cy="15" r="1.8" />
        </g>
      )
    default:
      return (
        <g className="gr-variant-ink">
          <circle cx="228" cy="9" r="1.6" />
          <rect x="237" y="6.5" width="3.4" height="3.4" transform="rotate(20 238.7 8.2)" />
          <path d="M229 21.5L231.8 16.8L234.6 21.5Z" />
          <circle cx="241.5" cy="20.5" r="1.4" />
          <circle cx="235.5" cy="13.5" r="1.1" />
        </g>
      )
  }
}

function VariantMark({ uid, g }) {
  const pattern = !g.special && g.pattern ? g.pattern : ''
  const color = !g.special && !pattern && g.color ? g.color : ''
  const name = pattern ? (g.pattern_label || pattern) : color ? (g.color_label || color) : ''
  const hint = name && `${name}${pattern ? ' · новый узор' : g.new_item === false ? ' · новый цвет' : ''}`
  return (
    <g className="gr-variant">
      <title>{hint || 'без цвета и узора'}</title>
      {pattern ? (
        <>
          <clipPath id={`${uid}-variant`}>
            <rect x="223" y="4" width="22" height="22" rx="2" />
          </clipPath>
          <g clipPath={`url(#${uid}-variant)`}>
            <PatternMark pattern={pattern} />
          </g>
        </>
      ) : color ? (
        <rect className={`gr-variant-swatch is-${color}`} x="223.5" y="4.5" width="21" height="21" rx="2" />
      ) : (
        <path className="gr-variant-dash" d="M229 15H239" />
      )}
    </g>
  )
}

const SCROLL_PX_PER_S = 30
const SCROLL_HOLD_MS = 1200
const SCROLL_RETURN_MS = 450
const SCROLL_FADE_MS = 300
const SCROLL_FADE = '16px'
function ScrollText({ className = '', children }) {
  const box = useRef(null)
  const text = useRef(null)
  const [shift, setShift] = useState(0)
  useLayoutEffect(() => {
    const measure = () => {
      const b = box.current, t = text.current
      if (!b || !t) return
      const cs = getComputedStyle(b)
      const room = b.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
      setShift(Math.max(0, Math.ceil(t.offsetWidth - room)))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(text.current)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    const b = box.current, t = text.current
    if (!shift || !b || !t || prefersReducedMotion()) return
    const hold = SCROLL_HOLD_MS
    const go = (shift / SCROLL_PX_PER_S) * 1000
    const fade = Math.min(SCROLL_FADE_MS, go / 2)
    const end = hold + go
    const back = end + hold
    const total = back + SCROLL_RETURN_MS
    const at = (ms) => ms / total
    const opts = { duration: total, iterations: Infinity }
    const x = (px) => ({ transform: `translateX(${px}px)` })
    const anims = [
      t.animate([
        { offset: 0, ...x(0) },
        { offset: at(hold), ...x(0), easing: 'ease-in-out' },
        { offset: at(end), ...x(-shift) },
        { offset: at(back), ...x(-shift), easing: 'cubic-bezier(0.65, 0, 0.35, 1)' },
        { offset: 1, ...x(0) },
      ], opts),
      b.animate([
        { offset: 0, '--gr-fade-l': '0px' },
        { offset: at(hold), '--gr-fade-l': '0px' },
        { offset: at(hold + fade), '--gr-fade-l': SCROLL_FADE },
        { offset: at(back), '--gr-fade-l': SCROLL_FADE },
        { offset: 1, '--gr-fade-l': '0px' },
      ], opts),
      b.animate([
        { offset: 0, '--gr-fade-r': SCROLL_FADE },
        { offset: at(end - fade), '--gr-fade-r': SCROLL_FADE },
        { offset: at(end), '--gr-fade-r': '0px' },
        { offset: at(back), '--gr-fade-r': '0px' },
        { offset: 1, '--gr-fade-r': SCROLL_FADE },
      ], opts),
    ]
    const stop = watchVisibility(b, (visible) => anims.forEach((a) => (visible ? a.play() : a.pause())))
    return () => {
      stop()
      anims.forEach((a) => a.cancel())
    }
  }, [shift])

  return (
    <div ref={box} className={`gr-scroll ${className}${shift ? ' is-scrolling' : ''}`}>
      <span ref={text} className="gr-scroll-text">{children}</span>
    </div>
  )
}
