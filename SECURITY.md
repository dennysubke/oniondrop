# Security

## Reporting a vulnerability

Please do not publish a suspected vulnerability in a public issue before a fix is available. Use GitHub's private vulnerability reporting feature for this repository when available.

Include the affected version, deployment method, reproduction steps, expected impact and any relevant sanitized logs. Never include real onion service keys, login passwords or received private files.

## Deployment guidance

The OnionDrop administration interface should be restricted to a trusted network or protected by HTTPS and authentication. Do not expose port 8397 directly to the public internet.

Private OnionShare authorization protects an individual receive service. It does not protect the OnionDrop administration interface.

Backups of `/data/services` are sensitive because they contain persistent onion identities and may contain client-authorization credentials.
