# Changelog

## 0.2.0

OnionDrop is now a fully standalone, platform-independent Docker application while retaining an optional Umbrel integration.

### Added

- First-run setup and optional built-in administrator login
- Eight interface languages: English, German, Spanish, Italian, French, Chinese, Japanese and Russian
- Compact language selectors with discreet flag indicators
- Animated Tor connection state, bootstrap progress and Tor version display
- Persistent SHA-256 checksums for received files
- Downloadable PNG QR codes for onion addresses and private access keys
- Multi-file selection and ZIP download
- Read-only previews for common images, media, PDFs, text, source code, JSON, tables, Office/OpenDocument files, EPUB, EML, RTF and archive listings
- Standalone Docker Compose deployment
- Security headers, CSRF protection, login throttling and scrypt password storage
- Automatic migration of 0.1.0 inbox metadata

### Changed

- Removed all Umbrel-specific wording and runtime assumptions from the core application
- Preserved complete supported fields when importing and restarting OnionShare configurations
- Kept the simplified interface and compact About section introduced in 0.1.0
- Retained clipboard support for both secure contexts and HTTP installations

### Fixed

- Private access keys are now copied directly from the current inbox state instead of being embedded in an HTML attribute
- Replaced platform-dependent emoji flags with small local SVG flags in an accessible custom language picker

### Security

- Uploaded HTML and SVG are rendered as text rather than active pages
- Structured document preview reads are bounded by decompressed member limits
- Temporary ZIP downloads are removed after the response closes
- Private application settings and onion configuration files are written with restrictive permissions where supported
