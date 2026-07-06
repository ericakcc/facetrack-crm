// src/facetrack/components/face_capture/frontend/capture_logic.js
// Pure, DOM-free capture-decision logic. Attached to window.CaptureLogic so
// index.html (classic script) and the Playwright unit tests share one source.
(function (global) {
  "use strict";

  // Exponential moving average smoother for head-pose angles (degrees).
  function makePoseSmoother(alpha) {
    let prev = null;
    return {
      update(pose) {
        if (prev === null) {
          prev = { yaw: pose.yaw, pitch: pose.pitch, roll: pose.roll };
        } else {
          prev = {
            yaw: alpha * pose.yaw + (1 - alpha) * prev.yaw,
            pitch: alpha * pose.pitch + (1 - alpha) * prev.pitch,
            roll: alpha * pose.roll + (1 - alpha) * prev.roll,
          };
        }
        return { yaw: prev.yaw, pitch: prev.pitch, roll: prev.roll };
      },
      reset() {
        prev = null;
      },
    };
  }

  // Variance of the discrete Laplacian over a grayscale buffer. Higher = sharper.
  function laplacianVariance(gray, width, height) {
    let sum = 0;
    let sumSq = 0;
    let n = 0;
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const i = y * width + x;
        const lap =
          4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - width] - gray[i + width];
        sum += lap;
        sumSq += lap * lap;
        n++;
      }
    }
    if (n === 0) return 0;
    const mean = sum / n;
    return sumSq / n - mean * mean;
  }

  // Highest-scoring in-tolerance frame; falls back to highest-scoring overall
  // when no frame is in tolerance. frames: [{score:number, inTolerance:boolean}]
  function pickSharpestFrame(frames) {
    if (!frames || frames.length === 0) return null;
    const inTol = frames.filter((f) => f.inTolerance);
    const pool = inTol.length > 0 ? inTol : frames;
    return pool.reduce((best, f) => (f.score > best.score ? f : best), pool[0]);
  }

  global.CaptureLogic = {
    makePoseSmoother,
    laplacianVariance,
    pickSharpestFrame,
  };
})(window);
