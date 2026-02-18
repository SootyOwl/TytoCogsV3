## 0.8.0 (2026-02-18)

### Feat

- convert spottube to hybrid command and add autowatch toggle (#115)

## 0.7.5 (2026-02-18)

### Fix

- **redvids**: Run blocking download operations in thread pool (#112)

## 0.7.4 (2025-12-29)

### Fix

- **tests**: update video URLs in test cases
- **tldw**: refine LLM response instructions

## 0.7.3 (2025-12-18)

### Fix

- **dependencies**: pin openai version to 2.8.1

## 0.7.2 (2025-12-18)

### Fix

- **tldw**: pin openai version to 2.8.1

## 0.7.1 (2025-12-04)

### Refactor

- **tldw**: update cleanup_summary to accept response object

## 0.7.0 (2025-12-04)

### Feat

- **tldw**: update LLM client and enhance response handling

## 0.6.0 (2025-09-12)

### Feat

- **tldw**: support YouTube live video URL extraction

## 0.5.0 (2025-09-08)

### Feat

- **tldw**: add threaded reply setting for summaries
- **tldw**: enhance summary generation with detailed footer

### Fix

- **tldw**: update return types for video summary methods

## 0.4.2 (2025-09-08)

### Fix

- **tldw**: add extra headers to LLM response

## 0.4.1 (2025-09-08)

### Fix

- **tldw**: adjust max_tokens for LLM response

## 0.4.0 (2025-08-16)

### Feat

- **tldw**: add migration notification for OpenRouter integration
- **tldw**: migrate from Anthropic to OpenRouter for video summarization

### Fix

- **tldw**: update migration notification message for clarity and detail
- **tldw**: correct access to is_private flag in interaction extras
- **tldw**: send embed message after setting footer in language commands
- **tldw**: update summary replies to use Discord embeds for better formatting and longer messages
- **tldw**: fix the dynamic prefix grabbing from the migration notice
- update minimum Python version for multiple cogs verified with vermin
- **tldw**: update LLM client initialization with base URL
- **tldw**: switch to aiohttp for asynchronous model fetching and improve error handling
- **tldw**: close LLM client on cog unload to prevent resource leaks
- **tldw**: specify type for bot parameter in setup function

### Refactor

- **tldw**: remove redundant error check and refactor empty summary handling
- **tldw**: update API key handling and model selection for OpenRouter integration

## 0.3.0 (2025-07-22)

### Feat

- **ispyfj**: implement exponential backoff retry for login and refactor login logic
- Switch from youtube-transcript-api to my own yt-transcript-fetcher package
- enhance language management commands with modal and button interactions
- add launch configuration for redbot debugging in VSCode
- **ispyfj**: enhance video handling for uploading, better session management
- **tldw**: Expose transcript languages as a configurable setting Fixes #53, #52
- **ispyfj**: update login mechanism to use username and password; refactor cookie handling
- **mcinfo**: add command to fetch and display status of a single Minecraft server
- **mcinfo**: add global interval configuration and logging for server status checks
- **mcinfo**: implement logging for server status checks and channel validation
- **ispyfj**: add cookie for fjsession to bypass login
- **ispyfj**: use a session with cookies for bypassing login required links
- **tldw**: refactor YouTube transcript handling for new API and improve error management
- **tldw**: enhance tests for YouTube transcript functionality and add LLM response tests
- **mcinfo**: add permission check for sending messages in channel before initializing message
- **mcinfo**: trigger channel check after setting mode to update description or message
- **mcinfo**: add info.json for Minecraft server status cog configuration
- **mcinfo**: add initial implementation of mcinfo cog with server status fetching and formatting helpers
- enhance proxy handling and parameterize transcript tests for better coverage
- enhance proxy handling and parameterize transcript tests for better coverage
- enhance set_proxy command to clear proxy when no input is provided
- implement caching for YouTube video summaries to improve performance
- add private context menu for summarizing YouTube videos and sync bot tree
- update YouTube context menu names for clarity and visibility
- add private context menu for summarizing YouTube videos and improve error handling
- enhance video summarization with improved error handling and additional test case
- add context menu command to summarize YouTube videos and refactor command group for settings
- add cleanup_summary method to format summaries with markdown and handle empty responses
- add TLDW cog to summarize YouTube videos using Claude
- Add RedVids cog for embedding Reddit videos in Discord messages
- Add typing indicator and refactor to convert_link function in x2image.py
- Add spoiler option to x2image.py convert command
- Update x2image.py to include original tweet link in reply
- Update x2image cog to use asyncio for screenshotting
- Update x2image cog to use additional custom flags for Html2Image initialization
- Update x2image cog to use custom flags for Html2Image initialization
- Add pytest-asyncio dependency for asyncio testing
- Add x2image cog for converting x.com links to images
- :sparkles: convert video url to file and upload it instead of linking it
- Remove embed in original message (to clean up a bit)
- Add beautifulsoup4 dependency for better HTML parsing
- Update identifier in ispyfj.py config
- Add vscode settings for Python testing
- Improve link validation in IspyFJ cog
- Add IspyFJ cog for extracting Funnyjunk video links
- Add Funnyjunk link converter cog

### Fix

- **redvids**: fix incomplete URL substring sanitization
- **tldw**: fix language reference in reorder callback
- add environment variables for pytest in GitHub Actions workflow
- update test_download_reddit_video to use async/await and adjust max_size fix: refactor https_proxy fixture to use environment variable for proxy configuration
- update info.json to reflect cog status as disabled due to Chrome's headless mode changes
- **tldw**: update transcript language assertion in test_get_transcript_languages
- **mcinfo**: improve error handling and refactor message update logic
- **mcinfo**: log interval changes for server status checks
- **mcinfo**: restrict set interval command to bot owner for enhanced security
- **mcinfo**: streamline channel removal process from config for better clarity
- **mcinfo**: update command alias for mcinfo group to improve consistency
- **mcinfo**: correctly update channel message ID in configuration after initialization
- **mcinfo**: update channel configuration retrieval to ensure all settings are fetched
- **mcinfo**: update type hints and access methods for channel configuration
- set hidden and disabled properties to true for the GPT3 Chatbot cog because it's outdated and no longer working
- simplify error message for video download failure
- update response handling to use 'content' parameter for error messages
- remove ephemeral flag from error messages because it's not supported
- update response content to display video summary instead of original message
- update response handling to edit original response instead of sending new messages
- add response defer for improved user experience during video summarization
- correct markdown formatting in video transcript key points message
- update markdown formatting in video transcript summaries
- correct markdown formatting for video transcript summaries
- add validation for empty text input and correct key in message structure
- correct model validation logic to properly check against available models
- add default model to the list and update model validation logic
- format model list output with code styling for better readability
- update model handling to use new attributes and improve command clarity
- update Anthropic client to AsyncAnthropic and add model management commands
- update Anthropic client to use AsyncAnthropic and improve error handling in PDF summary generation
- improve error message for invalid PDF URL input
- enhance PDF URL validation to account for case variations in content type header
- improve PDF URL validation to handle case variations in content type
- update summary output structure to include link to full article PDF/DOI
- validate URL input and check content type for PDF documents
- sending content
- send the text itself instead of the textblock
- fix link validation in x2image.py convert command
- await add_cog (duh)
- make setup function awaitable???

### Refactor

- **ispyfj**: improve error handling and retry logic for video URL extraction
- **test**: update get_video_url test to use async and set session cookies
- remove unused import of ToolUseBlock from tldscience.py
- update caching mechanism to use video ID instead of URL for summaries
- rename tldw command group to tldwatch for consistency
- remove unused model commands and related logic for clarity
- consolidate and enhance summary instructions for clarity
- streamline code formatting and enhance summary generation logic
- *always* close video file in IspyFJ cog to prevent resource leaks
- Improve error handling in RedVids cog
- Update RedVids cog to use temporary file instead of directory (duh)
- Update RedVids cog to use temporary file name instead of directory
- Remove ffmpeg requirement from redvids cog
- Remove unnecessary typing indicator and improve convert_link function in x2image.py
- Update x2image.py virtual time budget to 5000ms
- Update x2image.py flags to include "--disable-software-rasterizer"
- Add fixup command to x2image.py
- Add x2image command alias "xti"
- Update x2image.py to include dark mode option in get_twitter_embed function, default to dark mode
- Add await ctx.defer() to x2image.py convert command
- Remove unused GitHub Actions workflows
- Update x2image.py flags
- Update x2image.py to use --hide-scrollbars, --disable-gpu, and --no-sandbox flags for Html2Image initialization
- Update x2image.py to use --virtual-time-budget=5000 flag for Html2Image initialization
- Update x2image.py to use --virtual-time-budget=10000 and --disable-software-rasterizer flags for Html2Image initialization
- Update x2image.py to use --disable-gpu flag for Html2Image initialization
- Update x2image.py to use asyncio.to_thread with a timeout
- Update x2image cog to use data_manager for file paths
- use async
- Improve error handling in IspyFJ cog
- Update IspyFJ cog to use hybrid command decorator
- Improve video URL extraction in IspyFJ cog
- Update IspyFJ cog to use ctx.reply for sending video URL
- Improve video URL extraction in IspyFJ cog
