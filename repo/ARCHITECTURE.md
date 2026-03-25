# Overview
Building an AI-driven Text-based RPG Discord Bot connected to the Monster Harvesting API. The bot allows users to choose classes, generate AI-driven stories, hunt monsters, and join cooperative multiplayer sessions with a refined, fair co-op system.

# Project Type
BACKEND (FastAPI + Discord Bot + LLM Integration)

# Success Criteria
- **Onboarding:** Users can use `/help` to understand all mechanics and commands.
- **World & Class Selection:** Users first pick an open-license RPG universe, then pick a class (Mage, Warrior, Archer).
- **AI Narrative:** `/story` generates a unique AI scenario based on the chosen universe.
- **Combat:** `/hunt` runs a fair, stats-based combat loop.
- **Co-op (Refined):** Two distinct co-op modes (Observer and Active). `/leaveW` mid-fight applies a Deserter Curse. Block message for guest spam has a per-fight cooldown.

# Tech Stack
- **FastAPI**: Core API, shared logic and data access.
- **SQLAlchemy & SQLite/PostgreSQL**: Persists Users, Characters, Sessions, and Deserter states.
- **discord.py (pycord)**: Slash commands and interaction handling.
- **LLM (OpenAI/Gemini)**: Dynamic `/story` generation using open-domain world contexts.

# Command Reference (Full Design)

| Command | Who Can Use | Description |
|---|---|---|
| `/help` | Anyone | Explains all commands, classes, and world systems |
| `/start` | New users | Character creation flow (Pick World → Pick Class) |
| `/story` | Character owners | Generates AI scenario for their current world context |
| `/hunt` | Character owners | Initiates a solo monster encounter |
| `/joinW @user` | Any character | Joins another user's world in Observer Mode |
| `/leaveW` | Guests | Exits the host's world. Applies Deserter Curse if done mid-fight |
| `/fightcoop` | Guests in Observer Mode | Activates Active Co-op Mode for the current/next fight |
| `/co-hunt` | Host only | Initiates a hunt while a guest is in Active Co-op Mode |

# Co-op State Machine

```
Guest: /joinW @host
       │
       ▼
┌─────────────────────────┐
│  OBSERVER MODE          │  ← Guest earns 30% passive XP from host kills
│  /fightcoop unlocked    │
└──────────┬──────────────┘
           │ Guest: /fightcoop
           ▼
┌─────────────────────────┐
│  ACTIVE CO-OP MODE      │  ← Both fight together; host win% boosted
│  Host chooses all actions│  ← Guest auto-mirrors silently
│  Guest commands BLOCKED │  ← Block msg sent ONCE per fight (cooldown), then silently ignored
└──────────┬──────────────┘
           │ /leaveW (any time)
           ▼
┌─────────────────────────┐
│  DESERTER CURSE         │  ← Guest's next solo fight: monster is 1 tier stronger
│  Guest returns to own   │
│  world automatically    │
│  Host reverts to solo % │
└─────────────────────────┘
```

# RPG Universe Options (Open-License Only)
To avoid copyright issues and allow future monetization:
- **High Fantasy** — Swords, dragons, elves. Generic, public domain archetypes.
- **Cosmic Horror** — Lovecraftian monsters and eldritch dread. (Cthulhu Mythos is public domain.)
- **Norse Mythology** — Gods, giants, Yggdrasil. Fully public domain.
- **Cyberpunk Underworld** — Generic sci-fi dystopia, no specific IP.

# Combat & Progression System (Finalized)

### Character Base Stats
- **Mage:** 40 HP | 13 + level AC | Primary: Wisdom
- **Warrior:** 70 HP | 15 + level AC | Primary: Strength
- **Archer:** 55 HP | 14 + level AC | Primary: Agility
- **Luck:** All classes roll for Luck. Higher Luck = better item drop chance & critical hit chance.
- *Initialization:* Stats roll 4d6 (drop lowest) and are mathematically clamped (e.g., 8 to 16) to avoid players being wildly overpowered or instantly killed.

### Combat Mechanics
- **Turn Order:** Initiative roll (d20 + Agility). Higher score attacks first.
- **Hit Check:** d20 + Level vs Target AC (Player or Monster).
- **Damage Formula:** `WeaponDice + PrimaryStat`.
- **Critical Hit:** Natural 20 on the d20 roll = automatic hit and `2x WeaponDice + PrimaryStat`.

### Weapons & Progression
- **Starter Gear:** Players receive a Tier 1 weapon appropriate for their class upon creation (Staff, Shortsword, or Shortbow).
- **Weapon Categories:** 30 total weapons spread across 4 categories (STR, AGI, WIS, Hybrid STR/WIS).
- **Monster Tiers:** 5 tiers total (6 monsters per tier). Players max at Level 10.
- **XP Scaling:** You earn full XP from monsters in your tier. Grinding monsters significantly below your level halves the XP gained.
- **Death Penalty:** Dropping to 0 HP costs 10% of your current level's XP (you never drop down a level) and auto-heals you to full.
- **Healing:** `/rest` command has a 1-hour cooldown. (Potions will be added later for instant healing).

# File Structure
```text
├── main.py
├── database.py
├── models.py
├── schemas.py
├── routers/
│   ├── items.py
│   ├── monsters.py
│   └── users.py
├── bot/
│   ├── bot_main.py
│   └── cogs/
│       ├── system.py    # /help, /start
│       ├── rpg.py       # Universe + class picking
│       ├── hunt.py      # /hunt, combat engine
│       ├── coop.py      # /joinW, /leaveW, /fightcoop, /co-hunt, Deserter Curse
│       └── ai_story.py  # /story
└── requirements.txt
```

# Task Breakdown
### Phase 0: Database (database-architect)
- **Task 1**: Models for `User`, `Character` (class + stats), `WorldSession` (host_id, guest_id, mode: OBSERVER/ACTIVE), `DeserterState`.

### Phase 1: Core API (backend-specialist)
- **Task 2**: Character creation endpoints (world selection → class selection).
- **Task 3**: `combat_engine.py` — stat-based fight resolution, observer XP%, active co-op win% boost, tier scaling for Deserter Curse.

### Phase 2: Discord Bot Foundation (backend-specialist)
- **Task 4**: Bot setup, `/help` embed with full command reference, `/start` character creation flow.

### Phase 3: AI & Game Features (backend-specialist)
- **Task 5**: `/story` LLM integration using chosen open-license universe as LLM system prompt context.
- **Task 6**: `/hunt` and solo combat loop.
- **Task 7**: Full co-op system — Observer Mode (passive XP %), Active Mode (host priority, guest blocked with cooldown), `/leaveW` with Deserter Curse.

# Phase X: Verification
- Lint: [ ]
- Security: [ ]
- Build: [ ]
- Date: [ ]
