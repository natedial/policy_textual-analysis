# Database Setup Guide

## Setting Up Supabase

### 1. Create Supabase Project

1. Go to https://supabase.com
2. Sign up / Log in
3. Click "New Project"
4. Choose a name (e.g., "fed-tracker")
5. Set a strong database password (save this!)
6. Choose a region (closest to you)
7. Click "Create new project"

Wait ~2 minutes for provisioning.

### 2. Run Schema Migration

1. In your Supabase dashboard, go to **SQL Editor** (left sidebar)
2. Click **"New query"**
3. Copy the entire contents of `schema.sql`
4. Paste into the SQL editor
5. Click **"Run"** (or press Cmd/Ctrl + Enter)

You should see: "Success. No rows returned"

### 3. Verify Tables Created

Go to **Table Editor** in the sidebar. You should see:
- `speakers` (with 7 seed speakers)
- `speeches`
- `fingerprints`
- `detected_shifts`

### 4. Get Database Credentials

Go to **Project Settings** → **Database**

You'll need:
- **Connection String** (URI format)
- Or individual values:
  - Host
  - Database name
  - Port
  - User
  - Password

### 5. Configure Application

Add to your `.env` file:

```bash
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-anon-key-here
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.your-project-ref.supabase.co:5432/postgres
```

**Finding your keys:**
- `SUPABASE_URL` and `SUPABASE_KEY`: **Project Settings** → **API**
- `DATABASE_URL`: **Project Settings** → **Database** → Connection string (URI mode)

### 6. Install Python Dependencies

```bash
source venv/bin/activate
pip install supabase psycopg2-binary
```

### 7. Test Connection

```bash
python -c "from supabase import create_client, Client; import os; supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY')); print(supabase.table('speakers').select('*').execute())"
```

You should see the 7 seed speakers.

## Schema Overview

### Core Tables

**speakers**: Fed officials
- Stores name, title, institution
- Seeded with current Board members

**speeches**: Raw content
- URL, speaker, date, type
- Full text from HTML/PDF
- Deduplication via unique URL constraint

**fingerprints**: Semantic analysis
- Linked to speech
- JSON themes (stance, trajectory, emphasis, etc.)
- Tracks model version and prompt version for reproducibility

**detected_shifts**: Comparison results
- Links two speeches via their fingerprints
- Stores all detected shifts as JSON
- Summary counts for quick filtering

### Useful Queries

**Get all Powell speeches:**
```sql
SELECT * FROM speeches
WHERE speaker_name = 'Jerome H. Powell'
ORDER BY speech_date DESC;
```

**Find speeches with fingerprints:**
```sql
SELECT * FROM recent_speeches_with_fingerprints
WHERE speaker_name = 'Jerome H. Powell';
```

**Get high-significance shifts only:**
```sql
SELECT * FROM high_significance_shifts
WHERE speaker_name = 'Jerome H. Powell';
```

**Track inflation stance over time:**
```sql
SELECT
  s.speech_date,
  s.title,
  f.themes->'INFLATION'->>'stance' as stance,
  (f.themes->'INFLATION'->>'emphasis_score')::int as emphasis
FROM fingerprints f
JOIN speeches s ON f.speech_id = s.id
WHERE s.speaker_name = 'Jerome H. Powell'
  AND f.themes ? 'INFLATION'
ORDER BY s.speech_date;
```

## Next Steps

After setting up the database:
1. Run the ingestion script to add your first speech
2. Verify fingerprint extraction works
3. Test shift detection with two speeches
4. Build out the Streamlit UI

See `README.md` for application usage instructions.
