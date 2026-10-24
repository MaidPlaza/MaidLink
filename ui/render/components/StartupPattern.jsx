import React, { useEffect, useRef } from 'react'
import {
  PATTERN_WIDTH, PATTERN_HEIGHT, DOT_CAPACITY, DOT_STRIDE, computeDots, drawStartupPattern,
} from '../utils/startupPattern'

const FRAME_MS = 1000 / 30

const VERT = `
attribute vec2 a_pos;
attribute float a_r;
attribute float a_edge;
uniform vec2 u_res;
uniform float u_dpr;
varying float v_r;
varying float v_size;
varying float v_edge;
void main() {
  gl_Position = vec4(a_pos.x / u_res.x * 2.0 - 1.0, 1.0 - a_pos.y / u_res.y * 2.0, 0.0, 1.0);
  v_size = (a_r * 2.0 + 2.0) * u_dpr;
  v_r = a_r * u_dpr;
  v_edge = a_edge;
  gl_PointSize = v_size;
}`

const FRAG = `
precision mediump float;
uniform vec4 u_top;
uniform vec4 u_bottom;
varying float v_r;
varying float v_size;
varying float v_edge;
void main() {
  float d = length(gl_PointCoord - 0.5) * v_size;
  float a = clamp(v_r - d + 0.5, 0.0, 1.0);
  if (a <= 0.0) discard;
  gl_FragColor = mix(u_top, u_bottom, v_edge) * a;
}`

function premultiplied(css) {
  const c = document.createElement('canvas')
  c.width = c.height = 1
  const x = c.getContext('2d')
  x.fillStyle = css || 'transparent'
  x.fillRect(0, 0, 1, 1)
  const [r, g, b, a] = x.getImageData(0, 0, 1, 1).data
  const k = a / 255
  return [r / 255 * k, g / 255 * k, b / 255 * k, k]
}

function compile(gl, type, src) {
  const s = gl.createShader(type)
  gl.shaderSource(s, src)
  gl.compileShader(s)
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    console.warn('[startup-pattern] шейдер:', gl.getShaderInfoLog(s))
    return null
  }
  return s
}

function makeGlRenderer(canvas, dpr, topCss, bottomCss) {
  const gl = canvas.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: false })
  if (!gl) return null
  const ext = gl.getExtension('EXT_blend_minmax')
  if (!ext) return null
  const vs = compile(gl, gl.VERTEX_SHADER, VERT)
  const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG)
  if (!vs || !fs) return null
  const prog = gl.createProgram()
  gl.attachShader(prog, vs)
  gl.attachShader(prog, fs)
  gl.linkProgram(prog)
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null
  gl.useProgram(prog)

  const dots = new Float32Array(DOT_CAPACITY * DOT_STRIDE)
  const buf = gl.createBuffer()
  gl.bindBuffer(gl.ARRAY_BUFFER, buf)
  gl.bufferData(gl.ARRAY_BUFFER, dots.byteLength, gl.DYNAMIC_DRAW)
  const bytes = DOT_STRIDE * 4
  for (const [name, size, offset] of [['a_pos', 2, 0], ['a_r', 1, 8], ['a_edge', 1, 12]]) {
    const loc = gl.getAttribLocation(prog, name)
    gl.enableVertexAttribArray(loc)
    gl.vertexAttribPointer(loc, size, gl.FLOAT, false, bytes, offset)
  }
  gl.uniform2f(gl.getUniformLocation(prog, 'u_res'), PATTERN_WIDTH, PATTERN_HEIGHT)
  gl.uniform1f(gl.getUniformLocation(prog, 'u_dpr'), dpr)
  gl.uniform4fv(gl.getUniformLocation(prog, 'u_top'), premultiplied(topCss))
  gl.uniform4fv(gl.getUniformLocation(prog, 'u_bottom'), premultiplied(bottomCss))
  gl.enable(gl.BLEND)
  gl.blendEquation(ext.MAX_EXT)
  gl.blendFunc(gl.ONE, gl.ONE)
  gl.viewport(0, 0, canvas.width, canvas.height)
  gl.clearColor(0, 0, 0, 0)

  return (t) => {
    if (gl.isContextLost()) return
    const n = computeDots(t, dots)
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, dots.subarray(0, n * DOT_STRIDE))
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.drawArrays(gl.POINTS, 0, n)
  }
}

export default function StartupPattern() {
  const ref = useRef(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return undefined
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.round(PATTERN_WIDTH * dpr)
    canvas.height = Math.round(PATTERN_HEIGHT * dpr)
    const css = getComputedStyle(canvas)
    const top = css.getPropertyValue('--app-window-startup-pattern-top-color').trim()
    const bottom = css.getPropertyValue('--app-window-startup-pattern-bottom-color').trim()

    const draw = makeGlRenderer(canvas, dpr, top, bottom)
    if (!draw) {
      console.warn('[startup-pattern] WebGL недоступен → неподвижный кадр')
      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        drawStartupPattern(ctx, 0, top, bottom)
      }
      return undefined
    }
    draw(0)
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined

    let raf = 0
    let last = -Infinity
    const t0 = performance.now()
    const frame = (now) => {
      raf = requestAnimationFrame(frame)
      if (now - last < FRAME_MS) return
      last = now
      draw((now - t0) / 1000)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [])

  return <canvas ref={ref} className="startup-chip-insertion-pattern" aria-hidden="true" />
}
