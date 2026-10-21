# tldw changelog

## Unreleased

### Changed
- Require `yt-transcript-fetcher>=2.0.0,<3` to use YouTube's current transcript panels.
- Fetch transcripts on a dedicated worker so YouTube requests and retry waits do not block Discord.
- Serialize access to the shared transcript client, including when a command is cancelled,
  and close its session after outstanding work finishes when the cog unloads.
- Show distinct messages for missing captions, unavailable videos, rate limits, network
  failures, and invalid YouTube responses. Preserve original exceptions in bot tracebacks.
- Keep configured language priorities and summary caching. The cog adds no retries on
  top of the package's existing rate-limit and transient-error retries.

### Fixed
- Handle videos without captions during language discovery without referencing an unset language.
- Reject empty transcripts before sending them to the summarization service.

## 1.0.1 (2025-04-29)

### Added
- Added support for user configurable transcript languages.
Users can now add/remove/list/reorder languages from the `languages` list using the appropriate `[p]tldwset languages` commands.
- Now have a changelog file to track changes and updates to the cog.

### Changed
- The `get_transcript` function now uses the `languages` list to determine
  which languages to use for the transcript.


---
