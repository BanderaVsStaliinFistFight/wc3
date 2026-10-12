"""World layout for "Shadows over Brightwater".

Everything that both the terrain generator and the game script need to agree
on lives here: map size, player bases, the town, outposts, roads, the river,
forests, creep camps and bosses. Coordinates are in world units (the map
centre is 0, 0; one tile is 128 units).
"""

MAP_NAME = 'Shadows over Brightwater'
MAP_AUTHOR = 'Claude'
SEED = 20261012

WIDTH = 128          # tiles
HEIGHT = 128
BOUNDS = (6, 6, 4, 8)  # left, right, bottom, top margin tiles (World Editor default)
TILESET = 'L'          # Lordaeron Summer

HALF_W = WIDTH * 64
HALF_H = HEIGHT * 64
PLAY_MIN_X = -HALF_W + BOUNDS[0] * 128
PLAY_MAX_X = HALF_W - BOUNDS[1] * 128
PLAY_MIN_Y = -HALF_H + BOUNDS[2] * 128
PLAY_MAX_Y = HALF_H - BOUNDS[3] * 128
CAMERA = (PLAY_MIN_X + 512, PLAY_MIN_Y + 256, PLAY_MAX_X - 512, PLAY_MAX_Y - 256)

# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

USER_PLAYERS = 4
BRIGHTWATER_PLAYER = 4   # allied computer town
SCOURGE_PLAYER = 5       # hostile computer faction

PLAYER_NAMES = ['Red Banner', 'Blue Banner', 'Teal Banner', 'Purple Banner',
                'Brightwater', 'The Scourge']

# Town hall position and gold mine position of each user player.
BASES = [
    {'hall': (-3328, -6208), 'mine': (-3328, -7104)},
    {'hall': (3328, -6208), 'mine': (3328, -7104)},
    {'hall': (-5888, -4672), 'mine': (-6592, -5440)},
    {'hall': (5888, -4672), 'mine': (6592, -5440)},
]

# ---------------------------------------------------------------------------
# Brightwater (allied town)
# ---------------------------------------------------------------------------

TOWN = (0, -5568)
TOWN_RADIUS = 1150
CASTLE = (0, -6080)
TOWN_STRUCTURES = [
    # (unit id, x, y, owner) -- owner 'town' or 'passive'
    ('hcas', 0, -6080, 'town'),
    ('nfoh', 0, -5056, 'passive'),      # Fountain of Health
    ('ngme', -768, -5248, 'passive'),   # Goblin Merchant (consumables)
    ('nmrk', 768, -5248, 'passive'),    # Marketplace, restocked as the Brightwater Armory
    ('nmer', -1024, -6080, 'passive'),  # Mercenary Camp
    ('hgtw', -576, -4544, 'town'),
    ('hgtw', 576, -4544, 'town'),
    ('hatw', 1088, -5696, 'town'),
    ('hhou', 1088, -6272, 'town'),
    ('hhou', 1600, -6016, 'town'),
    ('hhou', -1600, -5568, 'town'),
    ('hbar', -1216, -5120, 'town'),
]
TOWN_GUARDS = [('hfoo', -320, -4800), ('hfoo', 320, -4800), ('hfoo', -192, -5376),
               ('hfoo', 192, -5376), ('hrif', -448, -5760), ('hrif', 448, -5760)]
MILITIA_RALLY = (0, -4864)

# ---------------------------------------------------------------------------
# Outposts: capture them for income. Index order is used by the script.
# ---------------------------------------------------------------------------

OUTPOSTS = [
    {'name': 'Crossroads', 'pos': (0, -1536), 'start': 'wild'},
    {'name': 'Westwatch', 'pos': (-4864, -896), 'start': 'wild'},
    {'name': 'Eastmarch', 'pos': (4864, -896), 'start': 'wild'},
    {'name': 'Northgate', 'pos': (0, 2304), 'start': 'scourge'},
]

# ---------------------------------------------------------------------------
# The Scourge citadel in the north
# ---------------------------------------------------------------------------

CITADEL = (0, 5824)
CITADEL_RADIUS = 1700        # blighted area
RAID_SPAWN = (0, 4736)
SCOURGE_STRUCTURES = [
    ('unp2', 0, 6144),       # Black Citadel -- destroy it to win
    ('uzg1', -704, 5248),
    ('uzg1', 704, 5248),
    ('uzg1', -1344, 5952),
    ('uzg1', 1344, 5952),
    ('ugrv', -1216, 6464),
    ('usep', 1216, 6464),
    ('uzig', -768, 6656),
    ('uzig', 768, 6656),
]
SCOURGE_GUARDS = [('uabo', -320, 5312), ('uabo', 320, 5312), ('ucry', -576, 5632),
                  ('ucry', 576, 5632), ('unec', 0, 5760)]
LICH_POS = (0, 5440)

# ---------------------------------------------------------------------------
# Terrain features
# ---------------------------------------------------------------------------

# Roads: list of polylines (world coords) and half widths.
ROADS = [
    ([(0, -5100), (0, -3328), (0, -1536), (0, 400), (0, 2304), (0, 4736)], 224),
    ([(-500, -5568), (-1700, -5800), (-3328, -6000)], 192),
    ([(500, -5568), (1700, -5800), (3328, -6000)], 192),
    ([(-3328, -6000), (-4700, -5300), (-5888, -4672)], 176),
    ([(3328, -6000), (4700, -5300), (5888, -4672)], 176),
    ([(-5888, -4672), (-5300, -4000), (-4864, -3328), (-4864, -896),
      (-5300, 900), (-5888, 2304)], 176),
    ([(5888, -4672), (5300, -4000), (4864, -3328), (4864, -896),
      (5300, 900), (5888, 2304)], 176),
    ([(0, -1536), (-2400, -1250), (-4864, -896)], 176),
    ([(0, -1536), (2400, -1250), (4864, -896)], 176),
    ([(0, 2304), (-1800, 3200), (-3328, 4352), (-4600, 5100), (-5760, 5760)], 160),
    ([(0, 2304), (1800, 3200), (3328, 4352), (4600, 5100), (5760, 5760)], 160),
]

# The river crosses the map west to east, shallow fords at these x positions.
RIVER_BASE_Y = -3328
FORDS_X = [-4864, 0, 4864]
FORD_HALF_WIDTH = 448
RIVER_HALF_WIDTH = 400

LAKES = [((-2560, 1024), 640, 520), ((2944, -4544), 420, 300)]

# Open areas that must stay free of trees: (x, y, radius)
CLEARINGS = [
    (TOWN[0], TOWN[1], TOWN_RADIUS + 150),
    (CITADEL[0], CITADEL[1], 1550),
] + [(b['hall'][0], b['hall'][1], 1150) for b in BASES] + [
    (b['mine'][0], b['mine'][1], 420) for b in BASES] + [
    (o['pos'][0], o['pos'][1], 760) for o in OUTPOSTS]

# Forest regions: (kind, tree id, density, shape) -- shape is an ellipse
# (cx, cy, rx, ry). Trees also line the playable border.
FORESTS = [
    ('darkwood', 'ATtr', 0.78, (-5200, 1700, 2300, 2100)),
    ('eastwood', 'LTlt', 0.55, (5200, 1700, 2300, 2000)),
    ('blightwood', 'CTtr', 0.62, (0, 5600, 3000, 1700)),
    ('southwest', 'LTlt', 0.60, (-5600, -6600, 1500, 1000)),
    ('southeast', 'LTlt', 0.60, (5600, -6600, 1500, 1000)),
    ('southmid_w', 'LTlt', 0.55, (-1700, -7000, 900, 600)),
    ('southmid_e', 'LTlt', 0.55, (1700, -7000, 900, 600)),
    ('riverbank_w', 'LTlt', 0.40, (-2600, -4000, 1100, 450)),
    ('riverbank_e', 'LTlt', 0.40, (2600, -4000, 1100, 450)),
    ('northwest', 'FTtw', 0.55, (-4300, 3800, 1600, 1100)),
    ('northeast', 'FTtw', 0.55, (4300, 3800, 1600, 1100)),
    ('midfield_w', 'LTlt', 0.30, (-2400, -200, 1300, 900)),
    ('midfield_e', 'LTlt', 0.30, (2400, -200, 1300, 900)),
]

# Lumber groves right next to each base so peasants have trees to cut.
GROVES = [
    ('LTlt', (-4250, -6900, 650, 450)),
    ('LTlt', (-2350, -6950, 600, 420)),
    ('LTlt', (4250, -6900, 650, 450)),
    ('LTlt', (2350, -6950, 600, 420)),
    ('LTlt', (-7000, -4300, 380, 900)),
    ('LTlt', (-5300, -3950, 650, 260)),
    ('LTlt', (7000, -4300, 380, 900)),
    ('LTlt', (5300, -3950, 650, 260)),
]

# Raised rocky ridges (cliff level 3, decorative, no ramps): ellipses.
RIDGES = [
    (-6700, 4400, 520, 900),
    (6700, 4400, 520, 900),
    (-2750, 6550, 600, 330),
    (2750, 6550, 600, 330),
    (-6800, -1900, 420, 700),
    (6800, -1900, 420, 700),
]

# ---------------------------------------------------------------------------
# Creeps (Neutral Hostile). 'respawn' camps come back a few minutes after
# they were cleared. 'outpost' camps guard an outpost and never respawn.
# ---------------------------------------------------------------------------

def _camp(name, x, y, units, respawn=True, outpost=-1):
    return {'name': name, 'pos': (x, y), 'units': units, 'respawn': respawn, 'outpost': outpost}


CAMPS = [
    # South, between the bases and the river (easy)
    _camp('Gnoll Den', -1856, -4416, ['ngno', 'ngno', 'ngna']),
    _camp('Kobold Dig', 1856, -4352, ['nkob', 'nkob', 'nkog']),
    _camp('Spider Hollow', -4480, -4480, ['nspg', 'nspg', 'nspb']),
    _camp('Murloc Shore', 4480, -4480, ['nmrl', 'nmrl', 'nmrr']),
    _camp('Wolf Run', -4992, -7040, ['nwlt', 'nwlt']),
    _camp('Smugglers', 5056, -7040, ['nban', 'nban', 'nbrg']),
    # Outpost guards
    _camp('Crossroads Gnolls', 0, -1280, ['ngnb', 'ngno', 'ngno', 'ngna'], False, 0),
    _camp('Westwatch Trolls', -4864, -640, ['nftr', 'nftr', 'nftt'], False, 1),
    _camp('Eastmarch Brigands', 4864, -640, ['nbrg', 'nbrg', 'nwzr'], False, 2),
    # Middle (medium)
    _camp('Troll Camp', -2368, -2240, ['nftr', 'nftr', 'nfsp']),
    _camp('Gnoll Warband', 2368, -2240, ['ngnb', 'ngns', 'ngnw']),
    _camp('Ogre Patrol', -1536, 128, ['nogr', 'nogr']),
    _camp('Rogue Hideout', 1536, 128, ['nrog', 'nrog', 'nwzr']),
    _camp('Mirror Lake Murlocs', -2560, 1856, ['nmrm', 'nmrm', 'nmrr']),
    _camp('Wolf Pack', 2752, 1088, ['nwlg', 'nwlg', 'nwlt']),
    _camp('Spider Nest', -4096, 1664, ['nssp', 'nssp', 'nsgt']),
    _camp('Dire Wolves', -6400, 576, ['nwld', 'nwlt', 'nwlt']),
    _camp('Furbolg Glade', 4160, 1664, ['nfrl', 'nfrl', 'nfrs']),
    _camp('Highwaymen', 6400, 576, ['nbrg', 'nbrg', 'nrog']),
    # North (hard)
    _camp('Haunted Graveyard', -3328, 4608, ['ngh1', 'ngh1', 'nskg', 'nskg', 'ngh2']),
    _camp('Old Quarry', 3328, 4608, ['ngst', 'ngst', 'ngrk', 'ngrk']),
    _camp('Troll Warband', -2112, 2880, ['nftb', 'nftb', 'nfsh']),
    _camp('Ogre Raiders', 2112, 2880, ['nogm', 'nomg', 'nogr']),
    _camp('Drake Nest', -4736, 4928, ['nrdr', 'nrdk', 'nrdk']),
    _camp('Gnoll Overseer', 4736, 4928, ['ngnv', 'ngnb', 'ngnb']),
]

# Bosses (Neutral Hostile, never respawn). The first unit is the boss.
BOSSES = [
    {'key': 'brood', 'name': 'the Brood Mother', 'pos': (-5888, 2304),
     'units': ['nsbm', 'nsgt', 'nsgt', 'nspg']},
    {'key': 'bandit', 'name': 'the Bandit Lord', 'pos': (5888, 2304),
     'units': ['nbld', 'nenf', 'nass', 'nass']},
    {'key': 'ogre', 'name': 'the Ogre Lord', 'pos': (5760, 5760),
     'units': ['nogl', 'nogm', 'nogm', 'nomg']},
    {'key': 'dragon', 'name': 'the Red Dragon', 'pos': (-5760, 5760),
     'units': ['nrwm', 'nrdr', 'nrdr']},
]

# Signposts and decorations placed by the terrain generator.
SIGNPOSTS = [(-320, -4160), (320, -1984), (-4544, -1280), (4544, -1280), (-320, 1856)]
