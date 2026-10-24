import React, { useEffect, useRef } from 'react'

const VERT = `
attribute vec2 aPos;
uniform vec4 uRect;
uniform vec2 uRes;
varying vec2 vUv;
void main() {
  vec2 px = uRect.xy + aPos * uRect.zw;
  vec2 clip = vec2(px.x / uRes.x * 2.0 - 1.0, 1.0 - px.y / uRes.y * 2.0);
  vUv = vec2(aPos.x, aPos.y);
  gl_Position = vec4(clip, 0.0, 1.0);
}`

const FRAG_HEAD = `
precision mediump float;
#define PI 3.14159265
varying vec2 vUv;
uniform sampler2D uTex;
uniform float uTime;
uniform vec3 uColor;
uniform vec4 uTexRect;
vec4 sampleText(vec2 quv) {
  vec2 t = (quv - uTexRect.xy) / uTexRect.zw;
  if (t.x < 0.0 || t.x > 1.0 || t.y < 0.0 || t.y > 1.0) return vec4(0.0);
  return texture2D(uTex, t);
}
`

const FRAGS = {
  passthrough: FRAG_HEAD + `
    void main() { gl_FragColor = sampleText(vUv); }`,

  warp: FRAG_HEAD + `
    void main() {
      vec2 uv = vUv;
      uv.x += sin(uv.y * 26.0 + uTime * 6.0) * 0.05;
      uv.y += cos(uv.x * 20.0 + uTime * 5.0) * 0.05;
      gl_FragColor = sampleText(uv);
    }`,

  glow: FRAG_HEAD + `
    void main() {
      vec4 c = sampleText(vUv);
      float t = 0.5 + 0.5 * sin(uTime * 4.0);
      float d = 0.02;
      float halo =
          sampleText(vUv + vec2( d, 0.0)).a
        + sampleText(vUv + vec2(-d, 0.0)).a
        + sampleText(vUv + vec2(0.0,  d)).a
        + sampleText(vUv + vec2(0.0, -d)).a
        + sampleText(vUv + vec2( d,  d)).a
        + sampleText(vUv + vec2(-d, -d)).a;
      halo *= (0.3 + 0.7 * t) / 6.0;
      gl_FragColor = vec4(uColor, max(c.a, halo));
    }`,

  action: FRAG_HEAD + `
    float hash(float n) { return fract(sin(n) * 43758.5453); }
    void main() {
      vec2 p = vUv - 0.5;
      float ang = atan(p.y, p.x);
      float rad = length(p) * 2.0;
      float COUNT = 42.0;
      float wc = fract((ang / (2.0 * PI) + 0.5) * COUNT);
      float idx = floor((ang / (2.0 * PI) + 0.5) * COUNT);
      float rnd = hash(idx);
      float line = smoothstep(0.82, 1.0, abs(wc - 0.5) * 2.0);
      float len = 0.45 + 0.55 * fract(rnd + floor(uTime * (6.0 + rnd * 8.0)) * 0.17);
      float radMask = smoothstep(0.28, 0.5, rad) * (1.0 - smoothstep(len, len + 0.12, rad));
      float linesA = line * radMask;
      vec4 tex = sampleText(vUv);
      vec3 col = mix(uColor, tex.rgb, tex.a);
      float a = max(linesA * 0.85, tex.a);
      gl_FragColor = vec4(col, a);
    }`,
}

function compile(gl, type, src) {
  const sh = gl.createShader(type)
  gl.shaderSource(sh, src)
  gl.compileShader(sh)
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.warn('[shader-text] compile:', gl.getShaderInfoLog(sh))
    gl.deleteShader(sh)
    return null
  }
  return sh
}

function makeProgram(gl, frag) {
  const vs = compile(gl, gl.VERTEX_SHADER, VERT)
  const fs = compile(gl, gl.FRAGMENT_SHADER, frag)
  if (!vs || !fs) return null
  const p = gl.createProgram()
  gl.attachShader(p, vs); gl.attachShader(p, fs); gl.linkProgram(p)
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    console.warn('[shader-text] link:', gl.getProgramInfoLog(p))
    return null
  }
  return {
    program: p,
    aPos: gl.getAttribLocation(p, 'aPos'),
    uRect: gl.getUniformLocation(p, 'uRect'),
    uRes: gl.getUniformLocation(p, 'uRes'),
    uTex: gl.getUniformLocation(p, 'uTex'),
    uTime: gl.getUniformLocation(p, 'uTime'),
    uColor: gl.getUniformLocation(p, 'uColor'),
    uTexRect: gl.getUniformLocation(p, 'uTexRect'),
  }
}

const SHAKE_AMP = 0.7
const SHAKE_RATE = 14
const SHAKE_BOLD = 0.4
function frnd(n) {
  const s = Math.sin(n * 12.9898) * 43758.5453
  return s - Math.floor(s)
}

const BLACK = { css: '#000000', rgb: [0, 0, 0] }

export default function ShaderTextLayer({ scrollRef }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const scroller = scrollRef?.current
    if (!canvas || !scroller) return

    const gl = canvas.getContext('webgl', { premultipliedAlpha: false, alpha: true })
    if (!gl) { console.warn('[shader-text] WebGL недоступен → фолбэк на цветной текст'); return }

    console.info('[shader-text] активен')
    scroller.setAttribute('data-rich-shader', '')

    const quad = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, quad)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW)

    gl.enable(gl.BLEND)
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)

    const programs = {}
    const getProgram = (effect) => {
      const name = FRAGS[effect] ? effect : 'passthrough'
      if (!programs[name]) programs[name] = makeProgram(gl, FRAGS[name])
      return programs[name] || null
    }

    const cache = new Map()
    const raster = document.createElement('canvas')
    const rctx = raster.getContext('2d')
    const range = document.createRange()

    function makeTexture(text, font, color, w, h, dpr, bold = false) {
      const key = `${text}|${font}|${color}|${Math.round(w)}|${Math.round(h)}|${dpr}|${bold ? 1 : 0}`
      const hit = cache.get(key)
      if (hit) { hit.seen = true; return hit }

      const pw = Math.max(1, Math.round(w * dpr))
      const ph = Math.max(1, Math.round(h * dpr))
      raster.width = pw; raster.height = ph
      rctx.clearRect(0, 0, pw, ph)
      rctx.scale(dpr, dpr)
      rctx.font = font
      rctx.fillStyle = color
      rctx.textBaseline = 'middle'
      rctx.textAlign = 'left'
      rctx.fillText(text, 0, h / 2)
      if (bold) {
        rctx.lineWidth = SHAKE_BOLD
        rctx.strokeStyle = color
        rctx.lineJoin = 'round'
        rctx.strokeText(text, 0, h / 2)
      }
      rctx.setTransform(1, 0, 0, 1, 0, 0)

      const tex = gl.createTexture()
      gl.bindTexture(gl.TEXTURE_2D, tex)
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, raster)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)

      const entry = { tex, seen: true }
      cache.set(key, entry)
      return entry
    }

    const swatch = document.createElement('canvas')
    swatch.width = swatch.height = 1
    const sctx = swatch.getContext('2d', { willReadFrequently: true })
    const colors = new Map()
    function parseCssColor(value) {
      if (colors.has(value)) return colors.get(value)
      sctx.fillStyle = '#000000'; sctx.fillStyle = value
      const probe = sctx.fillStyle
      sctx.fillStyle = '#ffffff'; sctx.fillStyle = value
      let out = null
      if (value && sctx.fillStyle === probe) {
        sctx.clearRect(0, 0, 1, 1)
        sctx.fillRect(0, 0, 1, 1)
        const [r, g, b, a] = sctx.getImageData(0, 0, 1, 1).data
        out = { css: `rgba(${r}, ${g}, ${b}, ${a / 255})`, rgb: [r / 255, g / 255, b / 255] }
      }
      if (colors.size > 64) colors.clear()
      colors.set(value, out)
      return out
    }

    function spanFontColor(span) {
      const cs = getComputedStyle(span)
      const parent = span.parentElement
      const color = parseCssColor(cs.getPropertyValue('--fx-color').trim())
        || (parent && parseCssColor(getComputedStyle(parent).color))
        || BLACK
      return {
        font: cs.font || `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`,
        color: color.css,
        rgb: color.rgb,
      }
    }

    let raf = 0
    const t0 = performance.now()
    let dbgSpans = -1
    let dbgErr = false

    function frame() {
      const dpr = window.devicePixelRatio || 1
      const box = canvas.getBoundingClientRect()
      const cw = Math.max(1, Math.round(box.width * dpr))
      const ch = Math.max(1, Math.round(box.height * dpr))
      if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch }

      gl.viewport(0, 0, cw, ch)
      gl.clearColor(0, 0, 0, 0)
      gl.clear(gl.COLOR_BUFFER_BIT)

      const time = (performance.now() - t0) / 1000
      const spans = scroller.querySelectorAll('.rich-fx[data-effect]')

      if (spans.length !== dbgSpans) {
        dbgSpans = spans.length
        console.info(`[shader-text] спанов: ${spans.length}; канвас ${Math.round(box.width)}x${Math.round(box.height)} @${dpr}x`)
      }

      for (const key of cache.keys()) cache.get(key).seen = false

      try {
      spans.forEach((span) => {
        const r = span.getBoundingClientRect()
        if (r.width < 1 || r.height < 1) return

        const effect = span.getAttribute('data-effect')

        const node = span.firstChild
        if (effect === 'shake' && node && node.nodeType === 3) {
          const prog = getProgram('passthrough')
          if (!prog) return
          const { font, color } = spanFontColor(span)
          const s = node.nodeValue
          const slot = Math.floor(time * SHAKE_RATE)
          gl.useProgram(prog.program)
          gl.bindBuffer(gl.ARRAY_BUFFER, quad)
          gl.enableVertexAttribArray(prog.aPos)
          gl.vertexAttribPointer(prog.aPos, 2, gl.FLOAT, false, 0, 0)
          gl.uniform2f(prog.uRes, cw, ch)
          gl.uniform1f(prog.uTime, time)
          gl.uniform4f(prog.uTexRect, 0, 0, 1, 1)
          for (let i = 0; i < s.length; i++) {
            const chr = s[i]
            if (chr === ' ' || chr === '\n' || chr === '\t') continue
            range.setStart(node, i); range.setEnd(node, i + 1)
            const cr = range.getBoundingClientRect()
            if (cr.width < 0.5 || cr.height < 0.5) continue
            if (cr.bottom < box.top - 40 || cr.top > box.bottom + 40) continue
            const t = makeTexture(chr, font, color, cr.width, cr.height, dpr, true)
            const ox = (frnd(i * 1.37 + slot * 0.7) * 2 - 1) * SHAKE_AMP
            const oy = (frnd(i * 2.53 + slot * 1.3 + 11.1) * 2 - 1) * SHAKE_AMP
            gl.uniform4f(prog.uRect, (cr.left + ox - box.left) * dpr, (cr.top + oy - box.top) * dpr, cr.width * dpr, cr.height * dpr)
            gl.activeTexture(gl.TEXTURE0)
            gl.bindTexture(gl.TEXTURE_2D, t.tex)
            gl.uniform1i(prog.uTex, 0)
            gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
          }
          return
        }
        const pad = effect === 'action' ? r.height * 0.9 : 0
        const dx = r.left - pad
        const dy = r.top - pad
        const dw = r.width + pad * 2
        const dh = r.height + pad * 2
        if (dy + dh < box.top - 40 || dy > box.bottom + 40) return

        const prog = getProgram(effect)
        if (!prog) return

        const { font, color, rgb } = spanFontColor(span)
        const t = makeTexture(span.textContent || '', font, color, r.width, r.height, dpr)
        const x = (dx - box.left) * dpr
        const y = (dy - box.top) * dpr
        const w = dw * dpr
        const h = dh * dpr
        const [cr, cg, cb] = rgb

        gl.useProgram(prog.program)
        gl.bindBuffer(gl.ARRAY_BUFFER, quad)
        gl.enableVertexAttribArray(prog.aPos)
        gl.vertexAttribPointer(prog.aPos, 2, gl.FLOAT, false, 0, 0)
        gl.uniform4f(prog.uRect, x, y, w, h)
        gl.uniform2f(prog.uRes, cw, ch)
        gl.uniform1f(prog.uTime, time)
        gl.uniform3f(prog.uColor, cr, cg, cb)
        gl.uniform4f(prog.uTexRect, pad / dw, pad / dh, r.width / dw, r.height / dh)
        gl.activeTexture(gl.TEXTURE0)
        gl.bindTexture(gl.TEXTURE_2D, t.tex)
        gl.uniform1i(prog.uTex, 0)
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
      })
      } catch (e) {
        if (!dbgErr) { dbgErr = true; console.error('[shader-text] ошибка в кадре:', e) }
      }

      for (const [key, entry] of cache) {
        if (!entry.seen) { gl.deleteTexture(entry.tex); cache.delete(key) }
      }

      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(raf)
      scroller.removeAttribute('data-rich-shader')
      for (const [, entry] of cache) gl.deleteTexture(entry.tex)
      cache.clear()
    }
  }, [scrollRef])

  return <canvas ref={canvasRef} className="rich-shader-canvas" />
}
