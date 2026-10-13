"""The map's own heroes, two Dark Iron dwarves built on the Mountain King (so
they keep his voice, attack and armour). Each has his own model and four
abilities: stock ones renamed and re-iconed, so their balance stays the
game's own.

- The Dark Iron Thane (H000): mapgen/dwarf.py, fire versions of the
  Mountain King's abilities
- The Dark Iron Brawler (H001): mapgen/brawler.py, a bare-fisted brawler
"""

from . import brawler, dwarf
from . import objects as O

THANE_ID = 'H000'
THANE_NAME = 'Dark Iron Thane'
BRAWLER_ID = 'H001'
BRAWLER_NAME = 'Dark Iron Brawler'

CMD = 'ReplaceableTextures\\CommandButtons\\'
PAS = 'ReplaceableTextures\\PassiveButtons\\'
GOLD = '|cffffcc00'


def _levels(field, texts):
    return [(field, O.STRING, level, 0, text) for level, text in enumerate(texts, 1)]


def _ability(base, new, name, label, hotkey, levels, ubertip, research_ubertip, art, research_art):
    """label is the name with its hotkey letter highlighted; ubertip(level)
    gives each level's description."""
    tips = ['Activate %s' % label] if levels == 1 else \
        ['%s - [%sLevel %d|r]' % (label, GOLD, i) for i in range(1, levels + 1)]
    mods = [('anam', O.STRING, name),
            ('aret', O.STRING, 'Learn %s - [%sLevel %%d|r]' % (label, GOLD)),
            ('arut', O.STRING, research_ubertip),
            ('ahky', O.STRING, hotkey),
            ('arhk', O.STRING, hotkey),
            ('aart', O.STRING, art),
            ('arar', O.STRING, research_art)]
    return (base, new, mods + _levels('atp1', tips) + _levels('aub1', [ubertip(i) for i in range(1, levels + 1)]))


def _per_level(text, levels=3):
    return ' |n|n' + ' |n'.join('%sLevel %d|r - %s' % (GOLD, i, text(i)) for i in range(1, levels + 1))


# -- the Dark Iron Thane: the Mountain King's abilities, set on fire --------

THANE_ABILITIES = [
    _ability('AHtb', 'A000', 'Molten Hammer', 'Mol%st|ren Hammer' % GOLD, 'T', 3,
             lambda i: 'Hurls a hammer glowing from the forge at a target enemy unit, dealing <A000,DataA%d> damage '
                       'and stunning the target for <A000,Dur%d> seconds.' % (i, i),
             'A hammer glowing from the forge, hurled at an enemy unit to burn and stun it.'
             + _per_level(lambda i: '<A000,DataA%d> damage, <A000,Dur%d> second stun.' % (i, i)),
             CMD + 'BTNFireBolt.blp', CMD + 'BTNFireBolt.blp'),
    _ability('AHtc', 'A001', 'Fire Stomp', '%sF|rire Stomp' % GOLD, 'F', 3,
             lambda i: 'Slams the ground with the heat of the Molten Core, dealing <A001,DataA%d> damage to nearby '
                       'enemy land units and slowing their movement by <A001,DataC%d,%%>%% and attack rate by '
                       '<A001,DataD%d,%%>%%.' % (i, i, i),
             'Slams the ground, scorching nearby enemy land units and slowing their movement and attack rate.'
             + _per_level(lambda i: '<A001,DataA%d> damage.' % i),
             CMD + 'BTNWallOfFire.blp', CMD + 'BTNWallOfFire.blp'),
    _ability('AHbh', 'A002', 'Searing Blows', 'Searing %sB|rlows' % GOLD, 'B', 3,
             lambda i: 'Gives a <A002,DataA%d>%% chance that an attack will sear for <A002,DataC1> bonus damage and '
                       'stun an opponent for <A002,Dur1> seconds.' % i,
             'Gives a chance that an attack will sear for <A002,DataC1> bonus damage and stun an opponent for '
             '<A002,Dur1> seconds.' + _per_level(lambda i: '<A002,DataA%d>%% chance per attack.' % i),
             PAS + 'PASBTNIncinerate.blp', CMD + 'BTNIncinerate.blp'),
    _ability('AHav', 'A003', 'Avatar of Flame', 'A%sv|ratar of Flame' % GOLD, 'V', 1,
             lambda i: 'Wreathes the Thane in the fire of Ragnaros, giving <A003,DataA1> bonus armor, <A003,DataB1> '
                       'bonus hit points, <A003,DataC1> bonus damage and spell immunity. |nLasts <A003,Dur1> seconds.',
             'When Avatar of Flame is activated, it gives the Thane <A003,DataA1> bonus armor, <A003,DataB1> bonus '
             'hit points, <A003,DataC1> bonus damage and spell immunity. |nLasts <A003,Dur1> seconds.',
             CMD + 'BTNHeroAvatarOfFlame.blp', CMD + 'BTNHeroAvatarOfFlame.blp'),
]

# -- the Dark Iron Brawler: a keg, his fists, and a spin ---------------------

BRAWLER_ABILITIES = [
    _ability('ANdh', 'A004', 'Dark Iron Ale', '%sD|rark Iron Ale' % GOLD, 'D', 3,
             lambda i: 'Hurls a keg of Dark Iron Ale at enemy units, drenching them so that their movement speed is '
                       'reduced by <A004,DataC%d,%%>%% and they have a <A004,DataB%d,%%>%% chance to miss on attacks. '
                       '|nLasts <A004,Dur%d> seconds.' % (i, i, i),
             'Hurls a keg of Dark Iron Ale at enemy units, slowing them and making them miss on attacks. '
             '|nLasts <A004,Dur1> seconds.'
             + _per_level(lambda i: '<A004,DataC%d,%%>%% movement speed reduction, <A004,DataB%d,%%>%% miss chance.'
                          % (i, i)),
             CMD + 'BTNStrongDrink.blp', CMD + 'BTNStrongDrink.blp'),
    _ability('AOws', 'A005', 'Ground Slam', '%sG|rround Slam' % GOLD, 'G', 3,
             lambda i: 'Slams the ground with both fists, dealing <A005,DataA%d> damage to nearby enemy land units '
                       'and stunning them for <A005,Dur%d> seconds.' % (i, i),
             'Slams the ground with both fists, stunning and damaging nearby enemy land units.'
             + _per_level(lambda i: '<A005,DataA%d> damage, <A005,Dur%d> second stun.' % (i, i)),
             CMD + 'BTNWarStomp.blp', CMD + 'BTNWarStomp.blp'),
    _ability('ANic', 'A006', 'Burning Knuckles', 'Burning %sK|rnuckles' % GOLD, 'K', 3,
             lambda i: 'Each punch carries the flames of the Shadowforge, which cling to the target. They add '
                       '<A006,DataA%d> damage on the first attack, twice as much on the second, three times as much '
                       'on the third, and so on.|n|nIf a unit dies while burning, it is incinerated, dealing up to '
                       '<A006,DataB%d> damage to all nearby enemy units.' % (i, i),
             'Each punch carries flames that cling to the target and burn hotter with every attack. A unit that '
             'dies while burning is incinerated, damaging nearby enemy units.'
             + _per_level(lambda i: '<A006,DataA%d> bonus damage, <A006,DataB%d> incineration damage.' % (i, i)),
             PAS + 'PASBTNImmolation.blp', CMD + 'BTNImmolationOn.blp'),
    _ability('AOww', 'A007', 'Iron Cyclone', 'Iron %sC|ryclone' % GOLD, 'C', 1,
             lambda i: 'Spins into a whirlwind of iron fists, becoming immune to magic and dealing <A007,DataA1> '
                       'damage per second to nearby enemy land units. |nLasts <A007,Dur1> seconds.',
             'Spins into a whirlwind of iron fists, becoming immune to magic and dealing <A007,DataA1> damage per '
             'second to nearby enemy land units.',
             CMD + 'BTNWhirlwind.blp', CMD + 'BTNWhirlwind.blp'),
]

ABILITIES = THANE_ABILITIES + BRAWLER_ABILITIES


def _hero(new, name, proper_names, model, icon, abilities, description, extra=()):
    """The hotkey is the first letter of the last word of the name."""
    first, last = name.rsplit(' ', 1)
    hotkey = last[0]
    label = '%s %s%s|r%s' % (first, GOLD, hotkey, last[1:])
    return ('Hmkg', new, [
        ('unam', O.STRING, name),
        ('upro', O.STRING, ','.join(proper_names)),
        ('upru', O.INT, len(proper_names)),
        ('umdl', O.STRING, model),
        ('uico', O.STRING, icon),
        ('uhab', O.STRING, ','.join(a for _, a, _ in abilities)),
        ('utip', O.STRING, 'Summon %s' % label),
        ('utpr', O.STRING, 'Revive %s' % label),
        ('uawt', O.STRING, 'Revive %s' % label),
        ('uhot', O.STRING, hotkey),
        ('utub', O.STRING, description + ' |n|n%sAttacks land units.|r' % GOLD),
    ] + list(extra))


UNITS = [
    _hero(THANE_ID, THANE_NAME,
          ['Dagran Ironfoe', 'Bael Grimstone', 'Hurley Blackforge', 'Thelgar Embermaul', 'Argus Coalbeard',
           'Brokk Cinderfist', 'Hargun Slagjaw', 'Morgas Ashenhammer'],
          dwarf.MODEL_PATH, dwarf.ICON_PATH, THANE_ABILITIES,
          'Warrior Hero of the Shadowforge, wielding the fire of the mountain. Can learn Molten Hammer, Fire Stomp, '
          'Searing Blows and Avatar of Flame.'),
    _hero(BRAWLER_ID, BRAWLER_NAME,
          ['Rorgun Slagfist', 'Durm Blackbrew', 'Grimbol Ironjaw', 'Kragg Coalbelly', 'Thalgar Emberknuckle',
           'Ogrin Ashbrew', 'Barek Cindertooth', 'Mordin Grimale'],
          brawler.MODEL_PATH, brawler.ICON_PATH, BRAWLER_ABILITIES,
          'Warrior Hero from the Grim Guzzler, who settles every argument with his bare fists. Can learn Dark Iron '
          'Ale, Ground Slam, Burning Knuckles and Iron Cyclone.',
          # quicker and lighter on his feet than the Mountain King, a little less sturdy
          [('ustr', O.INT, 22), ('ustp', O.UNREAL, 2.7),
           ('uagi', O.INT, 16), ('uagp', O.UNREAL, 1.8),
           ('uint', O.INT, 13), ('uinp', O.UNREAL, 1.3)]),
]


def files():
    """The archive files for the heroes: models, portraits, textures, icons,
    object data and the import list."""
    assets = dict(dwarf.build())
    assets.update(brawler.build())
    out = dict(assets)
    out['war3map.w3u'] = O.w3u(UNITS)
    out['war3map.w3a'] = O.w3a(ABILITIES)
    out['war3map.imp'] = O.imp(sorted(assets))
    return out
