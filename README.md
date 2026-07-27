# OnionDrop

OnionDrop is a persistent, OnionShare-compatible file intake app designed for Umbrel. It wraps the official OnionShare CLI receive mode in a dedicated Tor-style web interface and keeps each receive service, onion identity, private access key, log, and uploaded file in persistent storage.

## What version 0.1.0 includes

- Multiple persistent OnionShare receive services (up to four active by default)
- Private-key-protected or public onion services
- Files, anonymous text messages, or both
- Automatic restart after OnionDrop restarts
- Optional expiration and soft storage stop
- QR codes and complete invite copying
- Local file browser, downloads, deletion, and service logs
- Import and export of persistent OnionShare receive JSON files
- Responsive, dependency-free Tor-style frontend
- Multi-architecture Docker base for `linux/amd64` and `linux/arm64`

## Compatibility

OnionDrop does not implement a lookalike transfer protocol. The Docker image installs `onionshare-cli` from the official OnionShare source and starts it in persistent receive mode. The generated onion address and client-auth private key are therefore native OnionShare service credentials. Senders open the address in Tor Browser, exactly like a receive service created by OnionShare Desktop.

Persistent receive JSON files can be moved between OnionDrop and compatible OnionShare CLI/Desktop installations. OnionDrop rewrites only the receive folder when importing so uploaded files stay inside `/data/inboxes`.

## Security notes

- Uploaded files are untrusted. Do not open unknown documents directly on a trusted workstation.
- The soft storage stop is checked after data reaches disk and is not a strict per-upload size limit.
- Each active inbox runs an isolated OnionShare/Tor process. This prevents one service shutdown from removing another service, but it also uses more memory than a single Tor daemon.
- A public onion service has no private client-auth key. Anyone who learns its address can submit content.
- Back up `/data/services` together with `/data/state.json`. The service files contain private onion identity material.
- OnionDrop is not SecureDrop and is not intended to replace a professionally operated whistleblower platform.

## Local build

```bash
docker buildx create --name oniondrop-builder --use 2>/dev/null || docker buildx use oniondrop-builder
docker buildx inspect --bootstrap

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --build-arg ONIONSHARE_VERSION=2.6.4 \
  -t dennysubke/oniondrop:0.1.0 \
  --push .
```

For a local test without Tor, set `ONIONDROP_MOCK=true` in `docker-compose.dev.yml`. Mock mode generates fake credentials and must never be used as a real transfer service.

## Docker Hub digest

After pushing, obtain the multiarch digest and pin it in the Umbrel package:

```bash
docker buildx imagetools inspect dennysubke/oniondrop:0.1.0
```

Then change the image line to:

```yaml
image: dennysubke/oniondrop:0.1.0@sha256:YOUR_MULTIARCH_DIGEST
```

## Persistent paths

| Path | Purpose |
|---|---|
| `/data/state.json` | OnionDrop metadata |
| `/data/services/*.json` | OnionShare persistent service identities |
| `/data/inboxes/<id>/` | Received files and messages |
| `/data/logs/<id>.log` | OnionShare process output |
| `/data/home/` | OnionShare runtime settings |
