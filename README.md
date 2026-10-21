# TytoCogsV3

A collection of custom cogs for [Red-DiscordBot V3](https://github.com/Cog-Creators/Red-DiscordBot), featuring AI-powered content summarization, media link conversion, and utility tools.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10-3.11](https://img.shields.io/badge/python-3.10--3.11-blue.svg)](https://www.python.org/downloads/)
[![Red-DiscordBot](https://img.shields.io/badge/Red--DiscordBot-V3-red.svg)](https://github.com/Cog-Creators/Red-DiscordBot)

## 📦 Available Cogs

### Active Cogs

| Cog | Description | Dependencies |
|-----|-------------|--------------|
| **ispyfj** | Converts FunnyJunk video links to direct, embeddable links for Discord | None |
| **mcinfo** | Fetches and displays Minecraft server status and information | mcstatus |
| **redvids** | Embeds Reddit videos directly into Discord from links | ffmpeg, redvid |
| **spottube** | Automatically converts Spotify links to YouTube links when posted in chat | Spotify & YouTube APIs |
| **tldscience** | Summarizes scientific articles using Claude AI (Anthropic) | Anthropic API |
| **tldw** | "Too Long, Didn't Watch" - Summarizes YouTube videos using OpenRouter LLM | OpenRouter API, yt-transcript-fetcher |

### Disabled Cogs

| Cog | Description | Status |
|-----|-------------|--------|
| **gpt3chatbot** | GPT-3 powered chatbot with customizable personas | Currently disabled |
| **x2image** | Converts X.com (Twitter) links to image screenshots | Disabled due to Chrome headless mode changes |

## 🚀 Installation

### Prerequisites

- [Red-DiscordBot V3](https://github.com/Cog-Creators/Red-DiscordBot) installed and configured
- Python 3.10 or 3.11
- ffmpeg (required for `redvids` cog)

### Installing the Repository

1. Add this repository to your Red instance:
```
[p]repo add TytoCogsV3 https://github.com/SootyOwl/TytoCogsV3
```

2. Install the cog(s) you want:
```
[p]cog install TytoCogsV3 <cog_name>
```

3. Load the cog:
```
[p]load <cog_name>
```

Replace `[p]` with your bot's prefix and `<cog_name>` with the name of the cog you want to install (e.g., `tldw`, `mcinfo`, `spottube`).

## ⚙️ Configuration

### API Keys

Some cogs require API keys to function:

#### tldscience
Requires an Anthropic (Claude) API key:
```
[p]set api anthropic api_key <your_api_key>
```

#### tldw
Requires an OpenRouter API key:
```
[p]set api openrouter api_key <your_api_key>
```

#### spottube
Requires Spotify and YouTube API credentials. Configuration details are available in the cog's documentation.

### General Settings

Each cog may have additional configuration options. Use `[p]help <cog_name>` to see available commands and settings for each cog.

## 📖 Usage Examples

### tldw (YouTube Summarization)
```
[p]tldw https://www.youtube.com/watch?v=example
```
Generates a summary of the YouTube video's content.

### tldscience (Article Summarization)
```
[p]tldscience https://example.com/scientific-article
```
Provides a TLDR summary of scientific articles and research papers.

### mcinfo (Minecraft Server Status)
```
[p]mcinfo play.example.com
```
Displays the status and information for a Minecraft server.

### spottube (Spotify to YouTube Conversion)
Simply post a Spotify link in chat, and the bot will automatically reply with the corresponding YouTube link.

### redvids (Reddit Video Embedding)
Post a Reddit link containing a video, and the bot will embed it directly in Discord.

### ispyfj (FunnyJunk Video Links)
Post a FunnyJunk video link, and the bot will convert it to an embeddable format.

## 🛠️ Development

### Setting Up Development Environment

1. Clone the repository:
```bash
git clone https://github.com/SootyOwl/TytoCogsV3.git
cd TytoCogsV3
```

2. Install dependencies using uv:
```bash
uv sync --dev
```

3. Install pre-commit hooks:
```bash
pre-commit install
```

### Running Tests

```bash
uv run pytest
```

Normal tests block network access and skip checks marked `live`, even when API
keys are configured. Required PR tests run only these ordinary tests and receive
no service credentials.

To explicitly run live external-service checks:

```bash
uv run pytest --live -m live -ra
```

These checks contact YouTube, FunnyJunk, Minecraft servers, and OpenRouter. The
OpenRouter check can incur API charges. Configure `OPENROUTER_API_KEY` (or the
legacy `OPENAI_API_KEY`) for that check, and `FUNNYJUNK_USERNAME` plus
`FUNNYJUNK_PASSWORD` for authenticated FunnyJunk checks. Missing or blank
credentials cause the relevant tests to skip; configured but invalid credentials
still fail. Local `.env` files are supported.

On GitHub, use **Actions → Live Service Checks → Run workflow**. This workflow is
manual only: it does not run on pushes, pull requests, or a schedule. Repository
Actions secrets provide credentials and optional `HTTP_PROXY` / `HTTPS_PROXY`;
tests whose credentials are absent skip. Existing disabled X checks remain skipped.


### Code Style

This project uses:
- **Black** for code formatting (line length: 120)
- **Flake8** for linting
- **pre-commit** hooks to ensure code quality

Format your code before committing:
```bash
black .
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to:
1. Follow the existing code style
2. Update tests as appropriate
3. Update documentation as needed
4. Follow the [Code of Conduct](CODE_OF_CONDUCT.md)

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## 👤 Author

**Tyto (SootyOwl)**
- GitHub: [@SootyOwl](https://github.com/SootyOwl)
- Email: tyto@tyto.cc

## ⚠️ Disclaimer

None of this code is guaranteed to work. Use at your own risk.

## 🙏 Acknowledgments

- Built for [Red-DiscordBot V3](https://github.com/Cog-Creators/Red-DiscordBot)
- Thanks to all contributors and users of these cogs
- Special thanks to Nyko for co-authoring the gpt3chatbot cog
