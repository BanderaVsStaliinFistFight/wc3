"""The Dark Iron Thane: a custom hero built on the Mountain King, with his
own model, icon and four fire-themed abilities (the Mountain King's, renamed
and re-iconed, so their balance stays the game's own)."""

from . import dwarf
from . import objects as O

HERO_ID = 'H000'
HERO_NAME = 'Dark Iron Thane'

PROPER_NAMES = ['Dagran Ironfoe', 'Bael Grimstone', 'Hurley Blackforge', 'Thelgar Embermaul', 'Argus Coalbeard',
                'Brokk Cinderfist', 'Hargun Slagjaw', 'Morgas Ashenhammer']

CMD = 'ReplaceableTextures\\CommandButtons\\'
PAS = 'ReplaceableTextures\\PassiveButtons\\'


def _levels(field, texts):
    return [(field, O.STRING, level, 0, text) for level, text in enumerate(texts, 1)]


def _ability(base, new, name, hotkey, tips, ubertips, research_ubertip, art, research_art):
    mods = [('anam', O.STRING, name),
            ('aret', O.STRING, 'Learn %s - [|cffffcc00Level %%d|r]' % hotkey),
            ('arut', O.STRING, research_ubertip),
            ('aart', O.STRING, art),
            ('arar', O.STRING, research_art)]
    return (base, new, mods + _levels('atp1', tips) + _levels('aub1', ubertips))


def _tips(label, count):
    if count == 1:
        return ['Activate %s' % label]
    return ['%s - [|cffffcc00Level %d|r]' % (label, i) for i in range(1, count + 1)]


ABILITIES = [
    _ability('AHtb', 'A000', 'Molten Hammer', '|cffffcc00M|rolten Hammer',
             _tips('|cffffcc00M|rolten Hammer', 3),
             ['Hurls a hammer glowing from the forge at a target enemy unit, dealing <A000,DataA%d> damage and '
              'stunning the target for <A000,Dur%d> seconds.' % (i, i) for i in range(1, 4)],
             'A hammer glowing from the forge, hurled at an enemy unit to burn and stun it. |n|n'
             '|cffffcc00Level 1|r - <A000,DataA1> damage, <A000,Dur1> second stun. |n'
             '|cffffcc00Level 2|r - <A000,DataA2> damage, <A000,Dur2> second stun. |n'
             '|cffffcc00Level 3|r - <A000,DataA3> damage, <A000,Dur3> second stun.',
             CMD + 'BTNFireBolt.blp', CMD + 'BTNFireBolt.blp'),
    _ability('AHtc', 'A001', 'Fire Stomp', '|cffffcc00F|rire Stomp',
             _tips('|cffffcc00F|rire Stomp', 3),
             ['Slams the ground with the heat of the Molten Core, dealing <A001,DataA%d> damage to nearby enemy land '
              'units and slowing their movement by <A001,DataC%d,%%>%% and attack rate by <A001,DataD%d,%%>%%.'
              % (i, i, i) for i in range(1, 4)],
             'Slams the ground, scorching nearby enemy land units and slowing their movement and attack rate. |n|n'
             '|cffffcc00Level 1|r - <A001,DataA1> damage. |n'
             '|cffffcc00Level 2|r - <A001,DataA2> damage. |n'
             '|cffffcc00Level 3|r - <A001,DataA3> damage.',
             CMD + 'BTNWallOfFire.blp', CMD + 'BTNWallOfFire.blp'),
    _ability('AHbh', 'A002', 'Searing Blows', '|cffffcc00S|rearing Blows',
             _tips('|cffffcc00S|rearing Blows', 3),
             ['Gives a <A002,DataA%d>%% chance that an attack will sear for <A002,DataC1> bonus damage and stun an '
              'opponent for <A002,Dur1> seconds.' % i for i in range(1, 4)],
             'Gives a chance that an attack will sear for <A002,DataC1> bonus damage and stun an opponent for '
             '<A002,Dur1> seconds. |n|n'
             '|cffffcc00Level 1|r - <A002,DataA1>% chance per attack. |n'
             '|cffffcc00Level 2|r - <A002,DataA2>% chance per attack. |n'
             '|cffffcc00Level 3|r - <A002,DataA3>% chance per attack.',
             PAS + 'PASBTNIncinerate.blp', CMD + 'BTNIncinerate.blp'),
    _ability('AHav', 'A003', 'Avatar of Flame', 'Avatar of |cffffcc00F|rlame',
             _tips('Avatar of |cffffcc00F|rlame', 1),
             ['Wreathes the Thane in the fire of Ragnaros, giving <A003,DataA1> bonus armor, <A003,DataB1> bonus hit '
              'points, <A003,DataC1> bonus damage and spell immunity. |nLasts <A003,Dur1> seconds.'],
             'When Avatar of Flame is activated, it gives the Thane <A003,DataA1> bonus armor, <A003,DataB1> bonus '
             'hit points, <A003,DataC1> bonus damage and spell immunity. |nLasts <A003,Dur1> seconds.',
             CMD + 'BTNHeroAvatarOfFlame.blp', CMD + 'BTNHeroAvatarOfFlame.blp'),
]

UNITS = [
    ('Hmkg', HERO_ID, [
        ('unam', O.STRING, HERO_NAME),
        ('upro', O.STRING, ','.join(PROPER_NAMES)),
        ('upru', O.INT, len(PROPER_NAMES)),
        ('umdl', O.STRING, dwarf.MODEL_PATH),
        ('uico', O.STRING, dwarf.ICON_PATH),
        ('uhab', O.STRING, ','.join(new for _, new, _ in ABILITIES)),
        ('utip', O.STRING, 'Summon Dark Iron |cffffcc00T|rhane'),
        ('utpr', O.STRING, 'Revive Dark Iron |cffffcc00T|rhane'),
        ('uawt', O.STRING, 'Revive Dark Iron |cffffcc00T|rhane'),
        ('uhot', O.STRING, 'T'),
        ('utub', O.STRING, 'Warrior Hero of the Shadowforge, wielding the fire of the mountain. Can learn Molten '
                           'Hammer, Fire Stomp, Searing Blows and Avatar of Flame. |n|n'
                           '|cffffcc00Attacks land units.|r'),
    ]),
]


def files():
    """The archive files for the hero: model, texture, icons, object data
    and the import list."""
    assets, _, _, _ = dwarf.build()
    out = dict(assets)
    out['war3map.w3u'] = O.w3u(UNITS)
    out['war3map.w3a'] = O.w3a(ABILITIES)
    out['war3map.imp'] = O.imp(sorted(assets))
    return out
