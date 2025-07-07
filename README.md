# ATL Wiki Bot

A Discord bot system that verifies Discord users against MediaWiki accounts using OAuth, designed for the All Things Linux community.

## 🏗️ Architecture

This is a monorepo containing two main components:

- **Discord Bot** (`bot/`) - Handles Discord interactions and user verification
- **Flask API** (`api/`) - Manages OAuth flow and MediaWiki integration  
- **PostgreSQL Database** - Stores verification data and user links

```text
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Discord Bot   │    │   Flask API     │    │   MediaWiki     │
│                 │    │                 │    │                 │
│ • Commands      │◄──►│ • OAuth Flow    │◄──►│ • User Verify   │
│ • Role Mgmt     │    │ • JWT Tokens    │    │ • Account Link  │
│ • Verification  │    │ • Database      │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │
         └───────────────────────┼────────────────────────────────┐
                                 │                                │
                    ┌────────────▼──────────────┐                 │
                    │    PostgreSQL Database    │                 │
                    │                           │                 │
                    │ • User links              │                 │
                    │ • Verification tokens     │                 │
                    │ • Audit logs              │                 │
                    └───────────────────────────┘                 │
                                                                  │
                              ┌───────────────────────────────────▼─┐
                              │            Docker Network           │
                              │                                     │
                              │ • Service discovery                 │
                              │ • Internal communication            │
                              │ • Isolated environment              │
                              └─────────────────────────────────────┘
```

## ✨ Features

- **🔗 MediaWiki Integration**: OAuth-based verification with MediaWiki
- **🤖 Discord Commands**: Easy-to-use slash commands for verification
- **👥 Role Management**: Automatic role assignment for verified users
- **📊 Admin Tools**: User management
- **🗄️ Database Persistence**: PostgreSQL for reliable data storage
- **🐳 Docker Ready**: Full containerization with Docker Compose
- **📝 Rich Logging**: Comprehensive logging with emoji indicators
- **🔒 Security**: JWT tokens, secure OAuth flow, environment-based secrets

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- A Discord application with bot permissions
- MediaWiki OAuth consumer credentials

### 1. Clone and Setup

```bash
git clone <repository-url>
cd atl-wiki-bot
cp env.example .env
```

### 2. Configure Environment

Edit `.env` with your credentials:

```bash
# Discord Configuration
DISCORD_TOKEN=your_discord_bot_token_here
WIKI_AUTHOR_ROLE_ID=123456789012345678
ALLOWED_ROLE_IDS=123456789012345678,987654321098765432
DISCORD_PREFIX="w$"

# MediaWiki OAuth (get from Special:OAuthConsumerRegistration)
MW_CONSUMER_KEY=your_mediawiki_consumer_key
MW_CONSUMER_SECRET=your_mediawiki_consumer_secret
MW_API_URL=https://your.wiki.org/api.php

# API Security Keys (generate random secure strings)
FLASK_SECRET_KEY=your_super_secret_flask_key_here
JWT_SECRET=your_jwt_secret_key_here

# API URLs (adjust for production)
VERIFICATION_URL=http://localhost:5000/verify
CALLBACK_URL=http://localhost:5000/verify/callback

# Database URL (uses Docker service name 'db')
DATABASE_URL=postgresql://wiki-link-user:password@db:5432/wiki-link-db
```

> **Note**: The database URL is automatically configured for Docker. Only change if using external database.

### 3. Launch with Docker

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### 4. Verify Setup

- Bot should appear online in Discord
- API accessible at `http://localhost:5000`
- Database running on port `5432`

## 🛠️ Development

### Local Development Setup

```bash
# Install Poetry (if not installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

### Running Components Individually

```bash
# Run Discord bot
poetry run python -m bot.main

# Run Flask API
poetry run python -m api.app

# Run with auto-reload (development)
docker compose up --watch
```

### Project Structure

```text
atl-wiki-bot/
├── bot/                    # Discord Bot
│   ├── commands/           # Slash commands
│   │   └── verification.py # Verification commands
│   │   └── lookup.py       # Lookup commands
│   ├── core/              # Core functionality
│   │   ├── config.py      # Configuration management
│   │   ├── database.py    # Database operations
│   │   ├── embeds.py      # Discord embed templates
│   │   ├── logger.py      # Logging utilities
│   │   ├── pagination.py  # Paginated views
│   │   ├── tasks.py       # Background tasks
│   │   └── verification.py# Verification logic
│   ├── bot.py             # Main bot class
│   └── main.py            # Entry point
├── api/                   # Flask API
│   ├── app.py             # Flask application
│   └── __init__.py
├── docker-compose.yml     # Docker orchestration
├── Dockerfile.bot         # Bot container
├── Dockerfile.api         # API container
├── pyproject.toml         # Python dependencies
└── env.example            # Environment template
```

## 🎯 Commands

### User Commands (available to everyone)

- `/verify` - Start MediaWiki account verification
- `/unverify` - Remove your own verification link
- `/lookup` - Look up Discord user from MediaWiki username or vice versa

### Admin Commands (require allowed role)

- `/unverify <user|mediawiki_username>` - Remove verification for any user by Discord or MediaWiki username
- `/verified` - List all verified users

## 🔧 Configuration

### Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Copy the token to `DISCORD_TOKEN`
5. Enable required intents:
   - Server Members Intent
   - Message Content Intent

### MediaWiki OAuth Setup

1. Go to `Special:OAuthConsumerRegistration` on your wiki
2. Create a new OAuth consumer with these grants:
   - `Basic rights` (to access user information)
   - `Confirm user identification` (to verify user identity)
3. Copy Consumer Key/Secret to environment variables

### Role Configuration

- `WIKI_AUTHOR_ROLE_ID`: Role granted to verified users
- `ALLOWED_ROLE_IDS`: Roles that can use admin commands (comma-separated)

## 🗄️ Database Schema

```sql
-- Verification links table
CREATE TABLE links (
    id SERIAL PRIMARY KEY,
    discord_user_id BIGINT NOT NULL UNIQUE,
    mediawiki_username VARCHAR(255),
    verified BOOLEAN DEFAULT FALSE,
    token VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_discord_user_id ON links(discord_user_id);
CREATE INDEX idx_token ON links(token);
CREATE INDEX idx_verified ON links(verified);
```

## 🐳 Docker Services

| Service | Container       | Port | Description            |
| ------- | --------------- | ---- | ---------------------- |
| `db`    | `wiki-link-db`  | 5432 | PostgreSQL database    |
| `bot`   | `wiki-link-bot` | -    | Discord bot            |
| `api`   | `wiki-link-api` | 5000 | Flask verification API |

### Docker Commands

```bash
# View service status
docker compose ps

# View logs for specific service
docker compose logs -f bot
docker compose logs -f api
docker compose logs -f db

# Rebuild and restart
docker compose up --build -d

# Access database
docker compose exec db psql -U wiki-link-user -d wiki-link-db

# Shell access
docker compose exec bot bash
docker compose exec api bash
```

## 🔍 Monitoring & Logs

### Log Levels and Emojis

- 🎉 **SUCCESS**: Verification completed
- ℹ️ **INFO**: User actions, general events
- ⚠️ **WARNING**: Pending verifications, soft errors
- ❌ **ERROR**: Failed operations, exceptions
- 🗄️ **DATABASE**: Database operations
- 🔗 **VERIFICATION**: Verification flow events

### Health Checks

- Database: `pg_isready` checks every 5 seconds
- API: Available at `http://localhost:5000/verify`
- Bot: Check Discord status

## 🚨 Troubleshooting

### Common Issues

**Bot not responding to commands:**

```bash
# Check bot logs
docker compose logs -f bot

# Verify token and permissions
docker compose exec bot env | grep DISCORD_TOKEN
```

**Database connection errors:**

```bash
# Check database health
docker compose exec db pg_isready -U wiki-link-user

# Restart database
docker compose restart db
```

**OAuth verification fails:**

```bash
# Check API logs
docker compose logs -f api

# Verify MediaWiki credentials
docker compose exec api env | grep MW_
```

**Permission errors:**

```bash
# Check role configuration
docker compose exec bot env | grep ROLE_ID

# Verify bot has role management permissions
```

### Debug Mode

Enable debug logging in development:

```bash
# Add to .env
FLASK_DEBUG=1

# Or set logging level in bot/core/logger.py
logger.add(sys.stdout, level="DEBUG")
```
