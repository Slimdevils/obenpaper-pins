# obenpaper-pins

Obenpaper's Pinterest, end to end: Claude makes the pins every week and the
publisher posts them every hour. Start with `pinterest-api/README.md`.

- `pin-studio/` — how pins are made (catalogue, tile renderer, weekly procedure)
- `pins/` — the rendered tiles (public: Pinterest fetches them from here)
- `pinterest-api/` — the queue, the rules and the publisher
- `.github/workflows/publish-pins.yml` — runs it every hour
