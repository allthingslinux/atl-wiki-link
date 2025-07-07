"""Database operations for the Discord bot."""

import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
import psycopg2
from .config import Config


class DatabaseManager:
    """Handles all database operations."""

    def __init__(self):
        self.connection_string = Config.DATABASE_URL

    def get_connection(self):
        """Get a database connection."""
        return psycopg2.connect(self.connection_string)

    def test_connection(self, max_retries: int = 10) -> bool:
        """Test database connection with retries."""
        import time

        for i in range(max_retries):
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1;")
                print("✅ Database is ready.")
                return True
            except psycopg2.OperationalError:
                print(f"⏳ Database not ready, retrying... ({i + 1}/{max_retries})")
                time.sleep(3)

        print("❌ Database did not become ready in time.")
        return False

    def init_database(self) -> None:
        """Initialize database tables."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS links (
                            discord_id BIGINT PRIMARY KEY,
                            mediawiki_username TEXT,
                            token TEXT NOT NULL,
                            created_at TIMESTAMP NOT NULL,
                            verified BOOLEAN DEFAULT FALSE
                        );
                    """)
                    conn.commit()
            print("[DB INIT] Table 'links' ensured and schema updated.")
        except Exception as e:
            print(f"[DB INIT ERROR] {e}")
            raise

    def create_verification_token(self, discord_id: int) -> Optional[str]:
        """Create a verification token for a user."""
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if user already exists (similar to old logic)
                    cur.execute(
                        "SELECT verified, created_at FROM links WHERE discord_id = %s",
                        (discord_id,),
                    )
                    result = cur.fetchone()

                    if result:
                        verified, created_at = result
                        if verified:
                            # User is already verified - this should be handled by the calling code
                            # but return None to indicate no new token needed
                            return None

                        # Check if existing token is recent (less than 1 hour old)
                        time_since_created = now - created_at.replace(
                            tzinfo=timezone.utc
                        )

                        if (
                            time_since_created.total_seconds() < 3600
                        ):  # Less than 1 hour
                            return None  # Recent pending verification exists

                        # Update existing record with new token (old token expired)
                        cur.execute(
                            "UPDATE links SET token = %s, created_at = %s, verified = FALSE WHERE discord_id = %s",
                            (token, now, discord_id),
                        )
                    else:
                        # Create new record (first time verification)
                        cur.execute(
                            "INSERT INTO links (discord_id, token, created_at, verified) VALUES (%s, %s, %s, FALSE)",
                            (discord_id, token, now),
                        )

                    conn.commit()
                    return token
        except Exception as e:
            print(f"Error creating verification token: {e}")
            return None

    def get_user_status(self, discord_id: int) -> Optional[Tuple[bool]]:
        """Get user verification status."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT verified FROM links WHERE discord_id = %s",
                        (discord_id,),
                    )
                    return cur.fetchone()
        except Exception as e:
            print(f"Error getting user status: {e}")
            return None

    def get_verified_users(self) -> List[Tuple[int, str]]:
        """Get all verified users."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT discord_id, mediawiki_username FROM links WHERE verified = TRUE"
                    )
                    return cur.fetchall()
        except Exception as e:
            print(f"Error getting verified users: {e}")
            return []

    def get_verified_user_ids(self) -> List[int]:
        """Get all verified user IDs."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT discord_id FROM links WHERE verified = TRUE")
                    return [row[0] for row in cur.fetchall()]
        except Exception as e:
            print(f"Error getting verified user IDs: {e}")
            return []

    def purge_old_tokens(self) -> int:
        """Remove old unverified tokens."""
        expiry = datetime.now(timezone.utc) - timedelta(hours=Config.TOKEN_EXPIRY_HOURS)

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM links WHERE verified = FALSE AND created_at < %s",
                        (expiry,),
                    )
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as e:
            print(f"Error purging old tokens: {e}")
            return 0

    def remove_verification(self, discord_id: int) -> bool:
        """Remove verification for a user."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM links WHERE discord_id = %s",
                        (discord_id,),
                    )
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count > 0
        except Exception as e:
            print(f"Error removing verification: {e}")
            return False

    def remove_verification_by_wiki_username(self, mediawiki_username: str) -> bool:
        """Remove verification for a user by their MediaWiki username (case-insensitive)."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM links WHERE mediawiki_username ILIKE %s",
                        (mediawiki_username,),
                    )
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count > 0
        except Exception as e:
            print(f"Error removing verification by wiki username: {e}")
            return False

    def get_mediawiki_username(self, discord_id: int) -> Optional[str]:
        """Get the MediaWiki username for a given Discord user ID (returns as stored)."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT mediawiki_username FROM links WHERE discord_id = %s",
                        (discord_id,),
                    )
                    row = cur.fetchone()
                    return row[0] if row and row[0] else None
        except Exception as e:
            print(f"Error getting MediaWiki username: {e}")
            return None

    def get_discord_id(self, mediawiki_username: str) -> Optional[int]:
        """Get the Discord user ID for a given MediaWiki username (case-insensitive)."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT discord_id FROM links WHERE mediawiki_username ILIKE %s",
                        (mediawiki_username,),
                    )
                    row = cur.fetchone()
                    return row[0] if row and row[0] else None
        except Exception as e:
            print(f"Error getting Discord ID: {e}")
            return None
