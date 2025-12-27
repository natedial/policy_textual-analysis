"""
Database integration for Fed Textual Change Tracker.
Handles all interactions with Supabase/PostgreSQL.
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


class Database:
    """Database client for Fed speech tracking."""

    def __init__(self, supabase_url: str = None, supabase_key: str = None):
        """
        Initialize database connection.

        Args:
            supabase_url: Supabase project URL (defaults to env var)
            supabase_key: Supabase anon key (defaults to env var)
        """
        self.url = supabase_url or os.getenv("SUPABASE_URL")
        self.key = supabase_key or os.getenv("SUPABASE_KEY")

        if not self.url or not self.key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY must be set in environment or passed to constructor"
            )

        self.client: Client = create_client(self.url, self.key)

    # =========================================================================
    # SPEAKERS
    # =========================================================================

    def get_or_create_speaker(self, name: str, title: str = None, institution: str = None) -> int:
        """
        Get speaker ID, creating if doesn't exist.

        Args:
            name: Speaker full name
            title: Title (e.g., "Chair")
            institution: Institution (e.g., "Board of Governors")

        Returns:
            Speaker ID
        """
        # Try to find existing
        result = self.client.table("speakers").select("id").eq("name", name).execute()

        if result.data:
            return result.data[0]["id"]

        # Create new
        result = self.client.table("speakers").insert({
            "name": name,
            "title": title,
            "institution": institution
        }).execute()

        return result.data[0]["id"]

    # =========================================================================
    # SPEECHES
    # =========================================================================

    def speech_exists(self, url: str) -> bool:
        """Check if speech URL already in database."""
        result = self.client.table("speeches").select("id").eq("url", url).execute()
        return len(result.data) > 0

    def insert_speech(
        self,
        url: str,
        speaker_name: str,
        speech_date: date,
        raw_text: str,
        title: str = None,
        speech_type: str = None,
        source: str = None,
        content_type: str = "html"
    ) -> int:
        """
        Insert a new speech.

        Args:
            url: Speech URL
            speaker_name: Full name of speaker
            speech_date: Date of speech
            raw_text: Cleaned speech text
            title: Speech title
            speech_type: Type (speech/statement/press_conference/interview)
            source: Source (e.g., "Board of Governors")
            content_type: html or pdf

        Returns:
            Speech ID
        """
        # Get or create speaker
        speaker_id = self.get_or_create_speaker(speaker_name)

        # Calculate word count
        word_count = len(raw_text.split())

        # Insert speech
        result = self.client.table("speeches").insert({
            "url": url,
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "title": title,
            "speech_date": speech_date.isoformat(),
            "speech_type": speech_type,
            "source": source,
            "content_type": content_type,
            "raw_text": raw_text,
            "word_count": word_count
        }).execute()

        return result.data[0]["id"]

    def get_speech(self, speech_id: int) -> Optional[Dict[str, Any]]:
        """Get speech by ID."""
        result = self.client.table("speeches").select("*").eq("id", speech_id).execute()
        return result.data[0] if result.data else None

    def get_speeches_by_speaker(
        self,
        speaker_name: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent speeches by speaker.

        Args:
            speaker_name: Full speaker name
            limit: Max number to return

        Returns:
            List of speech records
        """
        result = (
            self.client.table("speeches")
            .select("*")
            .eq("speaker_name", speaker_name)
            .order("speech_date", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data

    # =========================================================================
    # FINGERPRINTS
    # =========================================================================

    def insert_fingerprint(
        self,
        speech_id: int,
        themes: Dict[str, Any],
        policy_implications: Dict[str, Any],
        overall_tone: str,
        raw_llm_response: str = None,
        model_version: str = "claude-sonnet-4-20250514",
        prompt_version: str = "v1.0"
    ) -> int:
        """
        Insert semantic fingerprint for a speech.

        Args:
            speech_id: ID of speech
            themes: Theme dictionary (from extract.py)
            policy_implications: Policy implications dict
            overall_tone: Overall tone string
            raw_llm_response: Raw LLM output for debugging
            model_version: Model used for extraction
            prompt_version: Prompt version used

        Returns:
            Fingerprint ID
        """
        result = self.client.table("fingerprints").insert({
            "speech_id": speech_id,
            "themes": themes,
            "policy_implications": policy_implications,
            "overall_tone": overall_tone,
            "raw_llm_response": raw_llm_response,
            "model_version": model_version,
            "prompt_version": prompt_version
        }).execute()

        return result.data[0]["id"]

    def get_fingerprint(self, fingerprint_id: int) -> Optional[Dict[str, Any]]:
        """Get fingerprint by ID."""
        result = self.client.table("fingerprints").select("*").eq("id", fingerprint_id).execute()
        return result.data[0] if result.data else None

    def get_fingerprint_for_speech(self, speech_id: int) -> Optional[Dict[str, Any]]:
        """Get most recent fingerprint for a speech."""
        result = (
            self.client.table("fingerprints")
            .select("*")
            .eq("speech_id", speech_id)
            .order("extraction_date", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    # =========================================================================
    # DETECTED SHIFTS
    # =========================================================================

    def insert_detected_shifts(
        self,
        speech_a_id: int,
        speech_b_id: int,
        fingerprint_a_id: int,
        fingerprint_b_id: int,
        shifts: List[Dict[str, Any]]
    ) -> int:
        """
        Insert detected shifts between two speeches.

        Args:
            speech_a_id: Earlier speech ID
            speech_b_id: Later speech ID
            fingerprint_a_id: Earlier fingerprint ID
            fingerprint_b_id: Later fingerprint ID
            shifts: List of shift objects (from compare.py)

        Returns:
            Detected shifts ID
        """
        # Calculate summary stats
        high_count = sum(1 for s in shifts if s.get("significance") == "HIGH")
        medium_count = sum(1 for s in shifts if s.get("significance") == "MEDIUM")
        low_count = sum(1 for s in shifts if s.get("significance") == "LOW")

        result = self.client.table("detected_shifts").insert({
            "speech_a_id": speech_a_id,
            "speech_b_id": speech_b_id,
            "fingerprint_a_id": fingerprint_a_id,
            "fingerprint_b_id": fingerprint_b_id,
            "shifts": shifts,
            "total_shifts": len(shifts),
            "high_significance_count": high_count,
            "medium_significance_count": medium_count,
            "low_significance_count": low_count
        }).execute()

        return result.data[0]["id"]

    def get_high_significance_shifts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent high-significance shifts."""
        result = (
            self.client.table("high_significance_shifts")
            .select("*")
            .limit(limit)
            .execute()
        )
        return result.data

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def get_recent_speeches_with_fingerprints(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent speeches with their fingerprints."""
        result = (
            self.client.table("recent_speeches_with_fingerprints")
            .select("*")
            .limit(limit)
            .execute()
        )
        return result.data

    def get_speaker_timeline(
        self,
        speaker_name: str,
        theme: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get timeline of speeches for a speaker, optionally filtered by theme.

        Args:
            speaker_name: Full speaker name
            theme: Optional theme to filter by (e.g., "INFLATION")

        Returns:
            List of speeches with fingerprints, ordered by date
        """
        query = (
            self.client.table("recent_speeches_with_fingerprints")
            .select("*")
            .eq("speaker_name", speaker_name)
        )

        result = query.execute()

        speeches = result.data

        # Filter by theme if specified
        if theme:
            speeches = [
                s for s in speeches
                if s.get("themes") and theme in s["themes"]
            ]

        return sorted(speeches, key=lambda x: x["speech_date"])


if __name__ == "__main__":
    # Test connection
    db = Database()
    print("✅ Database connection successful!")

    # Test queries
    speakers = db.client.table("speakers").select("*").execute()
    print(f"\n📊 Found {len(speakers.data)} speakers in database")

    recent = db.get_recent_speeches_with_fingerprints(limit=5)
    print(f"📄 Found {len(recent)} recent speeches")
