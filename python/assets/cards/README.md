# Card Asset Contract (Downloaded Pack)

Blackjack now uses the downloaded card pack in:

- `python/assets/cards/medium_cards`

Required files:

- `card_back.png`
- 52 face files in this naming format:
  - `card_<suit>_<rank>.png`

Suit names:

- `spades`, `hearts`, `diamonds`, `clubs`

Rank format:

- `A`, `J`, `Q`, `K`, `10`
- `02` to `09` (zero-padded for 2-9)

Examples:

- `card_spades_A.png`
- `card_hearts_10.png`
- `card_clubs_J.png`
- `card_diamonds_07.png`

Notes:

- The game script (`python/games/blackjack.py`) validates these files at startup.
- Images are auto-scaled to `96x140` at runtime.
