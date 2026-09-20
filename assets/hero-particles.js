(() => {
  'use strict';

  const canvas = document.getElementById('hero-particles');
  const stage = canvas && canvas.closest('.hero-stage');
  if (!canvas || !stage) return;
  const art = stage.querySelector('.hero-stage-background img');
  const artPicture = stage.querySelector('.hero-stage-background picture');

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (reduceMotion.matches) {
    canvas.hidden = true;
    return;
  }

  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;

  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const state = {
    width: 1,
    height: 1,
    dpr: 1,
    visible: true,
    running: true,
    last: performance.now(),
    mouseX: 0.5,
    mouseY: 0.5,
    mouseActive: false,
    particles: [],
    pulses: [],
  };

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const lerp = (a, b, t) => a + (b - a) * t;

  function artPlacement() {
    const iw = (art && art.naturalWidth) || 1662;
    const ih = (art && art.naturalHeight) || 936;
    let boxX = 0;
    let boxY = 0;
    let boxW = state.width;
    let boxH = state.height;

    if (artPicture) {
      const stageRect = stage.getBoundingClientRect();
      const r = artPicture.getBoundingClientRect();
      boxX = r.left - stageRect.left;
      boxY = r.top - stageRect.top;
      boxW = r.width || state.width;
      boxH = r.height || state.height;
    }

    const fit = art ? getComputedStyle(art).objectFit : 'contain';
    const scale = fit === 'cover'
      ? Math.max(boxW / iw, boxH / ih)
      : Math.min(boxW / iw, boxH / ih);
    const w = iw * scale;
    const h = ih * scale;
    const centerX = boxX + (boxW - w) / 2;
    const centerY = fit === 'cover' ? boxY + (boxH - h) / 2 : boxY;
    return { x: centerX, y: centerY, width: w, height: h };
  }

  function mapArt(u, v) {
    const r = artPlacement();
    return { x: r.x + u * r.width, y: r.y + v * r.height };
  }

  function drawGridGlow(now) {
    const r = artPlacement();
    const left = r.x;
    const top = r.y;
    const right = r.x + r.width * 0.405;
    const bottom = r.y + r.height * 0.635;
    if (right <= 0 || bottom <= 0 || left >= state.width || top >= state.height) return;

    const t = now * 0.001;
    ctx.save();
    ctx.globalAlpha = state.width < 680 ? 0.55 : 1;
    ctx.beginPath();
    ctx.rect(left, top, right - left, bottom - top);
    ctx.clip();

    // Faint reinforcement of the source grid. A slow diagonal reflection passes
    // through it rather than making the entire matrix pulse at once.
    ctx.lineWidth = 0.55;
    const cols = 12;
    const rows = 12;
    for (let i = 0; i <= cols; i++) {
      const x = lerp(left, right, i / cols);
      const alpha = 0.030 + 0.034 * (0.5 + 0.5 * Math.sin(t * 0.42 + i * 0.55));
      ctx.strokeStyle = `rgba(101, 208, 255, ${alpha})`;
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.stroke();
    }
    for (let i = 0; i <= rows; i++) {
      const y = lerp(top, bottom, i / rows);
      const alpha = 0.024 + 0.030 * (0.5 + 0.5 * Math.sin(t * 0.38 + i * 0.48 + 1.1));
      ctx.strokeStyle = `rgba(101, 208, 255, ${alpha})`;
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.stroke();
    }

    const sweep = ((t * 0.045) % 1.35) - 0.20;
    const bandX = lerp(left, right, sweep);
    const bandW = Math.max(90, r.width * 0.105);
    const grad = ctx.createLinearGradient(bandX - bandW, bottom, bandX + bandW, top);
    grad.addColorStop(0, 'rgba(86, 212, 255, 0)');
    grad.addColorStop(0.42, 'rgba(86, 212, 255, 0.035)');
    grad.addColorStop(0.52, 'rgba(150, 236, 255, 0.18)');
    grad.addColorStop(0.62, 'rgba(86, 212, 255, 0.045)');
    grad.addColorStop(1, 'rgba(86, 212, 255, 0)');
    ctx.fillStyle = grad;
    ctx.fillRect(left, top, right - left, bottom - top);

    // The source artwork contains a pixel/square field in the lower-left.  Let a
    // handful of those cells catch the same slow reflection so the shimmer reads
    // as part of the image rather than as a generic grid overlay.
    const cellLeft = r.x + r.width * 0.005;
    const cellTop = r.y + r.height * 0.275;
    const cellW = r.width * 0.245;
    const cellH = r.height * 0.305;
    const cellCols = 11;
    const cellRows = 8;
    const gap = Math.max(1.5, r.width * 0.0018);
    const cw = cellW / cellCols;
    const ch = cellH / cellRows;
    for (let row = 0; row < cellRows; row++) {
      for (let col = 0; col < cellCols; col++) {
        const wave = 0.5 + 0.5 * Math.sin(t * 0.72 - col * 0.44 + row * 0.31);
        const diagonal = ((col / cellCols) * 0.78 + (1 - row / cellRows) * 0.22);
        const sweepDist = Math.abs((((t * 0.055) % 1.45) - 0.18) - diagonal);
        const catchLight = Math.max(0, 1 - sweepDist / 0.18);
        const alpha = 0.008 + wave * 0.010 + catchLight * 0.12;
        if (alpha < 0.018) continue;
        ctx.fillStyle = `rgba(116, 224, 255, ${alpha})`;
        ctx.shadowColor = `rgba(72, 204, 255, ${catchLight * 0.18})`;
        ctx.shadowBlur = catchLight * 8;
        ctx.fillRect(cellLeft + col * cw + gap, cellTop + row * ch + gap,
          Math.max(1, cw - gap * 2), Math.max(1, ch - gap * 2));
      }
    }
    ctx.shadowBlur = 0;

    ctx.restore();
  }

  function isMobile() {
    return state.width < 760;
  }

  function curveSet() {
    if (isMobile()) {
      // Match the upward sweep already present in the artwork. On narrow screens
      // keep the streams in the upper/middle hero rather than through the full stack.
      return [
        [[-0.10, 0.61], [0.18, 0.54], [0.54, 0.38], [1.10, 0.21]],
        [[-0.12, 0.49], [0.22, 0.44], [0.60, 0.31], [1.08, 0.16]],
        [[0.00, 0.34], [0.30, 0.29], [0.67, 0.24], [1.05, 0.11]],
      ];
    }
    return [
      [[-0.08, 0.76], [0.18, 0.65], [0.48, 0.53], [1.08, 0.24]],
      [[-0.06, 0.63], [0.24, 0.53], [0.58, 0.42], [1.06, 0.18]],
      [[0.01, 0.43], [0.31, 0.36], [0.67, 0.30], [1.04, 0.12]],
    ];
  }

  function bezier(points, t) {
    const mt = 1 - t;
    const x = mt * mt * mt * points[0][0]
      + 3 * mt * mt * t * points[1][0]
      + 3 * mt * t * t * points[2][0]
      + t * t * t * points[3][0];
    const y = mt * mt * mt * points[0][1]
      + 3 * mt * mt * t * points[1][1]
      + 3 * mt * t * t * points[2][1]
      + t * t * t * points[3][1];
    return { x: x * state.width, y: y * state.height };
  }

  function tangent(points, t) {
    const e = 0.0025;
    const a = bezier(points, clamp(t - e, 0, 1));
    const b = bezier(points, clamp(t + e, 0, 1));
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    return { x: dx / len, y: dy / len };
  }

  class FlowParticle {
    constructor(i, count) {
      const paths = curveSet();
      this.path = i % paths.length;
      this.t = (i / count + Math.random() * 0.22) % 1;
      this.speed = (0.018 + Math.random() * 0.030) * (Math.random() < 0.13 ? 1.45 : 1);
      this.radius = 0.75 + Math.random() * 1.45;
      this.alpha = 0.16 + Math.random() * 0.44;
      this.phase = Math.random() * Math.PI * 2;
      this.jitter = 2 + Math.random() * 9;
      this.hue = Math.random() < 0.72 ? '92, 204, 255' : '185, 224, 255';
    }

    update(dt) {
      this.t = (this.t + this.speed * dt) % 1;
    }

    position() {
      const paths = curveSet();
      const path = paths[this.path % paths.length];
      const p = bezier(path, this.t);
      const tan = tangent(path, this.t);
      const nx = -tan.y;
      const ny = tan.x;
      const wave = Math.sin(this.phase + this.t * Math.PI * 5.5) * this.jitter;
      let x = p.x + nx * wave;
      let y = p.y + ny * wave;

      // Very small pointer-induced bend: never emit from or chase the pointer.
      if (finePointer && state.mouseActive) {
        const mx = state.mouseX * state.width;
        const my = state.mouseY * state.height;
        const dx = x - mx;
        const dy = y - my;
        const dist = Math.hypot(dx, dy);
        const radius = Math.min(190, state.width * 0.16);
        if (dist > 0 && dist < radius) {
          const force = (1 - dist / radius) * 11;
          x += (dx / dist) * force;
          y += (dy / dist) * force;
        }
      }
      return { x, y, tan };
    }

    draw() {
      const p = this.position();
      const tail = 7 + this.radius * 5;
      const tx = p.x - p.tan.x * tail;
      const ty = p.y - p.tan.y * tail;

      const grad = ctx.createLinearGradient(tx, ty, p.x, p.y);
      grad.addColorStop(0, `rgba(${this.hue}, 0)`);
      grad.addColorStop(1, `rgba(${this.hue}, ${this.alpha * 0.65})`);
      ctx.strokeStyle = grad;
      ctx.lineWidth = Math.max(0.55, this.radius * 0.6);
      ctx.beginPath();
      ctx.moveTo(tx, ty);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();

      ctx.fillStyle = `rgba(${this.hue}, ${this.alpha})`;
      ctx.shadowColor = `rgba(${this.hue}, ${this.alpha * 0.9})`;
      ctx.shadowBlur = 5 + this.radius * 3;
      ctx.beginPath();
      ctx.arc(p.x, p.y, this.radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  class Pulse {
    constructor(offset, path) {
      this.t = offset;
      this.path = path;
      this.speed = 0.030 + Math.random() * 0.010;
      this.size = 10 + Math.floor(Math.random() * 5);
    }

    update(dt) {
      this.t = (this.t + this.speed * dt) % 1;
    }

    draw() {
      const paths = curveSet();
      const path = paths[this.path % paths.length];
      for (let i = 0; i < this.size; i++) {
        const spread = (i - this.size / 2) * 0.0042;
        const t = (this.t + spread + 1) % 1;
        const p = bezier(path, t);
        const tan = tangent(path, t);
        const nx = -tan.y;
        const ny = tan.x;
        const lateral = Math.sin(i * 2.17 + this.t * 12) * (2 + (i % 3) * 2.2);
        const fade = 1 - Math.abs(i - this.size / 2) / (this.size / 2);
        const alpha = 0.13 + fade * 0.52;
        const r = 0.8 + fade * 1.8;
        const x = p.x + nx * lateral;
        const y = p.y + ny * lateral;
        ctx.fillStyle = `rgba(171, 230, 255, ${alpha})`;
        ctx.shadowColor = `rgba(96, 209, 255, ${alpha})`;
        ctx.shadowBlur = 10;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.shadowBlur = 0;
    }
  }


  function drawNetworkGlow(now) {
    // Trace the visible network on the far-right of the source artwork. These
    // coordinates are normalized to the image itself (not the viewport), so the
    // glow stays attached to the graph as object-fit changes with browser size.
    const nodes = [
      [0.929, 0.125], // 0 top
      [0.858, 0.204], // 1 upper-left
      [0.961, 0.261], // 2 upper-right
      [0.994, 0.342], // 3 far-right upper
      [0.882, 0.349], // 4 upper-middle-left
      [0.955, 0.353], // 5 upper-middle-right
      [0.807, 0.440], // 6 left shoulder
      [0.888, 0.444], // 7 central junction
      [0.904, 0.522], // 8 central lower
      [0.923, 0.575], // 9 right-center
      [0.879, 0.624], // 10 lower-left junction
      [0.891, 0.641], // 11 nearby cyan node
      [0.819, 0.804], // 12 lower-left outer
      [0.931, 0.744], // 13 lower-mid
      [0.965, 0.754], // 14 lower-right
      [0.973, 0.811], // 15 lower-right junction
      [0.965, 0.885], // 16 bottom-mid
      [0.981, 0.928]  // 17 bottom-right
    ];
    const edges = [
      [0,1],[0,2],[1,4],[1,7],[2,4],[2,5],[2,3],[3,5],
      [4,5],[4,7],[5,7],[5,3],[6,7],[6,10],[7,8],[7,9],
      [7,10],[8,9],[8,10],[9,10],[9,13],[10,11],[10,12],
      [11,12],[11,13],[12,13],[13,14],[14,15],[15,16],[15,17],[16,17]
    ];
    const pts = nodes.map(([u, v]) => mapArt(u, v));
    const t = now * 0.001;
    const mobileScale = state.width < 680 ? 0.78 : 1;

    ctx.save();
    ctx.globalAlpha = mobileScale;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // Persistent low-level reinforcement makes the network visibly "alive"
    // before a traveling shimmer reaches an edge.
    for (let i = 0; i < edges.length; i++) {
      const [a, b] = edges[i];
      const na = pts[a];
      const nb = pts[b];
      const breathe = 0.5 + 0.5 * Math.sin(t * 0.62 + i * 0.47);
      const alpha = 0.12 + breathe * 0.13;
      ctx.strokeStyle = `rgba(98, 211, 255, ${alpha})`;
      ctx.lineWidth = 0.85 + breathe * 0.42;
      ctx.shadowColor = `rgba(76, 202, 255, ${0.14 + breathe * 0.12})`;
      ctx.shadowBlur = 4 + breathe * 5;
      ctx.beginPath();
      ctx.moveTo(na.x, na.y);
      ctx.lineTo(nb.x, nb.y);
      ctx.stroke();
    }

    // Nodes pulse independently, with a soft outer halo and a brighter core.
    for (let i = 0; i < pts.length; i++) {
      const n = pts[i];
      const pulse = 0.5 + 0.5 * Math.sin(t * 1.05 + i * 0.79);
      const haloR = 4.5 + pulse * 4.0;
      const halo = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, haloR);
      halo.addColorStop(0, `rgba(151, 235, 255, ${0.30 + pulse * 0.22})`);
      halo.addColorStop(0.34, `rgba(94, 216, 255, ${0.17 + pulse * 0.14})`);
      halo.addColorStop(1, 'rgba(74, 202, 255, 0)');
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(n.x, n.y, haloR, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = `rgba(177, 241, 255, ${0.46 + pulse * 0.34})`;
      ctx.shadowColor = `rgba(94, 217, 255, ${0.58 + pulse * 0.26})`;
      ctx.shadowBlur = 9 + pulse * 7;
      ctx.beginPath();
      ctx.arc(n.x, n.y, 1.35 + pulse * 1.0, 0, Math.PI * 2);
      ctx.fill();
    }

    // A short luminous segment travels edge-to-edge around the graph. This reads
    // as a line shimmer rather than a detached dot moving over the illustration.
    function traceEdge(edgeIndex, progress, alpha = 0.9) {
      const [aIdx, bIdx] = edges[edgeIndex % edges.length];
      const a = pts[aIdx];
      const b = pts[bIdx];
      const head = clamp(progress, 0, 1);
      const tail = clamp(head - 0.22, 0, 1);
      const x1 = lerp(a.x, b.x, tail);
      const y1 = lerp(a.y, b.y, tail);
      const x2 = lerp(a.x, b.x, head);
      const y2 = lerp(a.y, b.y, head);
      const grad = ctx.createLinearGradient(x1, y1, x2, y2);
      grad.addColorStop(0, 'rgba(115, 221, 255, 0)');
      grad.addColorStop(0.52, `rgba(139, 229, 255, ${alpha * 0.52})`);
      grad.addColorStop(1, `rgba(220, 250, 255, ${alpha})`);
      ctx.strokeStyle = grad;
      ctx.lineWidth = 1.7;
      ctx.shadowColor = `rgba(103, 222, 255, ${alpha * 0.9})`;
      ctx.shadowBlur = 14;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();

      ctx.fillStyle = `rgba(224, 251, 255, ${alpha})`;
      ctx.shadowBlur = 18;
      ctx.beginPath();
      ctx.arc(x2, y2, 1.9, 0, Math.PI * 2);
      ctx.fill();
    }

    const route = [0, 3, 9, 14, 17, 20, 26, 28, 30];
    const cycle = (t * 0.30) % route.length;
    traceEdge(route[Math.floor(cycle)], cycle % 1, 0.92);
    const cycle2 = (t * 0.21 + 3.65) % route.length;
    traceEdge(route[Math.floor(cycle2)], cycle2 % 1, 0.66);

    ctx.shadowBlur = 0;
    ctx.restore();
  }

  function particleTarget() {
    if (state.width < 560) return 46;
    if (state.width < 900) return 76;
    return 138;
  }

  function seed() {
    const count = particleTarget();
    state.particles = Array.from({ length: count }, (_, i) => new FlowParticle(i, count));
    state.pulses = [new Pulse(0.06, 0), new Pulse(0.49, 0), new Pulse(0.75, 1)];
  }

  function resize() {
    const rect = stage.getBoundingClientRect();
    state.width = Math.max(1, rect.width);
    state.height = Math.max(1, rect.height);
    state.dpr = clamp(window.devicePixelRatio || 1, 1, 2);
    canvas.width = Math.round(state.width * state.dpr);
    canvas.height = Math.round(state.height * state.dpr);
    canvas.style.width = `${state.width}px`;
    canvas.style.height = `${state.height}px`;
    ctx.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
    seed();
  }

  function frame(now) {
    if (!state.running) return;
    const dt = Math.min(0.05, Math.max(0.001, (now - state.last) / 1000));
    state.last = now;

    if (state.visible && !document.hidden) {
      ctx.clearRect(0, 0, state.width, state.height);
      ctx.globalCompositeOperation = 'lighter';
      drawGridGlow(now);
      drawNetworkGlow(now);
      for (const p of state.particles) {
        p.update(dt);
        p.draw();
      }
      for (const pulse of state.pulses) {
        pulse.update(dt);
        pulse.draw();
      }
      ctx.globalCompositeOperation = 'source-over';
    }
    requestAnimationFrame(frame);
  }

  if (finePointer) {
    stage.addEventListener('pointermove', (event) => {
      const r = stage.getBoundingClientRect();
      state.mouseX = clamp((event.clientX - r.left) / r.width, 0, 1);
      state.mouseY = clamp((event.clientY - r.top) / r.height, 0, 1);
      state.mouseActive = true;
    }, { passive: true });
    stage.addEventListener('pointerleave', () => { state.mouseActive = false; }, { passive: true });
  }

  const observer = new IntersectionObserver((entries) => {
    state.visible = entries[0] ? entries[0].isIntersecting : true;
  }, { rootMargin: '120px 0px' });
  observer.observe(stage);

  if ('ResizeObserver' in window) {
    new ResizeObserver(resize).observe(stage);
  } else {
    window.addEventListener('resize', resize, { passive: true });
  }

  reduceMotion.addEventListener?.('change', (event) => {
    if (event.matches) {
      state.running = false;
      canvas.hidden = true;
      ctx.clearRect(0, 0, state.width, state.height);
    }
  });

  resize();
  requestAnimationFrame(frame);
})();
