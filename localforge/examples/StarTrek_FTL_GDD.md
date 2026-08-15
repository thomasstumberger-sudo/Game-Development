# STAR TREK: FINAL FRONTIER
### Game Design Document v0.1

---

## 1. OVERVIEW

**Genre:** Roguelike Strategy / Tactical Simulation
**Tone:** Star Trek TNG/DS9 era — moral weight, diplomatic complexity, action as a last resort
**Core Inspiration:** FTL: Faster Than Light — sector maps, ship systems, crew management, real-time-with-pause combat
**Key Divergence:** Where FTL defaults to combat, Star Trek: Final Frontier defaults to *contact*. The most powerful tool on your ship isn't a phaser bank — it's your hailing frequency.

### Elevator Pitch
You command a starship on a deep-space assignment. The journey is procedurally generated across sectors of the galaxy. Every encounter offers a choice: talk, investigate, intervene, or fight. Combat is always an option, but never the only one — and it carries costs that diplomacy doesn't. Fail your mission and the ship is lost. Succeed and new vessels, factions, and galaxy regions unlock for future runs.

---

## 2. CORE DESIGN PILLARS

**1. Contact Before Combat**
Every hostile encounter should have a non-combat resolution path. The player should feel *clever* for talking their way out, not cheated for wanting to fight.

**2. The Crew Are Characters**
Officers are named, specialized, and morally reactive. Losing a named crew member is a genuine loss, not just a stat reduction. Crew can *disagree* with the captain's choices.

**3. Decisions With Memory**
Actions in one sector echo in later sectors. Faction reputation persists across the run. Burn a Ferengi trade post and Ferengi ships will be hostile three sectors later.

**4. The Ship Is Alive**
Your vessel has personality through its systems, its logs, and its sounds. The bridge feels like a workplace, not just a UI screen.

**5. Unlocks Feel Like Lore**
Every new ship, faction, and region unlocked has a backstory reason. Nothing is arbitrary — unlocks extend the universe.

---

## 3. STRUCTURE OF A RUN

### 3.1 Mission Assignment

At the start of each run, the player receives a mission briefing from Starfleet Command. This sets the destination sector and the macro-objective. Examples:

- Investigate the disappearance of a science vessel near the Badlands
- Negotiate a ceasefire between two pre-warp civilizations before they achieve FTL
- Escort a Cardassian defector to Deep Space Nine
- Respond to a distress signal inside Romulan Neutral Zone — without triggering an incident

Missions vary in difficulty, sector count, and secondary objective availability. Harder missions unlock if shorter ones are completed successfully.

### 3.2 The Sector Map

The galaxy is divided into **Sectors** — each one a node-based map identical in structure to FTL's layout. The player travels from node to node, choosing their path, managing resources, and reaching the sector exit to advance.

**Sector Types:**
| Type | Flavor | Dominant Faction | Tone |
|------|--------|-----------------|------|
| Federation Space | Familiar, safe-ish | Starfleet | Tutorial/low threat |
| Bajoran Corridor | Post-occupation tension | Mixed | Political, asymmetric |
| Klingon Border | Honor culture, constant posturing | Klingon Empire | Combat-heavy if careless |
| Romulan Neutral Zone | Paranoid, cloaked threats | Romulan Star Empire | Stealth/intel emphasis |
| Cardassian Territory | Bureaucracy and surveillance | Cardassian Union | Negotiation/deception |
| Deep Space Expanse | Unknown species, anomalies | None | Exploration/discovery |
| The Badlands | Plasma storms, rogue factions | Maquis | Chaos, off-the-books |
| Borg Space | Existential dread | The Collective | Horror tier — endgame only |

Sectors are unlocked progressively. New runs add sector variety.

### 3.3 Encounter Nodes

Each node on the sector map is one of the following types, with some nodes marked by icon and some hidden until arrival:

- **Contact Node** — A ship, station, or settlement initiates contact
- **Anomaly Node** — A scientific phenomenon to investigate
- **Distress Signal** — A vessel or colony in crisis
- **Faction Base** — A station belonging to a known faction (shop, quest, rest)
- **Debris Field** — Salvage opportunity, possible trap
- **Temporal/Spatial Anomaly** — Special event with exotic narrative payoff
- **Empty Space** — A rest/repair opportunity, sometimes with random flavor event
- **Ambush Node** — Hostile engagement, no hailing preamble

---

## 4. THE CONTACT SYSTEM

This is the game's signature mechanic — the *hailing encounter* — replacing FTL's combat-or-flee binary with a full social engagement layer.

### 4.1 The Hailing Screen

When a contact node is entered, a **Hailing Screen** opens. It displays:

- The contact's ship/structure (visual render)
- Their faction and threat level (estimated by sensors)
- Opening dialogue from their commanding officer
- Your response options (see below)

### 4.2 Response Options

Responses are generated from your ship's current **Diplomatic Posture**, **Crew Composition**, and **Reputation** with that faction. Options may include:

- **Hail / Open Hailing Frequencies** — Neutral opener, begins dialogue tree
- **Identify** — Use sensors to learn more before committing to an approach
- **Offer Aid** — Spend resources (medical, food, power) to de-escalate
- **Request Information** — Gather intel; may reveal mission-relevant data
- **Invoke Regulation / Prime Directive** — Starfleet protocol deflection
- **Bluff / Deceive** — Attempt subterfuge; officer Cunning skill applies
- **Threaten** — Display of force; may resolve instantly or escalate
- **Red Alert** — Skip dialogue, go directly to Combat
- **Warp Out** — Disengage at a fuel cost; sometimes not permitted

Each option has a success probability influenced by:
- Relevant officer stationed at the Bridge console
- Current ship damage (a damaged ship signals weakness)
- Faction reputation score
- Story context (are you in their territory uninvited?)

### 4.3 Dialogue Trees

Hailing encounters use a condensed branching dialogue format. Conversations are not infinitely long — typically 2-4 exchanges before a resolution is forced. The player must read tone and make decisions under time pressure (the encounter has an ambient tension meter — delay too long and the contact may act unilaterally).

Key Star Trek archetypes are scripted as encounter types:
- The Suspicious Klingon Warrior (prove worth through challenge)
- The Cardassian Bureaucrat (paper trail, jurisdiction games)
- The Borg Cube (no dialogue — special encounter only)
- The Unknown Alien (Universal Translator calibration mini-game)
- The Maquis Cell (political sympathy or antagonism based on player history)
- The Romulan Commander (game of veiled threats and inference)
- The Desperate Refugee Ship (moral weight, scarce resources)
- The Con Artist Posing as a Freighter (Deception skill check)

### 4.4 Away Missions

Some contact nodes escalate to an **Away Mission** — a boarding or ground action. These are resolved as a **text-based tactical encounter** with visual flavor art, not a separate action game.

Away Mission structure:
1. Player selects 1-3 crew members for the team (transporter beam-down)
2. The away team navigates 3-6 decision nodes (each a brief narrative beat)
3. Skill checks determine outcomes at each node
4. Crew can be injured, captured, or killed — or can resolve things peacefully
5. Rewards: intelligence, resources, rescued crew, story resolution

Away missions are *optional in most cases* but unlock better rewards and faction rep.

---

## 5. COMBAT SYSTEM

Combat exists and is fully functional — but the game frames it as a failure state of diplomacy in many cases, and a necessary tool in others.

### 5.1 Combat Structure

Combat is **real-time with pause** (identical to FTL's model).

The player manages:
- **Weapon targeting** — assign weapons to specific enemy systems
- **Shield management** — regenerating forward/aft shields
- **Power allocation** — distribute energy across systems in real-time
- **Crew assignments** — move crew to stations to boost system performance
- **Special abilities** — officer abilities, ship abilities, consumables

### 5.2 Star Trek Combat Flavor

**Weapons:**
| Weapon Class | Behavior | Notes |
|---|---|---|
| Phaser Arrays | Sustained beam; drains shields gradually | Federation default |
| Photon Torpedoes | Burst damage; bypasses partial shields | Limited ammo |
| Disruptors | Penetrating; damages systems, not just HP | Klingon/Romulan |
| Tractor Beam | Disables enemy movement/evasion | Support weapon |
| Cloaking Device | Not a weapon; breaks targeting lock | Romulan/unlock |
| Transphasic Torpedo | Anti-Borg; huge damage, rare | Late-game unlock |

**Ship Systems:**
| System | Function |
|---|---|
| Shields | Absorb incoming damage; regenerates when crew mans station |
| Weapons | Fire rate and power determined by energy allocation |
| Impulse Drive | Evasion percentage; damaged drive = easier to hit |
| Warp Core | Powers all systems; breach = catastrophic |
| Transporter | Away missions; boarding enemy vessels |
| Sensors | Reveals hidden enemy system damage; targeting precision |
| Sickbay | Auto-heals crew injuries over time |
| Science Lab | Passive: reveals anomalies; active: sensor lock on enemies |
| Holodeck | (Advanced) Distraction/deception options in combat |

### 5.3 Boarding

The player can beam crew onto enemy ships to disable systems from within — mirroring FTL's boarding mechanic with Star Trek flavor:

- Security officers fight enemy crew in corridors
- Engineers can sabotage warp cores
- Science officers can *disable* rather than destroy (earns Humanitarian bonus)
- Captured enemy crew can be interrogated for intel

### 5.4 Defeat Conditions

Enemy ships can be:
- **Destroyed** — Resources gained; reputation may suffer with faction
- **Disabled** — Preferred outcome; can then be hailed, boarded, or allowed to drift
- **Surrendered** — Some ships will hail and yield when heavily damaged

---

## 6. THE CREW

### 6.1 Officer Roles

Each ship has a set of **named officer slots** corresponding to classic Star Trek bridge stations:

| Station | Primary Skill | Secondary Skill |
|---|---|---|
| Captain (Player) | Command | Variable |
| First Officer | Command / Diplomacy | Crew morale management |
| Helm | Piloting | Evasion in combat |
| Tactical | Weapons | Boarding leadership |
| Engineering | Repair speed | Warp core efficiency |
| Science | Sensors / Anomaly analysis | Deception resistance |
| Medical | Crew healing | Morale recovery |
| Security | Boarding / anti-boarding | Interrogation |
| Counselor | Diplomatic insight | Crew morale buffer |

The starting Federation ship fills most slots. Some must be recruited during the run.

### 6.2 Crew Traits

Each officer has:
- **Skill Level** (1-5) in their primary and secondary areas
- **Species Trait** — Vulcans are resistant to bluffing; Betazoids sense deception; Klingons boost combat morale; Ferengi give trade discounts
- **Moral Alignment** — Officers have a Federation/Pragmatic/Ruthless axis; choices that violate their alignment reduce their effectiveness and may trigger crew conflict events
- **Backstory Beat** — A short personal narrative that can unlock a unique event or ability during the run

### 6.3 Crew Events

Periodically, a **Crew Event** fires between encounters:
- An officer requests to speak with the captain (personal mission thread)
- A conflict between two crew members requires mediation
- A crew member's species triggers a cultural event in a sector
- An officer with relevant backstory is recognized by an NPC

These events are non-combat, brief (1-3 choices), and affect morale, relationships, and sometimes plot.

### 6.4 Morale

Morale is a ship-wide resource (0-100). High morale improves skill check probabilities. Low morale triggers:
- Officers performing below their skill level
- Crew refusing certain orders
- Possible defection or mutiny in extreme cases

Morale increases via: successful missions, crew events resolved well, shore leave at friendly stations.
Morale decreases via: crew deaths, morally questionable decisions, extended combat, resource scarcity.

---

## 7. RESOURCES

| Resource | Acquired From | Spent On |
|---|---|---|
| Dilithium | Asteroid mining, trade, salvage | Warp jumps, weapon power |
| Replicator Matter | Trade posts, salvage | Food, equipment, away mission gear |
| Crew | Rescue, recruitment | Station manning, away missions |
| Medical Supplies | Starbases, events | Crew healing, aid diplomacy |
| Intelligence Data | Sensor sweeps, interrogation, events | Unlocking hidden nodes, faction bribes |
| Reputation (per faction) | Diplomatic successes, quest completion | Access to faction stations, unlock crew |

---

## 8. SHIPS

### 8.1 Starting Ship: USS Vanguard (Excelsior-class)

The default run ship. Balanced loadout, good diplomatic tools, moderate combat capability. Designed to make every system tutorial-accessible.

**Default Loadout:**
- Phaser arrays x2 (fore/aft)
- Photon torpedo launcher x1
- Standard shields
- Full bridge crew (8 slots)
- One empty crew slot for run recruitment

### 8.2 Unlock Progression

Ships are unlocked by achieving specific conditions during runs:

| Ship | Class | Faction | Unlock Condition |
|---|---|---|---|
| USS Vanguard | Excelsior | Federation | Default |
| USS Archon | Defiant-class | Federation | Complete a run defending DS9 |
| IKS Vor'cha | Vor'cha Attack Cruiser | Klingon | Complete a run as a Klingon ally |
| IRW Talon | D'deridex Warbird | Romulan | Survive 3 Romulan sectors undetected |
| Maquis Raider | Modified freighter | Maquis | Defect to Maquis in a Federation run |
| Ferengi Marauder | D'Kora | Ferengi | Achieve max wealth in a single run |
| Kazon Raider | Predator-class | Kazon | Complete a run in the Delta Quadrant (late unlock) |
| Borg Sphere | Sphere | Collective | Secret unlock — assimilation playthrough |

Each faction ship changes the gameplay loop substantially:
- Klingon ships have no Counselor; morale replaced by *Honor* system
- Romulan ships have Cloaking but reduced Diplomacy options
- Ferengi ships have expanded Trade mechanics, reduced combat
- Borg Sphere has no crew — drone system; no diplomacy whatsoever

### 8.3 Ship Upgrades

Between sectors, at starbases or faction stations, the player can:
- Install new weapons systems (slot-based; ship has limited hardpoints)
- Upgrade existing systems (tier 1-3)
- Add crew quarters (increases crew cap)
- Install special modules (science lab, holodecks, enhanced transporters)
- Repair hull damage

Upgrades are purchased with Dilithium and/or faction reputation.

---

## 9. FACTIONS & REPUTATION

### 9.1 Reputation Scale

Each major faction tracks a reputation score from -100 to +100.

| Range | Status | Effect |
|---|---|---|
| 75 to 100 | Allied | Favorable prices, aid in combat, unique quests |
| 25 to 74 | Friendly | Access to faction stations |
| -24 to 24 | Neutral | No bonuses or penalties |
| -25 to -74 | Hostile | Faction ships initiate combat on contact |
| -75 to -100 | Enemy | Shoot-on-sight; bounty placed on player ship |

### 9.2 Major Factions

**United Federation of Planets** — Starting ally. Reputation damaged by Prime Directive violations, civilian casualties, and treaty breaks. Boosted by humanitarian aid, successful diplomacy, and mission completion.

**Klingon Empire** — Honor-based reputation. Boosted by combat victories, keeping oaths, accepting challenges. Damaged by retreat, deception, dishonoring the dead.

**Romulan Star Empire** — Intelligence-based reputation. Boosted by showing strategic cunning, respecting their secrecy. Damaged by entering their space uninvited, sharing their intelligence with other factions.

**Cardassian Union** — Bureaucratic reputation. Boosted by following proper channels, bribing officials. Damaged by exposing their operations, supporting Bajoran resistance.

**Ferengi Alliance** — Commerce reputation. Boosted by profitable trades, honoring contracts. Damaged by charity, refusing profit opportunities.

**The Maquis** — Ideological reputation. Boosted by opposing Cardassian occupation, bending Starfleet rules. Cannot be simultaneously Allied with both Maquis and Cardassian factions.

**The Dominion** — Late-game faction. No reputation possible — always hostile until specific story unlocks. End-game antagonist for certain mission types.

---

## 10. NARRATIVE EVENTS

### 10.1 Event Categories

Events fire at nodes and have branching outcomes. Categories:

- **First Contact** — Encounter an uncharted species. Choices shape their perception of the Federation for the rest of the run.
- **Moral Dilemma** — A no-good-answer scenario (rescue 10 at the cost of the mission, or press on). Affects crew morale and Starfleet reputation.
- **Time Anomaly** — Temporal mechanics event; paradox choices with weird consequences.
- **Political Crisis** — Two factions on the edge of war; player's intervention tips the balance.
- **Personal Log** — A crew member's backstory event fires; their personal arc advances.
- **Distress Signal** — A ship or colony in crisis. Aid them (cost resources) or pass (gain time, lose reputation).
- **The Kobayashi Maru** — A no-win scenario event that fires once per run; tests player values, not skill.

### 10.2 The Captain's Log

Between encounters, the game generates a short **Captain's Log entry** summarizing recent events in Starfleet prose. This serves as:
- A narrative digest of choices made
- A lore delivery mechanism
- A record of the run's story for end-screen display

Captain's Log entries are AI-generated using the player's actual decisions as input — giving each run a unique narrative voice.

---

## 11. THE PRIME DIRECTIVE

The Prime Directive functions as a **second-order reputation system** — distinct from faction reputation. It measures how strictly the player adheres to Starfleet ethical doctrine.

**Prime Directive Score (0-100):**
- High score: Starfleet offers special commendations, better starting loadouts in future runs
- Low score: Tribunal event may fire mid-run; Starfleet ships may turn hostile; unlocks morally grey mission types

**Examples of Prime Directive violations:**
- Sharing advanced technology with pre-warp civilizations
- Intervening in the internal affairs of sovereign species
- Using deception against non-combatants
- Assisting one side in a civil conflict

Some missions *require* Prime Directive violations. Others punish them. The tension is intentional.

---

## 12. WIN / LOSE CONDITIONS

### 12.1 Run Failure
- Warp core breach / ship destruction
- All crew lost (skeleton crew warning at 2 remaining)
- Mission-critical objective failed (escort killed, defector captured, etc.)

On failure, the run ends. A debrief screen shows how far the player got, reputation earned, and any permanent unlocks triggered.

### 12.2 Run Victory
- Reach the final sector and complete the mission objective
- Survive the final encounter (not necessarily a combat)

Victory triggers an end-screen Captain's Log, debrief, and permanent unlock processing.

### 12.3 Permanent Unlocks
Earned across runs, stored between runs:
- New ships (see Section 8.2)
- New officer types (species previously not available)
- New sector types (expand the map pool)
- New mission types
- Lore entries (the Codex — an in-game encyclopedia of species and events)

---

## 13. UI / UX FRAMEWORK

### 13.1 Main Screens

**Sector Map** — Node-based overhead view of current sector. Shows path, visited nodes, and visible upcoming nodes. Faction territory color-coded.

**Bridge View** — The primary gameplay screen. A stylized overhead schematic of your ship showing all compartments, crew positions, and system health. Identical in function to FTL's ship view.

**Hailing Screen** — Full-screen contact interface. Speaker portrait, dialogue text, response options. Visual design varies by faction (Federation clean blue, Klingon red-gold, Romulan dark green, etc.).

**Away Mission Screen** — Text adventure frame with faction-themed art panel. Shows the team, the location, and decision nodes.

**Starbase Screen** — Docked interface for upgrades, crew recruitment, and trade.

**Captain's Log** — Journal view; collects all auto-generated logs for the run.

**Codex** — Unlockable encyclopedia of species, factions, ships, and events.

### 13.2 Visual Language

The aesthetic targets the LCARS interface system (the orange/blue Okudagram panels from TNG). Functional, dense, technical — but readable. Color coding carries information rather than decoration.

- **Federation UI:** Blue-dominant LCARS, clean lines
- **Klingon UI:** Red/bronze, angular, heavier typography
- **Romulan UI:** Dark green, geometric, bird-of-prey motifs
- **Borg UI:** Black/green, corrupted LCARS, scan-line distortion

---

## 14. AUDIO DESIGN

- **Bridge Ambience:** Each ship class has a distinct ambient loop (Federation hum, Klingon percussion drones, Romulan silence-with-occasional-chirp)
- **Tactical Alert:** The classic Red Alert klaxon fires on combat entry
- **Communicator Beeps:** UI interaction sounds drawn from series sound design
- **Contact Music:** Faction-themed musical motifs during hailing encounters
- **Combat Music:** Dynamic tension track that escalates with hull damage
- **Victory / Defeat:** Debrief sequences scored appropriately

---

## 15. IMPLEMENTATION PHASES

### Phase 1 — Core Loop (MVP)
- Sector map navigation
- Basic contact system (hailing with 3-4 response types)
- Combat (FTL-style, Federation ship only)
- 3 sector types (Federation Space, Klingon Border, Deep Space Expanse)
- 5 crew roles
- Resource management (Dilithium, Crew, Medical)
- Basic reputation (Federation and Klingon only)
- Win/lose conditions

### Phase 2 — Star Trek Identity
- Full hailing dialogue trees (6 faction types)
- Away mission system
- Captain's Log (manual, not AI-generated)
- 5 additional sector types
- Full 9-role crew system
- Morale system
- Prime Directive score
- First two ship unlocks

### Phase 3 — Depth & Replayability
- Full faction roster (7 factions)
- Full ship unlock tree (8 ships)
- AI-generated Captain's Log
- Codex / lore system
- Full event library (50+ event types)
- Crew backstory events
- Temporal anomaly events
- Kobayashi Maru event

### Phase 4 — Endgame
- Borg Space sector
- Dominion faction
- Borg Sphere unlock
- Final mission types
- Prestige run modifiers

---

## 16. OPEN DESIGN QUESTIONS

These require decisions before implementation begins:

1. **Pause or turn-based combat?** FTL's real-time-with-pause works well but is complex to implement. A turn-based variant would be simpler and arguably more Star Trek (Captain Picard thinks before acting).

2. **How much text?** Away missions as text adventures can be rich but slow. How long should individual narrative beats be?

3. **Crew permadeath or injury system?** FTL has permadeath. Star Trek culture avoids killing named characters casually. An injury/recovery system may fit the IP better.

4. **Captain character creation or fixed protagonist?** Fixed captain (canonical Starfleet officer) vs. custom captain (species, background, moral axis).

5. **Multiplayer potential?** A two-player co-op run where one player commands combat and one handles diplomacy would be deeply on-brand.

6. **Browser-based or native app?** Browser (HTML5/React) is fast to iterate; native (Godot, Unity) gives more depth. Given your existing stack, browser-first seems correct.

---

*Document version 0.1 — Initial design pass. All systems subject to revision.*
