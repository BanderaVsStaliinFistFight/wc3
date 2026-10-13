#!/usr/bin/env python3
"""Builds dist/ShadowsOverBrightwater.w3x from the sources in this repository.

Usage: python3 build.py [--preview]

Only the Python standard library is needed.
"""

import os
import sys

from mapgen import formats as F
from mapgen import hero as H
from mapgen import layout as L
from mapgen import script as S
from mapgen.mpq import MpqWriter
from mapgen.terrain import Terrain

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'dist', 'ShadowsOverBrightwater.w3x')

DESCRIPTION = ('Co-op RPG and strategy for 1-4 players. Raise a hero, build your base, '
               'claim outposts for income and destroy the Scourge citadel in the north '
               'before its raids overwhelm Brightwater.')
LOADING_TEXT = ('Pick a hero and lead your town hall, peasants and army.\n'
                'Clear creep camps for experience and loot, take the four outposts for income '
                'and finish side quests from the quest log (F9).\n'
                'Every few minutes the Scourge raids the castle, your bases or your outposts. '
                'Slay Kel\'Thuzad and raze the Black Citadel to win; lose Brightwater Castle and all is lost.\n'
                'Dark Iron Thane model based on "King" by Tranquil (hiveworkshop.com).')

FLAGS = (F.W3I_MASKED_PARTIALLY_VISIBLE | F.W3I_FIXED_PLAYER_SETTINGS | F.W3I_CUSTOM_FORCES
         | F.W3I_PROPERTIES_OPENED | F.W3I_WAVES_CLIFF | F.W3I_WAVES_ROLLING
         | F.W3I_REQUIRES_EXPANSION | F.W3I_ITEM_CLASSIFICATION)


def map_info():
    defenders = 0
    for i in range(L.USER_PLAYERS):
        defenders |= 1 << i
    defenders |= 1 << L.BRIGHTWATER_PLAYER
    players = []
    for i in range(L.USER_PLAYERS + 2):
        x, y = S.start_location(i)
        players.append({
            'id': i,
            'type': F.PLAYER_USER if i < L.USER_PLAYERS else F.PLAYER_COMPUTER,
            'race': F.RACE_UNDEAD if i == L.SCOURGE_PLAYER else F.RACE_HUMAN,
            'name': L.PLAYER_NAMES[i],
            'start': (x, y),
        })
    cam = L.CAMERA
    return {
        'name': L.MAP_NAME,
        'author': L.MAP_AUTHOR,
        'description': DESCRIPTION,
        'players_recommended': '1-4 (co-op)',
        # bottom-left, top-right, top-left, bottom-right
        'camera_bounds': [cam[0], cam[1], cam[2], cam[3], cam[0], cam[3], cam[2], cam[1]],
        'bounds_complements': list(L.BOUNDS),
        'playable_width': L.WIDTH - L.BOUNDS[0] - L.BOUNDS[1],
        'playable_height': L.HEIGHT - L.BOUNDS[2] - L.BOUNDS[3],
        'flags': FLAGS,
        'tileset': L.TILESET,
        'loading_title': L.MAP_NAME,
        'loading_subtitle': 'A co-op RPG with strategy',
        'loading_text': LOADING_TEXT,
        'players': players,
        'forces': [
            {'flags': F.FORCE_ALLIED | F.FORCE_ALLIED_VICTORY | F.FORCE_SHARE_VISION,
             'players': defenders, 'name': 'Defenders of Brightwater'},
            {'flags': F.FORCE_ALLIED | F.FORCE_ALLIED_VICTORY,
             'players': 1 << L.SCOURGE_PLAYER, 'name': 'The Scourge'},
        ],
    }


def build(preview=False, out=OUT, quiet=False):
    terrain = Terrain()
    for w in terrain.warnings:
        print('warning:', w, file=sys.stderr)

    with open(os.path.join(ROOT, 'src', 'war3map.j'), encoding='utf-8') as f:
        template = f.read()
    script, custom_script = S.build_script(template, DESCRIPTION)

    units = []
    for i in range(L.USER_PLAYERS + 2):
        x, y = S.start_location(i)
        units.append({'id': 'sloc', 'x': x, 'y': y, 'z': terrain.ground_z(x, y), 'player': i})

    minimap = terrain.render(256)
    files = [
        ('war3map.w3i', F.w3i(map_info())),
        ('war3map.w3e', F.w3e(terrain)),
        ('war3map.wpm', F.wpm(terrain.width, terrain.height, terrain.pathing)),
        ('war3map.shd', F.shd(terrain.width, terrain.height)),
        ('war3map.doo', F.doo(terrain.doodads)),
        ('war3mapUnits.doo', F.units_doo(units)),
        ('war3map.mmp', F.mmp(terrain.minimap_icons())),
        ('war3mapMap.blp', F.blp1_paletted(minimap, 256)),
        ('war3map.w3r', F.w3r()),
        ('war3map.w3c', F.w3c()),
        ('war3map.w3s', F.w3s()),
        ('war3map.wtg', F.wtg('Shadows over Brightwater', 'Init',
                              'Starts the game. The game code lives in the custom script section.')),
        ('war3map.wct', F.wct('', custom_script, [S.WE_INIT_TRIGGER])),
        ('war3map.j', script.encode('utf-8')),
    ]
    # the custom hero: model, texture, icons, object data and import list
    files += sorted(H.files().items())

    mpq = MpqWriter()
    for name, data in files:
        mpq.add(name, data)
    header = F.map_header(L.MAP_NAME, FLAGS, L.USER_PLAYERS)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'wb') as f:
        f.write(header + mpq.build())
    if not quiet:
        print('wrote %s (%d bytes, %d doodads)' % (os.path.relpath(out, ROOT), os.path.getsize(out), len(terrain.doodads)))

    if preview:
        size = 768
        path = os.path.join(ROOT, 'docs', 'overview.png')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(F.png(terrain.render(size, markers=True), size, size))
        print('wrote %s' % os.path.relpath(path, ROOT))
    return out, terrain


if __name__ == '__main__':
    build(preview='--preview' in sys.argv)
