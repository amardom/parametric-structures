"use strict";

function createDepthRenderer() {
  const bufferCanvas = document.createElement("canvas");
  const gl = bufferCanvas.getContext("webgl", { antialias: true, alpha: true });
  if (!gl) return null;

  const program = gl.createProgram();
  const sources = [
    [gl.VERTEX_SHADER, "#version 100\nattribute vec3 position; attribute vec4 rgba; varying vec4 color; void main() { gl_Position = vec4(position, 1.0); color = rgba; }"],
    [gl.FRAGMENT_SHADER, "#version 100\nprecision mediump float; varying vec4 color; void main() { gl_FragColor = color; }"],
  ];
  for (const [type, source] of sources) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return null;
    gl.attachShader(program, shader);
    gl.deleteShader(shader);
  }
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  const buffer = gl.createBuffer();
  const position = gl.getAttribLocation(program, "position");
  const rgba = gl.getAttribLocation(program, "rgba");
  let lost = false;
  bufferCanvas.addEventListener("webglcontextlost", () => { lost = true; });

  return function renderDepth(polygons, context, w, h) {
    if (lost || gl.isContextLost()) return false;
    let depthRange = 1;
    for (const { corners } of polygons) {
      for (const point of corners) depthRange = Math.max(depthRange, Math.abs(point[2]));
    }
    depthRange *= 1.01;

    const opaque = [];
    const translucent = [];
    for (const polygon of polygons) {
      const { corners, color, opacity = 1, lineWidth } = polygon;
      const vertices = opacity < 1 ? translucent : opaque;
      const [r, g, b] = color.map((value) => value / 255);
      let face = corners;
      if (lineWidth) {
        const [a, c] = corners;
        const dx = c[0] - a[0], dy = c[1] - a[1];
        const length = Math.hypot(dx, dy);
        if (length < 1e-6) continue;
        const offset = lineWidth / (2 * length);
        const ox = -dy * offset, oy = dx * offset;
        face = [[a[0] - ox, a[1] - oy, a[2]], [c[0] - ox, c[1] - oy, c[2]],
                [c[0] + ox, c[1] + oy, c[2]], [a[0] + ox, a[1] + oy, a[2]]];
      }
      for (let i = 1; i < face.length - 1; i++) {
        for (const [x, y, depth] of [face[0], face[i], face[i + 1]]) {
          vertices.push(2 * x / w - 1, 1 - 2 * y / h, -depth / depthRange, r, g, b, opacity);
        }
      }
    }

    const { width, height } = context.canvas;
    if (bufferCanvas.width !== width || bufferCanvas.height !== height) {
      bufferCanvas.width = width;
      bufferCanvas.height = height;
    }
    gl.viewport(0, 0, width, height);
    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.enableVertexAttribArray(position);
    gl.enableVertexAttribArray(rgba);
    gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 28, 0);
    gl.vertexAttribPointer(rgba, 4, gl.FLOAT, false, 28, 12);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.depthMask(true);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    function draw(vertices) {
      if (!vertices.length) return;
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STREAM_DRAW);
      gl.drawArrays(gl.TRIANGLES, 0, vertices.length / 7);
    }

    gl.disable(gl.BLEND);
    draw(opaque);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);
    draw(translucent);
    gl.depthMask(true);
    context.drawImage(bufferCanvas, 0, 0, w, h);
    return true;
  };
}
