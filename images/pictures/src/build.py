"""Concept pictures, Polymarket idiom: people as avatars, boxes with one or two words, dashed links,
numbers where a number says it best. Each picture stays under about fifteen words.
Edit a spec, run `python build.py`, then render with scripts/render-pictures.mjs."""
import pathlib, html as H

CSS = pathlib.Path(__file__).with_name('pics.style').read_text(encoding='utf-8')
HEAD = f'''<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap">
<style>{CSS}</style></head><body>'''
TAIL = '<script>if (location.search.includes("dark")) document.body.classList.add("dark");</script></body></html>'

def esc(x): return H.escape(str(x))
def box(t=None, s=None, n=None, hi=False, warn=False, tall=False, wide=False, compact=False):
    cls = 'box' + (' hi' if hi else '') + (' warn' if warn else '') + (' tall' if tall else '') + (' wide' if wide else '') + (' compact' if compact else '')
    inner = (f'<div class="n">{esc(n)}</div>' if n is not None else '') + (f'<div class="t">{esc(t)}</div>' if t else '') + (f'<div class="s">{esc(s)}</div>' if s else '')
    return f'<div class="{cls}">{inner}</div>'
def avatar(c, sm=False): return f'<div class="avatar a{c}{" sm" if sm else ""}"></div>'
def who(c, label): return f'<div class="who">{avatar(c)}<div class="label">{esc(label)}</div></div>'
def people(*cs, sm=False): return '<div class="people">' + ''.join(avatar(c, sm) for c in cs) + '</div>'
def chips(*items): return '<div class="chips">' + ''.join(f'<div class="chip {k}">{esc(t)}</div>' for t, k in items) + '</div>'
def panel(*children, cap=None): return '<div class="panel">' + (f'<p class="cap">{esc(cap)}</p>' if cap else '') + ''.join(children) + '</div>'
def dl(w=None): return f'<div class="dl"{f" style=--w:{w}px" if w else ""}></div>'
def vl(h=None): return f'<div class="dl v"{f" style=--h:{h}px" if h else ""}></div>'
def fork(top=25, bottom=25, mid=False):
    return (f'<div class="fork" style="--top:{top}%;--bottom:{bottom}%"><div class="arm a"></div><div class="arm b"></div>'
            + ('<div class="arm mid"></div>' if mid else '') + '</div>')
def stack(*x): return '<div class="stack">' + ''.join(x) + '</div>'
def col(*x): return '<div class="col">' + ''.join(x) + '</div>'
def rowc(*x): return '<div class="rowc">' + ''.join(x) + '</div>'
def rail(ticks): return '<div class="rail">' + ''.join(f'<div class="tick {"on" if on else ""}" style="left:{p}%"><span>{esc(t)}</span></div>' for p, t, on in ticks) + '</div>'
def page(name, stage, ticks=None, zoom=1):
    # zoom fills the frame the way Polymarket's pictures do; the rail is outside the zoomed stage
    pathlib.Path(f'{name}.html').write_text(HEAD + f'<div class="stage"><div class="inner" style="zoom:{zoom}">{stage}</div></div>' + (rail(ticks) if ticks else '') + TAIL, encoding='utf-8'); print('built', name)

# How parlays work: you, a slip, makers, one position, two ends
page('lifecycle',
     who(1, 'You') + dl() +
     panel(box('Slip'), chips(('Yes', 'yes'), ('No', 'no'), ('Yes', 'yes')), cap='2 to 5 legs') + dl() +
     panel(people(2, 3, 4, sm=True), box('Best odds', n='4.0x', hi=True), cap='Makers') + dl() +
     box('Position', tall=True, hi=True) + fork(28, 28) +
     stack(box('Settles'), box('Cash out')),
     [(0, 'quote', True), (36, 'commit', True), (72, 'live', True), (100, 'settled', False)], zoom=1.0)

# Vaults and custody: two people, two vaults, one position, fees out the bottom
page('vault-architecture',
     col(who(1, 'You'), vl(), box('Vault')) + dl() +
     col(box('Position', tall=True, hi=True), vl(), box('Fee', n='1%')) + dl() +
     col(who(2, 'Maker'), vl(), box('Vault')),
     [(0, 'fund', True), (50, 'lock', True), (100, 'settle', True)], zoom=1.2)

# Limits and fees: the waterfall as numbers
page('limits-and-fees',
     box('Bet', n='25', compact=True) + dl(44) + box('Fee', n='1%', warn=True, compact=True) + dl(44) + box('Stake', n='24.75', compact=True) + dl(44) +
     box('Odds', n='x 4.0', hi=True, compact=True) + dl(44) + box('Payout', n='99', compact=True) + fork(28, 28) +
     stack(box('Win', n='98.26', hi=True, compact=True), box('Lose', n='0', compact=True)),
     None, zoom=1.0)

# Glossary: three names on one rail
page('glossary',
     box('Quote request', wide=True, tall=True) + dl(140) + box('Parlay', wide=True, tall=True, hi=True) + dl(140) + box('Position', wide=True, tall=True),
     [(0, 'open', True), (40, 'commit', True), (72, 'on chain', True), (100, 'settled', False)], zoom=1.25)

# Early cashout: a position, an auction of three, two ends
page('early-cashout',
     who(1, 'You') + dl() + box('Position', tall=True, hi=True) + dl() +
     panel(rowc(avatar(2, True), chips(('18.20', ''))), rowc(avatar(3, True), chips(('19.05', 'yes'))), rowc(avatar(4, True), chips(('17.60', ''))), cap='Auction, 10 s') +
     fork(28, 28) + stack(box('Closed'), box('Transferred')),
     None, zoom=1.2)

# Funding: send, enable once, trade, withdraw
page('funding',
     who(1, 'You') + dl() + box('USDC') + dl() + box('Wallet') + dl() + box('Enable', s='once', hi=True) + dl() + box('Trade') + dl() + box('Withdraw'),
     None, zoom=1.0)

# Market making: request, quote, confirm, lock, settle
page('market-maker',
     who(2, 'Maker') + dl() + box('Request') + dl() + box('Quote', n='4.0x', hi=True) + dl() + box('Confirm', s='5 s', warn=True) + dl() + box('Lock') + dl() + box('Settle'),
     [(0, 'quote', True), (50, 'confirm', True), (100, 'settle', True)], zoom=1.0)

# Webhooks: event, signed post, your server, three replies
page('webhooks',
     box('Event') + dl() + box('POST', s='signed', hi=True) + dl() + who(2, 'Your server') + fork(18, 18, mid=True) +
     stack(box('2xx', s='done'), box('5xx', s='retried', warn=True), box('4xx', s='dropped')),
     None, zoom=1.25)

# WebSocket: connect, auth, subscribe, events
page('websocket',
     who(1, 'You') + dl() + box('Connect') + dl() + box('Auth', s='API key', hi=True) + dl() + box('Subscribe') + dl() + box('Events', tall=True),
     None, zoom=1.15)

# Real time and data: four channels on the trade timeline, no words but the names
def bar(l, r, hi=False): return f'<div class="bar {"hi" if hi else ""}" style="left:{l}%;width:{r-l}%"></div>'
def chan(name, *bars): return f'<div class="chan"><div class="name">{esc(name)}</div><div class="track">{"".join(bars)}</div></div>'
rt = HEAD + '<div class="channels">' + chan('Quote stream', bar(0, 34, True)) + chan('WebSocket', bar(34, 100)) + chan('Webhooks', bar(68, 100)) + chan('REST', bar(0, 100)) + '</div>' + \
     '<div class="marks">' + ''.join(f'<div class="tick on" style="left:{p}%"><span>{t}</span></div>' for p, t in [(0, 'request'), (34, 'commit'), (68, 'settle')]) + '</div>' + TAIL
pathlib.Path('realtime-and-data.html').write_text(rt, encoding='utf-8'); print('built realtime-and-data')

# Collateral: two parlays that cannot both win
page('collateral-netting',
     stack(box('Parlay A', n='12,000'), box('Parlay B', n='8,000')) + fork(28, 28, mid=True) +
     stack(box('One by one', n='20,000', warn=True), box('As a book', n='12,000', hi=True)),
     None, zoom=1.4)

# Integration models: managed and headless lanes into one venue
page('integration-models',
     stack(col(who(2, 'Your users')), col(who(2, 'Your platform'))) + fork(28, 28, mid=True) +
     stack(panel(box('Totalis wallet'), box('Totalis signs', s='enclave'), cap='Managed'),
           panel(box('Your keys'), box('You sign', s='Totalis builds'), cap='Headless')) +
     fork(28, 28, mid=True) + box('Totalis', s='quotes, positions, settlement', tall=True, hi=True),
     None, zoom=1.15)

