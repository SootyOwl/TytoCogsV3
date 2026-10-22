# mcinfo changelog

## mcstatus 14 migration

- Require `mcstatus>=14.2.0,<15` in both the cog installer and development project.
- Use the public `mcstatus.responses` API and immutable response fixtures.
- Handle DNS lookup failures and timeouts consistently with status-query failures,
  preserving their original exception causes. A failed server does not prevent
  other configured servers from being displayed.
- Gain the dependency's IPv6 DNS support and current protocol fixes. Existing
  Java server addresses and command configuration continue to work.
