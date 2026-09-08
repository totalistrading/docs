"""Emit one HTML file per concept picture from compact specs. Shared look lives in pics.css.
Rule of the system: at most four columns across, plain words only, one highlighted object per picture."""
import pathlib, html as H
HEAD = '''<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="pics.css"></head><body>'''
TAIL = '<script>if (location.search.includes("dark")) document.body.classList.add("dark");</script></body></html>'

def card(title=None, sub=None, kicker=None, badge=None, badge_cls='', lock=False, hi=False, soft=False, w=None, body='', cls=''):
    c = ['card'] + (['hi'] if hi else []) + (['soft'] if soft else []) + ([cls] if cls else [])
    style = f' style="--w:{w}px"' if w else ''
    out = f'<div class="{" ".join(c)}"{style}>'
    if badge: out += f'<span class="badge {badge_cls}">{H.escape(badge)}</span>'
    if lock: out += '<div class="lock"></div>'
    if kicker: out += f'<p class="kicker">{H.escape(kicker)}</p>'
    if title: out += f'<p class="title">{H.escape(title)}</p>'
    if sub: out += f'<p class="sub">{H.escape(sub)}</p>'
    return out + body + '</div>'

def link(tip=None, tip_cls='', w=None):
    if tip and not w: w = 44 + 13 * len(tip)   # labelled links grow with the label so it never touches a card
    style = f' style="--lw:{w}px"' if w else ''
    t = f'<span class="tip {tip_cls}">{H.escape(tip)}</span>' if tip else ''
    return f'<div class="link"{style}>{t}</div>'

def fork(top=25, bottom=25):
    return (f'<div class="fork" style="--top:{top}%;--bottom:{bottom}%"><div class="arm" style="top:{top}%"></div>'
            f'<div class="arm" style="top:{100-bottom}%"></div><div class="mid"></div></div>')

def stack(*cards): return '<div class="stack">' + ''.join(cards) + '</div>'
def col(*parts): return '<div class="col">' + ''.join(parts) + '</div>'
def vlink(): return '<div class="vlink"></div>'
def glow(x, y): return f'<div class="glow" style="left:{x}px;top:{y}px"></div>'
def rail(ticks):
    return '<div class="rail">' + ''.join(f'<div class="tick {"on" if on else ""}" style="left:{pct}%"><span>{H.escape(t)}</span></div>' for pct, t, on in ticks) + '</div>'
def rows(*pairs):
    return '<div class="rows">' + ''.join(f'<div class="row"><span>{H.escape(k)}</span><b class="{c}">{H.escape(v)}</b></div>' for k, v, c in pairs) + '</div>'
def tags(*items):
    return ''.join(f'<div class="tag {"best" if best else ""}"><span>{H.escape(n)}</span><b>{H.escape(v)}</b></div>' for n, v, best in items)
def sub_after(text): return f'<p class="sub" style="margin-top:14px">{H.escape(text)}</p>'
def slip(legs, bet, w=340):
    body = ''.join(f'<div class="leg"><span class="venue {v}">{v.upper()}</span><span class="name">{H.escape(n)}</span><span class="pill {"" if yes else "no"}">{"Yes" if yes else "No"}</span></div>' for v, n, yes in legs)
    body += f'<div class="total"><span>Your bet</span><b>{H.escape(bet)}</b></div>'
    return card(kicker='Your slip', body=body, w=w, cls='slip')

def page(name, stage_html, rail_ticks=None, glow_at=None):
    out = HEAD + (glow(*glow_at) if glow_at else '') + f'<div class="stage">{stage_html}</div>' + (rail(rail_ticks) if rail_ticks else '') + TAIL
    pathlib.Path(f'{name}.html').write_text(out, encoding='utf-8'); print('built', name)

LEGS = [('k', 'Fed holds in September', True), ('p', 'Bills win on Sunday', False), ('k', 'BTC above 100k', True)]

# lifecycle
page('lifecycle',
     slip(LEGS, '25 USDC') + link() +
     card(kicker='Makers quote', body=tags(('Maker A', '3.6x', False), ('Maker B', '4.0x', True), ('Maker C', '3.8x', False)) + sub_after('Best odds win'), w=290) + link() +
     card('One position', 'Your stake and the maker\'s collateral lock together on Solana', lock=True, hi=True, w=300) +
     fork(30, 30) +
     stack(card('Settles', 'When the last market resolves', badge='automatic', w=300),
           card('Cash out early', 'Makers bid for your position', badge='any time', badge_cls='hi', w=300)),
     [(0, 'quote', True), (33, 'commit', True), (66, 'live on chain', True), (100, 'settled', False)], glow_at=(930, 420))

# vault-architecture
page('vault-architecture',
     card('Your wallet', 'USDC in, payouts out. Never needs SOL.', w=280) + link('stake', 'hi') +
     card('Your vault', 'Gross, locked and free. Free is yours to trade or withdraw.', w=300) + link() +
     col(card('Fee vault', '1% of the winner\'s profit', w=300, soft=True), vlink(),
         card('Position', 'Your stake and the maker\'s collateral, locked together', lock=True, hi=True, w=300),
         vlink(), card('Settlement', 'Kalshi and Polymarket decide the outcome', w=300, soft=True)) +
     link('collateral') + card('Maker vault', 'Backs every quote the maker makes', w=280),
     [(0, 'fund', True), (50, 'commit', True), (100, 'settle', True)], glow_at=(770, 420))

# limits-and-fees
page('limits-and-fees',
     slip(LEGS, '25 USDC', w=330) + link('1% taker fee', 'warn') +
     card('Net stake', body=rows(('after the fee', '24.75', 'hi')), w=250) + link('x 4.0 odds', 'hi') +
     card('If every leg wins', body=rows(('payout', '99.00', ''), ('profit fee, 1%', '0.74', 'warn'), ('you receive', '98.26', 'hi')) + sub_after('If any leg loses, the maker keeps the 24.75 stake minus the same 1% fee'), w=340),
     [(0, 'bet', True), (35, 'stake', True), (70, 'payout', True), (100, 'settle', False)], glow_at=(1150, 420))

# glossary
page('glossary',
     card('Quote request', 'Your legs and bet, priced live by makers. Gone once it ends.', kicker='before you commit', w=340) + link() +
     card('Parlay', 'The record you can query from now on', kicker='from commit', hi=True, badge='product name', badge_cls='hi', w=340) + link() +
     card('Position', 'Your parlay on chain. Cash out from here.', kicker='from executed', lock=True, w=340),
     [(0, 'open', True), (20, 'quoted', True), (40, 'accepted', True), (60, 'confirmed', True), (80, 'executed', True), (100, 'settled', False)], glow_at=(770, 420))

# early-cashout
page('early-cashout',
     card('Your position', 'Live on chain, not yet settled', lock=True, w=290) + link('cash out', 'hi') +
     card(kicker='Auction, about 10 seconds', body=tags(('Maker A', '18.20', False), ('Maker B', '19.05', True), ('Maker C', '17.60', False)) + sub_after('Highest all-in price wins'), w=320) +
     fork(30, 30) +
     stack(card('Backing maker wins', 'Position closes. You are paid.', badge='bought back', badge_cls='hi', w=340),
           card('Another maker wins', 'Position moves to them, stays open. You are paid the same.', badge='transferred', w=340)),
     [(0, 'executed', True), (50, 'auction', True), (100, 'paid', True)], glow_at=(560, 420))

# funding
page('funding',
     card('Send USDC', 'To your wallet, from any Solana wallet or exchange', w=300) + link() +
     card('Enable trading', 'One consent in the app', badge='once', badge_cls='hi', w=290) + link() +
     card('Trade', 'Your stake moves into the vault by itself', hi=True, lock=True, w=290) + link() +
     card('Withdraw', 'Wallet and vault, in one call, any time', w=290),
     [(0, 'fund', True), (33, 'enable', True), (66, 'trade', True), (100, 'withdraw', True)], glow_at=(860, 420))

# market-maker
page('market-maker',
     card(kicker='A request arrives', body=tags(('your quote', '4.0x', True)) + sub_after('Better odds win the trade'), w=300) + link('user commits', 'hi') +
     card('Confirm', 'Within the window, or the request reopens', badge='5 seconds', badge_cls='warn', w=290) + link() +
     card('Collateral locks', 'Their stake and your risk, together on chain', lock=True, hi=True, w=300) + link() +
     card('Settlement', 'Keep the stake, or pay out the win', w=290),
     [(0, 'quote', True), (33, 'commit', True), (66, 'confirm', True), (100, 'settle', True)], glow_at=(870, 420))

# webhooks
page('webhooks',
     card('Something happens', 'A position settles or funds move', w=310) + link('signed', 'hi') +
     card('Delivered to you', 'One POST with a signature and a unique event id', hi=True, w=330) +
     fork(18, 18) +
     stack(card('Accepted', 'You reply 2xx. Done.', badge='delivered', badge_cls='hi', w=340),
           card('Retried', 'You reply 5xx or time out. Same event again, with backoff.', badge='failed', badge_cls='warn', w=340),
           card('Dropped', 'You reply another 4xx. Replay it once fixed.', badge='dead letter', w=340)),
     None, glow_at=(640, 470))

# websocket
page('websocket',
     card('Connect', 'One socket for all live events', w=280) + link() +
     card('Authenticate', 'Send your API key first', badge='before the timeout', badge_cls='warn', w=300) + link() +
     card('Subscribe', 'Your channel, keyed by your user id', w=300) + link() +
     card('Events arrive', 'Quotes accepted, positions settled, cash outs', badge='ping keeps it open', hi=True, w=320),
     None, glow_at=(1080, 420))

# realtime-and-data (custom layout)
def bar(l, r, text, hi=False):
    return f'<div class="bar {"hi" if hi else ""}" style="left:{l}%;width:{r-l}%">{H.escape(text)}</div>'
chan = lambda name, small, bars: f'<div class="chan"><div class="name">{name}<small>{small}</small></div><div class="track">{"".join(bars)}</div></div>'
rt = HEAD + '<div class="channels">' + \
     chan('Quote stream', 'while you shop for a price', [bar(0, 30, 'best quote, live', True)]) + \
     chan('WebSocket', 'live, while connected', [bar(30, 100, 'accepted, confirmed, settled, bought back')]) + \
     chan('Webhooks', 'durable, signed, retried', [bar(70, 100, 'settled, bought back, funds moved')]) + \
     chan('REST', 'any time', [bar(0, 100, 'portfolio, parlays, balances, history')]) + '</div>' + \
     '<div class="marks">' + ''.join(f'<div class="tick on" style="left:{p}%"><span>{t}</span></div>' for p, t in [(0, 'request'), (30, 'commit'), (70, 'settle')]) + \
     '<div class="tick" style="left:100%"><span>later</span></div></div>' + TAIL
pathlib.Path('realtime-and-data.html').write_text(rt, encoding='utf-8'); print('built realtime-and-data')
