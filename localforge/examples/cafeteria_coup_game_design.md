# Game Design Document: Cafeteria Coup (Working Title)

> **Core Elevator Pitch:** A fast-paced, proactive real-time stealth-heist game combining the room-manipulation puzzles of *Golden Sun*, the chaotic sandbox physics of *Streets of Rogue*, and the snarky insult-based debate system of *Secret of Monkey Island*. 
> You play as an ambitious Thief/Wizard who infiltrates high-security Archmage towers to steal legendary artifacts—not to save the world, but to win a seat on the Mage Council and fix the abysmal, sludge-filled menu in the university cafeteria.

---

## 1. World & Narrative Premise

* **The Academic Scam:** At the Grand Arcane Academy, formal classes are entirely optional because magic automates everything. Rather than educating students, the Mage Council maintains a petty, rigid hierarchy powered by vanity titles, merit points, and grandstanding.
* **The Petty Crusade:** While the Archmages hoard university funds for vanity projects and giant useless relics, the student body lives on cold gruel and magic sludge. You take an oath to infiltrate the Council and vote through budget reforms for the cafeteria.
* **The Pride Cover-Up:** Archmages cannot report stolen artifacts without admitting security flaws and facing public ridicule. When you steal a relic, they pretend nothing happened while secretly panic-buying absurd, over-compensating security upgrades for their towers.

---

## 2. Core Gameplay Loop

The game is built around a structured **3-Stage Heist Loop** with a mandatory return trip:

```
[ 1. Library Intel ] ➔ [ 2. Key Extraction ] ➔ [ 3. Tower Heist (Act 1) ]
                                                            │
[ 5. Council Trial ] ⇦ [ 4. The Return Trip (Act 3) ] ⇦ [ Intermission: Duels ]
```

### Stage 1: The Library (Intel & Social Hub)
* Infiltrate the restricted archives of the main campus library to steal the logbook containing the location of the Archmage’s master key.
* Interact with and roast snobby students in the stacks to log new academic comebacks into your notebook.

### Stage 2: Key Extraction (The Side Heist)
* Infiltrate specialized campus sub-locations (e.g., Botanical Gardens, Clocktower, Grand Kitchens) to steal the one-of-a-kind key required to bypass the target Archmage's unpickable vault lock.

### Stage 3: The Tower Heist (Act 1 - Infiltration)
* A sprawling, vertical multi-floor layout with non-linear navigation (e.g., balcony entries, sewer vents, servant halls).
* Use low-level utility spells, thief tools, and environmental manipulation to bypass security, steal the artifact, and escape.

### Intermission: Campus Duels & Insult Learning
* Challenge arrogant student spellcasters in the quad.
* Cast your newly stolen, giant useless artifact to flex. The student mocks your terrible/useless spell, dropping a top-tier academic roast. Your character logs the roast and its counter-comeback in their notebook.

### Stage 4: The Return Trip (Act 3 - Replacement)
* **The Twist:** You must sneak *back* into the tower and put the artifact back on its pedestal so the Archmage can flex it at the upcoming trial without knowing it was ever compromised.
* **Dynamic Remapping:** The tower's layout and guard behaviors are dynamically remapped based on your specific actions during Act 1 (see *Adaptive Security* below).

### Stage 5: The Mage Council Trial (Climax)
* Face the Archmages in a courtroom duel using **Arcane Filibustering** (Monkey Island insult mechanics).
* Slam down stolen artifacts as "Visual Punctuation" to force room silence, then drop learned comebacks to shatter the Council's egos and win your seat.

---

## 3. Thief Tools & Low-Level Utility Spells

Instead of passive waiting, stealth relies on proactive chaos manipulation through tool-spell synergies:

| Tool / Spell | Function | Systemic Combo Example |
| :--- | :--- | :--- |
| **Mage Hand** | Remote manipulation | Deploy physical lockpicks or drag tripwires across halls from hiding. |
| **Grease** | Creates slick surfaces | Cast *Gust* to slide heavy busts across greased floors like curling stones into guards. |
| **Douse / Freeze** | Liquid & temperature control | Throw a smoke bomb, *Douse* it with water, then *Freeze* it into a solid ice block doorway seal. |
| **Silence / Noisemaker** | Acoustic control | Set timed mechanical noisemakers; cast *Silence* to break glass right behind a guard's head. |
| **Reveal + Glass Cutter** | Sensory & physical bypassing | Use *Reveal* to highlight magic tripwires, then use physical wire-snips to disable rune housings. |

---

## 4. The "Alibi Engine" System

Getting spotted can be leveraged strategically using delayed-action mechanics:

1. **The Plant:** Set a 5-minute timed clockwork noisemaker or melting ice-rune trap near a target vault.
2. **The Position:** Walk out into a public courtyard while Heat is low.
3. **The Witness:** Force eye-contact with an NPC, start a public student duel, or engage an Archmage in a lengthy conversation.
4. **The Trigger & Check:** The trap detonates. The AI runs an alibi check, registers you were standing right in front of witnesses, and clears you of all suspicion.
5. **The Vacuum:** Guards rush away to investigate the distraction, leaving the tower completely unguarded for a clean break-in window.

---

## 5. Useless Legendary Artifact Spells

Stealing artifacts rewards the player with giant, absurdly over-engineered vanity spells that offer zero practical combat/stealth value:

* **Radiant Resuscitation of the Eternal Sun (The Phoenix Paradox):**
  * *Effect:* Summons a blinding, roaring spectral phoenix that fully restores health in a pillar of holy fire.
  * *Catch:* Can only be cast while dead. Prompt on death screen: `[Press 'F' to cast Phoenix (Unavailable: You are dead)]`.
  * *Use:* Used to flex in duels to bait students into roasting your useless spell formula.
* **Titan's Majestic Stature (The Human Doorstop):**
  * *Effect:* Expands physical size by 800% with dramatic bass-drop sound effects.
  * *Catch:* Movement speed drops to 0; cannot fit through doorways or low ceilings. You expand until wedged solid against walls/ceiling for the full duration.
  * *Tactical Use:* Act as a giant cork in narrow corridors to block pursuing guards while *Mage Hand* picks a door lock behind you.

---

## 6. Adaptive Security (Act 3 Return Trip)

The target tower's security updates in direct response to your specific Act 1 playstyle:

| Player Action in Act 1 | Archmage's Paranoia Response in Act 3 | Tactical Shift required for Return Trip |
| :--- | :--- | :--- |
| Knocked out guards with crowbars | Guards wear iron bucket helmets & neck collars | Melee knockouts fail; must use environmental traps. |
| Ghosted level without alerts | Paranoid over-patrol with glowing lantern-eye true-sight | Shadow paths blocked; must create loud chaos/distractions. |
| Used *Grease* on floorboards | Heated floor runes & guards wear heavy spiked cleats | Slippery hazards turned into damaging lava floors. |
| Used *Mage Hand* on locks | Keyholes coated in sticky anti-magic sap | *Mage Hand* fizzles on contact; must pick locks in person. |
| Used sound distractions / traps | Guards wear enchanted noise-canceling earmuffs | Guards immune to noise; but can't hear you sprinting behind them. |
