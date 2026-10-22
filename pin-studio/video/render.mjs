#!/usr/bin/env node
/**
 * Render one flip-through video from a spec built by pin-studio/video_spec.py.
 *
 *   node render.mjs --spec spec.json --out pin.mp4 [--poster pin.png]
 *
 * The spec carries absolute paths to the page images and the font folder;
 * they are copied into a temporary public folder so the composition can load
 * them, and nothing outside it is read. The poster is a still of the first
 * page, fully in place — the cover Pinterest shows before the video plays.
 *
 * Browser: REMOTION_BROWSER if set, else a pre-installed headless Chromium
 * when one is found, else Remotion downloads its own on first use.
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";

const HERE = path.dirname(fileURLToPath(import.meta.url));

function arg(name) {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? null : process.argv[i + 1];
}

function findBrowser() {
  if (process.env.REMOTION_BROWSER) return process.env.REMOTION_BROWSER;
  const base = "/opt/pw-browsers";
  if (!fs.existsSync(base)) return null;
  for (const dir of fs.readdirSync(base).sort().reverse()) {
    const shell = path.join(base, dir, "chrome-linux", "headless_shell");
    if (dir.startsWith("chromium_headless_shell") && fs.existsSync(shell)) return shell;
  }
  return null;
}

const specPath = arg("spec");
const out = arg("out");
const poster = arg("poster");
if (!specPath || !out) {
  console.error("usage: node render.mjs --spec spec.json --out video.mp4 [--poster cover.png]");
  process.exit(2);
}

const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const pub = fs.mkdtempSync(path.join(os.tmpdir(), "obp-video-"));
fs.mkdirSync(path.join(pub, "fonts"));
fs.mkdirSync(path.join(pub, "pages"));
for (const f of ["DMSerifDisplay-Regular.ttf", "Poppins-Regular.ttf", "Poppins-Medium.ttf"]) {
  fs.copyFileSync(path.join(spec.fontsDir, f), path.join(pub, "fonts", f));
}
const pages = spec.pages.map((p, i) => {
  const name = `pages/${String(i + 1).padStart(2, "0")}${path.extname(p.path)}`;
  fs.copyFileSync(p.path, path.join(pub, name));
  return { src: name, width: p.width, height: p.height };
});
const inputProps = { ...spec.props, pages };

const browserExecutable = findBrowser();
const chromiumOptions = { gl: "swangle" };

try {
  const serveUrl = await bundle({ entryPoint: path.join(HERE, "src", "index.jsx"), publicDir: pub });
  const composition = await selectComposition({ serveUrl, id: "Flipthrough", inputProps, browserExecutable, chromiumOptions });

  await renderMedia({
    serveUrl,
    composition,
    inputProps,
    codec: "h264",
    crf: 24,
    pixelFormat: "yuv420p",
    outputLocation: out,
    browserExecutable,
    chromiumOptions,
    muted: true,
  });
  console.log(`video  ${out}  (${(fs.statSync(out).size / 1e6).toFixed(1)} MB, ${composition.durationInFrames / composition.fps}s)`);

  if (poster) {
    const t = inputProps.timing;
    await renderStill({
      serveUrl,
      composition,
      inputProps,
      frame: t.intro + Math.round(t.perPage / 2),
      output: poster,
      imageFormat: "png",
      browserExecutable,
      chromiumOptions,
    });
    console.log(`poster ${poster}`);
  }
} finally {
  fs.rmSync(pub, { recursive: true, force: true });
}
