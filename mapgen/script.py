"""Generates the data-driven parts of war3map.j from layout.py and splices
them into the hand-written game script (src/war3map.j)."""

import math

from . import layout as L

LAYOUT_MARKER = '//#LAYOUT'
CONFIG_MARKER = '//#CONFIG'


def jstr(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def jreal(v):
    return '%.1f' % float(v)


def layout_function():
    out = ['function InitLayout takes nothing returns nothing']
    a = out.append

    for i, b in enumerate(L.BASES):
        a('    set baseHallX[%d] = %s' % (i, jreal(b['hall'][0])))
        a('    set baseHallY[%d] = %s' % (i, jreal(b['hall'][1])))
        a('    set baseMineX[%d] = %s' % (i, jreal(b['mine'][0])))
        a('    set baseMineY[%d] = %s' % (i, jreal(b['mine'][1])))

    for i, o in enumerate(L.OUTPOSTS):
        a('    set outpostX[%d] = %s' % (i, jreal(o['pos'][0])))
        a('    set outpostY[%d] = %s' % (i, jreal(o['pos'][1])))
        a('    set outpostName[%d] = %s' % (i, jstr(o['name'])))
        a('    set outpostStartsScourge[%d] = %s' % (i, 'true' if o['start'] == 'scourge' else 'false'))
    a('    set outpostCount = %d' % len(L.OUTPOSTS))

    k = 0
    for c, camp in enumerate(L.CAMPS):
        cx, cy = camp['pos']
        a('    set campX[%d] = %s' % (c, jreal(cx)))
        a('    set campY[%d] = %s' % (c, jreal(cy)))
        a('    set campName[%d] = %s' % (c, jstr(camp['name'])))
        a('    set campRespawns[%d] = %s' % (c, 'true' if camp['respawn'] else 'false'))
        a('    set campFirst[%d] = %d' % (c, k))
        a('    set campSize[%d] = %d' % (c, len(camp['units'])))
        n = len(camp['units'])
        for j, uid in enumerate(camp['units']):
            if j == 0 and n >= 3:
                ux, uy = cx, cy
            else:
                ang = 2 * math.pi * j / n + 0.6
                ux, uy = cx + 170 * math.cos(ang), cy + 170 * math.sin(ang)
            a("    set campUnitType[%d] = '%s'" % (k, uid))
            a('    set campUnitX[%d] = %s' % (k, jreal(round(ux))))
            a('    set campUnitY[%d] = %s' % (k, jreal(round(uy))))
            k += 1
    a('    set campCount = %d' % len(L.CAMPS))
    a('    set campUnitCount = %d' % k)

    k = 0
    for b, boss in enumerate(L.BOSSES):
        a('    set bossX[%d] = %s' % (b, jreal(boss['pos'][0])))
        a('    set bossY[%d] = %s' % (b, jreal(boss['pos'][1])))
        a('    set bossName[%d] = %s' % (b, jstr(boss['name'][0].upper() + boss['name'][1:])))
        a('    set bossFirst[%d] = %d' % (b, k))
        a('    set bossSize[%d] = %d' % (b, len(boss['units'])))
        for uid in boss['units']:
            a("    set bossUnitType[%d] = '%s'" % (k, uid))
            k += 1
    a('    set bossCount = %d' % len(L.BOSSES))
    a('    set bossUnitCount = %d' % k)

    for i, (uid, x, y, owner) in enumerate(L.TOWN_STRUCTURES):
        a("    set townStructType[%d] = '%s'" % (i, uid))
        a('    set townStructX[%d] = %s' % (i, jreal(x)))
        a('    set townStructY[%d] = %s' % (i, jreal(y)))
        a('    set townStructPassive[%d] = %s' % (i, 'true' if owner == 'passive' else 'false'))
    a('    set townStructCount = %d' % len(L.TOWN_STRUCTURES))
    for i, (uid, x, y) in enumerate(L.TOWN_GUARDS):
        a("    set townGuardType[%d] = '%s'" % (i, uid))
        a('    set townGuardX[%d] = %s' % (i, jreal(x)))
        a('    set townGuardY[%d] = %s' % (i, jreal(y)))
    a('    set townGuardCount = %d' % len(L.TOWN_GUARDS))

    for i, (uid, x, y) in enumerate(L.SCOURGE_STRUCTURES):
        a("    set scourgeStructType[%d] = '%s'" % (i, uid))
        a('    set scourgeStructX[%d] = %s' % (i, jreal(x)))
        a('    set scourgeStructY[%d] = %s' % (i, jreal(y)))
    a('    set scourgeStructCount = %d' % len(L.SCOURGE_STRUCTURES))
    for i, (uid, x, y) in enumerate(L.SCOURGE_GUARDS):
        a("    set scourgeGuardType[%d] = '%s'" % (i, uid))
        a('    set scourgeGuardX[%d] = %s' % (i, jreal(x)))
        a('    set scourgeGuardY[%d] = %s' % (i, jreal(y)))
    a('    set scourgeGuardCount = %d' % len(L.SCOURGE_GUARDS))

    a('    set castleX = %s' % jreal(L.CASTLE[0]))
    a('    set castleY = %s' % jreal(L.CASTLE[1]))
    a('    set rallyX = %s' % jreal(L.MILITIA_RALLY[0]))
    a('    set rallyY = %s' % jreal(L.MILITIA_RALLY[1]))
    a('    set raidX = %s' % jreal(L.RAID_SPAWN[0]))
    a('    set raidY = %s' % jreal(L.RAID_SPAWN[1]))
    a('    set lichX = %s' % jreal(L.LICH_POS[0]))
    a('    set lichY = %s' % jreal(L.LICH_POS[1]))
    a('endfunction')
    return '\n'.join(out) + '\n'


def start_location(i):
    if i < L.USER_PLAYERS:
        return L.BASES[i]['hall']
    if i == L.BRIGHTWATER_PLAYER:
        return L.CASTLE
    return L.CITADEL


def config_functions(description):
    n = L.USER_PLAYERS + 2
    races = ['RACE_PREF_HUMAN'] * L.USER_PLAYERS + ['RACE_PREF_HUMAN', 'RACE_PREF_UNDEAD']
    lines = []
    a = lines.append
    a('function InitCustomPlayerSlots takes nothing returns nothing')
    for i in range(n):
        controller = 'MAP_CONTROL_USER' if i < L.USER_PLAYERS else 'MAP_CONTROL_COMPUTER'
        colour = 6 if i == L.SCOURGE_PLAYER else i
        a('    // Player %d' % i)
        a('    call SetPlayerStartLocation(Player(%d), %d)' % (i, i))
        a('    call ForcePlayerStartLocation(Player(%d), %d)' % (i, i))
        a('    call SetPlayerColor(Player(%d), ConvertPlayerColor(%d))' % (i, colour))
        a('    call SetPlayerRacePreference(Player(%d), %s)' % (i, races[i]))
        a('    call SetPlayerRaceSelectable(Player(%d), false)' % i)
        a('    call SetPlayerController(Player(%d), %s)' % (i, controller))
    a('endfunction')
    a('')
    a('function InitCustomTeams takes nothing returns nothing')
    defenders = list(range(L.USER_PLAYERS)) + [L.BRIGHTWATER_PLAYER]
    a('    // Force: Defenders of Brightwater')
    for i in defenders:
        a('    call SetPlayerTeam(Player(%d), 0)' % i)
        a('    call SetPlayerState(Player(%d), PLAYER_STATE_ALLIED_VICTORY, 1)' % i)
    for i in defenders:
        for j in defenders:
            if i != j:
                a('    call SetPlayerAllianceStateAllyBJ(Player(%d), Player(%d), true)' % (i, j))
    for i in defenders:
        for j in defenders:
            if i != j:
                a('    call SetPlayerAllianceStateVisionBJ(Player(%d), Player(%d), true)' % (i, j))
    a('    // Force: The Scourge')
    a('    call SetPlayerTeam(Player(%d), 1)' % L.SCOURGE_PLAYER)
    a('endfunction')
    a('')
    a('function config takes nothing returns nothing')
    a('    call SetMapName(%s)' % jstr(L.MAP_NAME))
    a('    call SetMapDescription(%s)' % jstr(description))
    a('    call SetPlayers(%d)' % n)
    a('    call SetTeams(%d)' % n)
    a('    call SetGamePlacement(MAP_PLACEMENT_USE_MAP_SETTINGS)')
    for i in range(n):
        x, y = start_location(i)
        a('    call DefineStartLocation(%d, %s, %s)' % (i, jreal(x), jreal(y)))
    a('    call InitCustomPlayerSlots()')
    a('    call InitCustomTeams()')
    a('endfunction')
    a('')
    return '\n'.join(lines) + '\n'


def main_function():
    l, b, r, t = L.PLAY_MIN_X, L.PLAY_MIN_Y, L.PLAY_MAX_X, L.PLAY_MAX_Y
    bounds = ('%s + GetCameraMargin(CAMERA_MARGIN_LEFT), %s + GetCameraMargin(CAMERA_MARGIN_BOTTOM), '
              '%s - GetCameraMargin(CAMERA_MARGIN_RIGHT), %s - GetCameraMargin(CAMERA_MARGIN_TOP), '
              '%s + GetCameraMargin(CAMERA_MARGIN_LEFT), %s - GetCameraMargin(CAMERA_MARGIN_TOP), '
              '%s - GetCameraMargin(CAMERA_MARGIN_RIGHT), %s + GetCameraMargin(CAMERA_MARGIN_BOTTOM)'
              % (jreal(l), jreal(b), jreal(r), jreal(t), jreal(l), jreal(t), jreal(r), jreal(b)))
    return '\n'.join([
        'function main takes nothing returns nothing',
        '    call SetCameraBounds(%s)' % bounds,
        '    call SetDayNightModels("Environment\\\\DNC\\\\DNCLordaeron\\\\DNCLordaeronTerrain\\\\DNCLordaeronTerrain.mdl", '
        '"Environment\\\\DNC\\\\DNCLordaeron\\\\DNCLordaeronUnit\\\\DNCLordaeronUnit.mdl")',
        '    call NewSoundEnvironment("Default")',
        '    call SetAmbientDaySound("LordaeronSummerDay")',
        '    call SetAmbientNightSound("LordaeronSummerNight")',
        '    call SetMapMusic("Music", true, 0)',
        '    call InitBlizzard()',
        '    call InitGame()',
        'endfunction',
        '',
    ])


def build_script(template, description):
    """Returns (full war3map.j, custom script for the World Editor)."""
    lines = template.replace('\r\n', '\n').split('\n')
    if lines.count(LAYOUT_MARKER) != 1 or lines.count(CONFIG_MARKER) != 1:
        raise ValueError('script template must contain each marker once, on its own line')
    assert [b['key'] for b in L.BOSSES] == ['brood', 'bandit', 'ogre', 'dragon']

    def splice(config):
        out = []
        for line in lines:
            if line == LAYOUT_MARKER:
                out.append(layout_function())
            elif line == CONFIG_MARKER:
                out.append(config)
            else:
                out.append(line)
        return '\n'.join(out).rstrip() + '\n'

    custom = splice('')
    full = splice(config_functions(description) + main_function())
    return full.replace('\r\n', '\n').replace('\n', '\r\n'), custom.replace('\r\n', '\n').replace('\n', '\r\n')


WE_INIT_TRIGGER = (
    'function InitTrig_Init takes nothing returns nothing\r\n'
    '    call InitGame()\r\n'
    'endfunction\r\n'
)
