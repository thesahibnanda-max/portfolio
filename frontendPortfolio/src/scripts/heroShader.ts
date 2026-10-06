const VERTEX = `
attribute vec2 position;
attribute vec2 uv;
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const FRAGMENT = `
precision highp float;
varying vec2 vUv;
uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uPointer;
uniform float uPointerStrength;

vec3 permute(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }

float snoise(vec2 v) {
  const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
  vec2 i = floor(v + dot(v, C.yy));
  vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod(i, 289.0);
  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
  vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
  m = m * m;
  m = m * m;
  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5);
  vec3 a0 = x - ox;
  m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
  vec3 g;
  g.x = a0.x * x0.x + h.x * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}

float fbm(vec2 p) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 4; i++) {
    value += amplitude * snoise(p);
    p = p * 2.03 + vec2(17.0, 9.0);
    amplitude *= 0.5;
  }
  return value;
}

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

void main() {
  vec2 aspect = vec2(uResolution.x / uResolution.y, 1.0);
  vec2 p = vUv * aspect * 0.55;
  vec2 pointer = uPointer * aspect * 0.55;
  float t = uTime * 0.018;

  vec2 toPointer = p - pointer;
  float pull = exp(-dot(toPointer, toPointer) * 18.0) * uPointerStrength;
  p += normalize(toPointer + 1e-4) * pull * 0.06;

  vec2 q = vec2(fbm(p + vec2(0.0, t)), fbm(p + vec2(5.2, 1.3) - t));
  vec2 r = vec2(fbm(p + 1.6 * q + vec2(1.7, 9.2) + t * 1.2), fbm(p + 1.6 * q + vec2(8.3, 2.8) - t));
  float field = fbm(p + 1.8 * r);

  float bands = abs(fract(field * 4.0 + t * 1.5) - 0.5);
  float lines = smoothstep(0.035, 0.0, bands) * 0.9;
  float glow = smoothstep(-0.2, 0.9, field);

  vec3 base = vec3(0.043, 0.043, 0.047);
  vec3 ember = vec3(0.96, 0.647, 0.141);
  vec3 deep = vec3(0.24, 0.12, 0.03);

  vec3 color = base;
  color = mix(color, deep, glow * 0.6);
  color = mix(color, ember, pow(glow, 4.0) * 0.32);
  color += ember * lines * (0.08 + glow * 0.22);
  color += ember * pull * 0.05;

  float rightBias = smoothstep(0.05, 0.85, vUv.x);
  float vignette = smoothstep(1.15, 0.2, length((vUv - vec2(0.72, 0.6)) * vec2(1.0, 1.35)));
  color = mix(base, color, vignette * mix(0.35, 1.0, rightBias));

  color += (hash(vUv * uResolution + fract(uTime)) - 0.5) * 0.03;
  gl_FragColor = vec4(color, 1.0);
}
`;

const MAX_DPR = 1.25;
const SOFTWARE_RENDERER = /swiftshader|llvmpipe|softpipe|software|basic render/i;

const SLOW_FRAME_MS = 34;
const FRAMES_TO_SAMPLE = 30;
const REDUCED_DPR_SCALE = 0.5;

export function startHeroShader(canvas: HTMLCanvasElement): void {
  const begin = (): void => {
    void mountShader(canvas).catch((error: unknown) => {
      console.warn("Hero shader unavailable; showing the static gradient", error);
    });
  };
  const whenIdle = (): void => {
    if (typeof window.requestIdleCallback === "function") {
      window.requestIdleCallback(begin);
    } else {
      window.setTimeout(begin, 300);
    }
  };
  if (document.readyState === "complete") {
    whenIdle();
  } else {
    window.addEventListener("load", whenIdle, { once: true });
  }
}

async function mountShader(canvas: HTMLCanvasElement): Promise<void> {
  const { Renderer, Program, Mesh, Triangle } = await import("ogl");
  const baseDpr = Math.min(window.devicePixelRatio, MAX_DPR) * 0.75;
  const renderer = new Renderer({ canvas, dpr: baseDpr, alpha: false });
  const gl = renderer.gl;
  const software = isSoftwareRenderer(gl);
  if (software) {
    renderer.dpr = baseDpr * REDUCED_DPR_SCALE;
  }

  const uniforms = {
    uTime: { value: 0 },
    uResolution: { value: [1, 1] as [number, number] },
    uPointer: { value: [0.62, 0.55] as [number, number] },
    uPointerStrength: { value: 0 },
  };
  const program = new Program(gl, { vertex: VERTEX, fragment: FRAGMENT, uniforms });
  const mesh = new Mesh(gl, { geometry: new Triangle(gl), program });

  const host = canvas.parentElement ?? document.body;
  const resize = (): void => {
    renderer.setSize(host.clientWidth, host.clientHeight);
    uniforms.uResolution.value = [gl.canvas.width, gl.canvas.height];
  };
  resize();
  new ResizeObserver(resize).observe(host);

  const target = { x: 0.62, y: 0.55, strength: 0 };
  host.addEventListener("pointermove", (event) => {
    const rect = canvas.getBoundingClientRect();
    target.x = (event.clientX - rect.left) / rect.width;
    target.y = 1 - (event.clientY - rect.top) / rect.height;
    target.strength = 1;
  });
  host.addEventListener("pointerleave", () => {
    target.strength = 0;
  });

  canvas.classList.add("opacity-0", "transition-opacity", "duration-[2000ms]");
  let visible = true;
  let frameId = 0;
  let sampled = 0;
  let lastFrameAt = 0;
  let slowFrames = 0;
  let degraded = software;
  const startedAt = performance.now();
  const adapt = (now: number): boolean => {
    if (lastFrameAt !== 0 && sampled < FRAMES_TO_SAMPLE) {
      sampled += 1;
      if (now - lastFrameAt > SLOW_FRAME_MS) {
        slowFrames += 1;
      }
      if (sampled === FRAMES_TO_SAMPLE && slowFrames > FRAMES_TO_SAMPLE / 2) {
        if (degraded) {
          return false;
        }
        degraded = true;
        renderer.dpr = baseDpr * REDUCED_DPR_SCALE;
        resize();
        sampled = 0;
        slowFrames = 0;
      }
    }
    lastFrameAt = now;
    return true;
  };
  const frame = (now: number): void => {
    if (!adapt(now)) {
      frameId = 0;
      return;
    }
    const [x, y] = uniforms.uPointer.value;
    uniforms.uPointer.value = [x + (target.x - x) * 0.05, y + (target.y - y) * 0.05];
    uniforms.uPointerStrength.value += (target.strength - uniforms.uPointerStrength.value) * 0.04;
    uniforms.uTime.value = (now - startedAt) / 1000 + 40;
    renderer.render({ scene: mesh });
    frameId = requestAnimationFrame(frame);
  };
  const play = (): void => {
    if (frameId === 0 && visible && document.visibilityState === "visible") {
      frameId = requestAnimationFrame(frame);
    }
  };
  const pause = (): void => {
    cancelAnimationFrame(frameId);
    frameId = 0;
  };

  new IntersectionObserver((entries) => {
    visible = entries.some((entry) => entry.isIntersecting);
    if (visible) {
      play();
    } else {
      pause();
    }
  }).observe(canvas);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      play();
    } else {
      pause();
    }
  });

  play();
  requestAnimationFrame(() => canvas.classList.remove("opacity-0"));
}

export function isSoftwareRenderer(gl: WebGLRenderingContext | WebGL2RenderingContext): boolean {
  const info = gl.getExtension("WEBGL_debug_renderer_info");
  const renderer = info === null ? gl.getParameter(gl.RENDERER) : gl.getParameter(info.UNMASKED_RENDERER_WEBGL);
  return typeof renderer === "string" && SOFTWARE_RENDERER.test(renderer);
}
