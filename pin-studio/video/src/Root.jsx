import { Composition } from "remotion";
import { Flipthrough, durationFor } from "./Flipthrough";

// One composition; size, length and content all come from the spec that
// render.mjs passes in (built by pin-studio/video_spec.py).
export const Root = () => (
  <Composition
    id="Flipthrough"
    component={Flipthrough}
    fps={30}
    width={1000}
    height={1500}
    durationInFrames={300}
    defaultProps={{}}
    calculateMetadata={({ props }) => ({
      width: props.width,
      height: props.height,
      durationInFrames: durationFor(props),
    })}
  />
);
