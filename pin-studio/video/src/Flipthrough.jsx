import { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  continueRender,
  delayRender,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";

/* ==========================================================================
   A flip-through of a product's real pages, in the pin tiles' house look:
   the product's soft tint behind, kicker / DM Serif headline / subline on
   top, the "obenpaper" footer under a rule in the accent.

   Everything that must not be guessed — the words, their size and line
   breaks, every colour, the page files and the layout boxes — arrives in
   the props, computed by pin-studio/video_spec.py with the same text
   fitting the PNG tiles use. This file only draws and moves things.

   Motion follows the site's preview viewer: tablet pages SLIDE (about a
   third of a second), print pages simply CHANGE, a short fade. One slow
   push-in on the whole page area; nothing else moves.
   ========================================================================== */

const SLIDE = 10; // frames, ≈ 0.34 s at 30 fps — the site viewer's tablet slide
const CUT = 6; // frames, ≈ 0.2 s — the site viewer's print change

export function durationFor(props) {
  const t = props.timing ?? { intro: 36, perPage: 66, outro: 30 };
  return t.intro + t.perPage * (props.pages?.length ?? 1) + t.outro;
}

function useFonts() {
  const [handle] = useState(() => delayRender("fonts"));
  useEffect(() => {
    const faces = [
      new FontFace("DM Serif Display", `url(${staticFile("fonts/DMSerifDisplay-Regular.ttf")})`),
      new FontFace("Poppins", `url(${staticFile("fonts/Poppins-Regular.ttf")})`, { weight: "400" }),
      new FontFace("Poppins", `url(${staticFile("fonts/Poppins-Medium.ttf")})`, { weight: "500" }),
    ];
    Promise.all(faces.map((f) => f.load()))
      .then((loaded) => {
        loaded.forEach((f) => document.fonts.add(f));
        continueRender(handle);
      })
      .catch((err) => {
        console.error(err);
        continueRender(handle);
      });
  }, [handle]);
}

const ease = Easing.bezier(0.22, 0.61, 0.36, 1);

function rise(frame, start, length = 18, distance = 24) {
  const p = interpolate(frame, [start, start + length], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });
  return { opacity: p, transform: `translateY(${(1 - p) * distance}px)` };
}

function TextBlock({ layout, colors, frame }) {
  const { kicker, headline, subline } = layout;
  return (
    <>
      {kicker?.text ? (
        <div
          style={{
            position: "absolute",
            left: kicker.x,
            top: kicker.y,
            fontFamily: "Poppins",
            fontWeight: 500,
            fontSize: kicker.size,
            letterSpacing: kicker.tracking,
            color: colors.dark,
            whiteSpace: "nowrap",
            lineHeight: 1.2,
            ...rise(frame, 0, 14, 10),
          }}
        >
          {kicker.text}
        </div>
      ) : null}
      {headline.lines.map((line, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: headline.x,
            top: headline.y + i * headline.leading,
            fontFamily: "DM Serif Display",
            fontSize: headline.size,
            lineHeight: `${headline.leading}px`,
            color: colors.ink,
            whiteSpace: "nowrap",
            ...rise(frame, 4 + i * 5, 20, 28),
          }}
        >
          {line}
        </div>
      ))}
      {(subline?.lines ?? []).map((line, i) => (
        <div
          key={`s${i}`}
          style={{
            position: "absolute",
            left: subline.x,
            top: subline.y + i * subline.leading,
            fontFamily: "Poppins",
            fontSize: subline.size,
            lineHeight: `${subline.leading}px`,
            color: colors.ink2,
            whiteSpace: "nowrap",
            ...rise(frame, 16 + i * 4, 18, 14),
          }}
        >
          {line}
        </div>
      ))}
    </>
  );
}

function Footer({ layout, colors }) {
  const { footer } = layout;
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: footer.x0,
          width: footer.x1 - footer.x0,
          top: footer.y,
          height: 3,
          background: colors.main,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: footer.x0,
          top: footer.y + 18,
          fontFamily: "DM Serif Display",
          fontSize: footer.wordmarkSize,
          lineHeight: 1.2,
          color: colors.ink,
        }}
      >
        obenpaper
      </div>
      {footer.right ? (
        <div
          style={{
            position: "absolute",
            right: layout.width - footer.x1,
            top: footer.y + 30,
            fontFamily: "Poppins",
            fontWeight: 500,
            fontSize: footer.rightSize,
            lineHeight: 1.2,
            color: colors.dark,
          }}
        >
          {footer.right}
        </div>
      ) : null}
    </>
  );
}

/** Where page i is in its turn, as a fraction of the slide/cut in (0..1). */
function pageIndexAt(frame, timing, count) {
  const t = frame - timing.intro;
  if (t < 0) return { index: 0, progress: 1 };
  const index = Math.min(count - 1, Math.floor(t / timing.perPage));
  const into = t - index * timing.perPage;
  return { index, into };
}

function fitBox(box, ratio, maxW) {
  let w = Math.min(box.w, maxW ?? box.w);
  let h = w / ratio;
  if (h > box.h) {
    h = box.h;
    w = h * ratio;
  }
  return { w, h, x: box.x + (box.w - w) / 2, y: box.y + (box.h - h) / 2 };
}

function Tablet({ pages, box, colors, frame, timing }) {
  const page = pages[0];
  const bezel = Math.round(box.w * 0.028);
  const ratio = page.width / page.height;
  const inner = fitBox({ ...box, w: box.w - 2 * bezel, h: box.h - 2 * bezel }, ratio);
  const outer = { w: inner.w + 2 * bezel, h: inner.h + 2 * bezel };
  const x = box.x + (box.w - outer.w) / 2;
  const y = box.y + (box.h - outer.h) / 2;

  const { index, into } = pageIndexAt(frame, timing, pages.length);
  // The track sits at the current page, and slides from the previous one
  // during the first SLIDE frames of each turn.
  const from = index === 0 ? 0 : index - 1;
  const slide = index === 0 ? 1 : interpolate(into, [0, SLIDE], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease,
  });
  const position = from + (index - from) * slide;

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: outer.w,
        height: outer.h,
        borderRadius: bezel * 1.7,
        background: colors.ink,
        boxShadow: "0 18px 50px rgba(40,30,25,0.28)",
        padding: bezel,
        boxSizing: "border-box",
      }}
    >
      <div style={{ width: inner.w, height: inner.h, overflow: "hidden", borderRadius: bezel * 0.55, background: "#fff" }}>
        <div style={{ display: "flex", width: inner.w * pages.length, height: inner.h, transform: `translateX(${-position * inner.w}px)` }}>
          {pages.map((p) => (
            <Img key={p.src} src={staticFile(p.src)} style={{ width: inner.w, height: inner.h, objectFit: "cover", flex: "0 0 auto" }} />
          ))}
        </div>
      </div>
    </div>
  );
}

function Paper({ pages, box, frame, timing }) {
  const page = pages[0];
  const sheet = fitBox(box, page.width / page.height);
  const { index, into } = pageIndexAt(frame, timing, pages.length);
  const fade = index === 0 ? 1 : interpolate(into, [0, CUT], [0.35, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        position: "absolute",
        left: sheet.x,
        top: sheet.y,
        width: sheet.w,
        height: sheet.h,
        background: "#fff",
        boxShadow: "0 1px 3px rgba(40,30,25,0.18), 0 18px 46px rgba(40,30,25,0.22)",
        borderRadius: 3,
        overflow: "hidden",
      }}
    >
      <Img src={staticFile(pages[index].src)} style={{ width: "100%", height: "100%", objectFit: "cover", opacity: fade }} />
    </div>
  );
}

function Dots({ count, layout, colors, frame, timing }) {
  const { index } = pageIndexAt(frame, timing, count);
  const { dots } = layout;
  if (!dots || count < 2) return null;
  const size = dots.size;
  return (
    <div
      style={{
        position: "absolute",
        left: layout.media.x,
        width: layout.media.w,
        top: dots.y,
        display: "flex",
        justifyContent: "center",
        gap: size * 0.9,
      }}
    >
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          style={{
            width: size,
            height: size,
            borderRadius: size,
            background: i === index ? colors.dark : colors.ink,
            opacity: i === index ? 1 : 0.18,
          }}
        />
      ))}
    </div>
  );
}

export function Flipthrough(props) {
  useFonts();
  const frame = useCurrentFrame();
  const { colors, layout, pages, edition } = props;
  const timing = props.timing;
  const total = durationFor(props);

  // The page area rises in after the headline, then pushes in very slowly.
  const enter = interpolate(frame, [8, timing.intro], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease,
  });
  const push = interpolate(frame, [timing.intro, total], [1, 1.035], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const box = layout.media;

  return (
    <AbsoluteFill style={{ background: colors.bg }}>
      <TextBlock layout={layout} colors={colors} frame={frame} />
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: enter,
          transform: `translateY(${(1 - enter) * 40}px) scale(${push})`,
          transformOrigin: `${box.x + box.w / 2}px ${box.y + box.h / 2}px`,
        }}
      >
        {edition === "tablet" ? (
          <Tablet pages={pages} box={box} colors={colors} frame={frame} timing={timing} />
        ) : (
          <Paper pages={pages} box={box} frame={frame} timing={timing} />
        )}
      </div>
      <Dots count={pages.length} layout={layout} colors={colors} frame={frame} timing={timing} />
      <Footer layout={layout} colors={colors} />
    </AbsoluteFill>
  );
}
