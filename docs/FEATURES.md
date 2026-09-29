# Feature gallery

Every instant answer and the site-ranking UI, one screenshot each. Use **Ctrl+F** to find something, or jump from the contents below.

> [!NOTE]
> Like the rest of this repo, it's vibe coded (see the [README](../README.md)). These screenshots come from a live instance (SearXNG `2026-09-22`, default *light* theme, Chromium). What you actually see depends on your theme and fonts. Emoji in particular render with your OS's emoji font.

The query shown under each heading is exactly what was typed into the search box. A leading `!wp` just limited the web results to Wikipedia while taking the screenshots (so the real search engines weren't hammered). It has no effect on the answer, so leave it out.

## Contents

- [Fun & random](#fun-random)
- [Generators](#generators)
- [Timers & clocks](#timers-clocks)
- [Dates & calendar](#dates-calendar)
- [Weather](#weather)
- [Maths & money](#maths-money)
- [Developer](#developer)
- [Text & encoding](#text-encoding)
- [Colour](#colour)
- [Personal site ranking](#personal-site-ranking)
- [Themes](#themes)
- [The `help` card](#the-help-card)

## Fun & random

### `roll 2d6+3`

Dice with any count/sides/modifier. <code>roll</code>, <code>roll dice</code>, <code>d20</code>, <code>roll 4d8-1</code>, <code>slå terning</code>. <b>Roll again</b> re-rolls in the browser.

<img src="img/dice.png" width="620" alt="roll 2d6+3">

### `roll 3d20`

Non-d6 dice render as numbered gems.

<img src="img/dice-d20.png" width="620" alt="roll 3d20">

### `flip a coin`

Coin flip with a 3D flip animation. Also <code>heads or tails</code>, <code>plat eller krone</code> (Danish faces).

<img src="img/coin.png" width="620" alt="flip a coin">

### `random number 1-100`

Random integer in a range. Also <code>pick a number between 1 and 6</code>. Default range 1–100.

<img src="img/random-number.png" width="620" alt="random number 1-100">

### `pick pizza, sushi or tacos`

Picks one option. Separators: commas, <code>or</code>, <code>|</code>, <code>vs</code>, <code>eller</code>. <b>Pick again</b> runs a little roulette.

<img src="img/pick.png" width="620" alt="pick pizza, sushi or tacos">

### `shuffle alice, bob, carol, dave, erin`

Shuffles a list (e.g. turn order).

<img src="img/shuffle.png" width="620" alt="shuffle alice, bob, carol, dave, erin">

### `8ball will it rain tomorrow?`

Magic 8-ball; <b>Shake</b> for a new answer.

<img src="img/8ball.png" width="620" alt="8ball will it rain tomorrow?">

### `yes or no`

Yes or no. <code>ja eller nej</code> answers in Danish.

<img src="img/yes-no.png" width="620" alt="yes or no">

### `rock paper scissors`

Playable rock-paper-scissors with a running score (also <code>sten saks papir</code>).

<img src="img/rps.png" width="620" alt="rock paper scissors">

## Generators

### `password 24`

Password generator. Slider for length, symbols toggle; new passwords are made in the browser with <code>crypto.getRandomValues</code>. Also <code>password</code>, <code>generate password 40</code>.

<img src="img/password.png" width="620" alt="password 24">

### `uuid`

UUID v4 (<code>uuid</code>, <code>guid</code>) or time-ordered v7 (<code>uuid v7</code>).

<img src="img/uuid.png" width="620" alt="uuid">

### `lorem ipsum 2`

Placeholder text: <code>lorem 3 paragraphs</code>, <code>lorem 5 sentences</code>, <code>lorem 50 words</code>.

<img src="img/lorem.png" width="620" alt="lorem ipsum 2">

### `qr https://github.com/DeeKahy/searxng-instant-answers`

QR code for any text/URL (needs <code>segno</code>).

<img src="img/qr.png" width="620" alt="qr https://github.com/DeeKahy/searxng-instant-answers">

## Timers & clocks

### `timer 5 min`

Countdown timer with progress ring, presets, a beep at zero and the time left in the tab title. Understands <code>timer 90s</code>, <code>timer 1h30m</code>, <code>timer 2:30</code>, <code>5 minute timer</code>, <code>nedtælling 10 min</code>.

<img src="img/timer.png" width="620" alt="timer 5 min">

### `pomodoro`

25-minute focus timer.

<img src="img/pomodoro.png" width="620" alt="pomodoro">

### `stopwatch`

Stopwatch with laps (also <code>stopur</code>).

<img src="img/stopwatch.png" width="620" alt="stopwatch">

### `time in tokyo`

Live world clock for any city, compared with the home time zone. Also <code>what time is it in new york</code>, <code>klokken i london</code>, <code>tokyo local time</code>; plain <code>time</code> shows home.

<img src="img/world-clock.png" width="620" alt="time in tokyo">

### `unix 1767225600`

Unix timestamp ↔ date (seconds or milliseconds). A bare 10-digit number starting with 1 also works.

<img src="img/unix.png" width="620" alt="unix 1767225600">

### `timestamp`

The current Unix time, ticking live.

<img src="img/unix-now.png" width="620" alt="timestamp">

### `moon phase`

Moon phase, illumination and next full/new moon.

<img src="img/moon.png" width="620" alt="moon phase">

## Dates & calendar

### `days until christmas`

Live countdown to a date or holiday: christmas, juleaften, new year, easter, halloween, sankthans, fastelavn, the weekend… or any date. Also <code>dage til jul</code>, <code>how long until 24 dec</code>.

<img src="img/countdown.png" width="620" alt="days until christmas">

### `days between 1/1/2026 and 24/12/2026`

Days (and weekdays) between two dates. Dates are day-first: <code>24/12/2026</code>, <code>24.12.2026</code>, <code>2026-12-24</code>, <code>24 dec</code>, <code>december 24</code>.

<img src="img/days-between.png" width="620" alt="days between 1/1/2026 and 24/12/2026">

### `today + 90 days`

Date arithmetic: <code>today + 90 days</code>, <code>24/12/2026 - 2 weeks</code>, <code>100 days ago</code>, <code>in 3 months</code>.

<img src="img/date-math.png" width="620" alt="today + 90 days">

### `what day is 24/12/2026`

Which weekday a date falls on.

<img src="img/weekday.png" width="620" alt="what day is 24/12/2026">

### `week`

Current ISO week number with a mini calendar (<code>uge</code>, <code>ugenummer</code>, <code>what week is it</code>).

<img src="img/week.png" width="620" alt="week">

### `uge 42`

Date range of a given week (<code>week 42 2027</code>).

<img src="img/week-n.png" width="620" alt="uge 42">

### `today`

Today: date, week, day of year and a year-progress bar.

<img src="img/today.png" width="620" alt="today">

### `is 2028 a leap year`

Leap-year check (also <code>skudår 2028</code>).

<img src="img/leap.png" width="620" alt="is 2028 a leap year">

### `helligdage`

Danish public holidays for any year, with the next one highlighted (<code>holidays 2027</code>).

<img src="img/holidays.png" width="620" alt="helligdage">

### `easter 2027`

Easter and related dates.

<img src="img/easter.png" width="620" alt="easter 2027">

### `age 1995-04-12`

Age, days alive and next birthday.

<img src="img/age.png" width="620" alt="age 1995-04-12">

## Weather

### `weather copenhagen`

Current weather, 24-hour temperature + rain chart and 7-day forecast from Open-Meteo. <code>weather aarhus</code>, <code>vejret i odense</code>, <code>london weather</code>, <code>sunrise paris</code>; bare <code>weather</code>/<code>vejret</code> uses the home city.

<img src="img/weather.png" width="620" alt="weather copenhagen">

## Maths & money

### `15% of 80`

Percentage of a number (<code>15 procent af 80</code>).

<img src="img/percent-of.png" width="620" alt="15% of 80">

### `20 is what percent of 80`

What percentage one number is of another.

<img src="img/what-percent.png" width="620" alt="20 is what percent of 80">

### `80 + 25%`

Add/subtract a percentage (prices, VAT…).

<img src="img/add-percent.png" width="620" alt="80 + 25%">

### `change from 80 to 100`

Percentage change.

<img src="img/percent-change.png" width="620" alt="change from 80 to 100">

### `tip 500 between 4`

Tip table, optionally split between people (<code>tip 18% on 640</code>).

<img src="img/tip.png" width="620" alt="tip 500 between 4">

### `split 1250 between 4`

Split a bill.

<img src="img/split.png" width="620" alt="split 1250 between 4">

## Developer

### `0xff`

Number in decimal/hex/binary/octal (+ bytes and the Unicode character). <code>0b1010</code>, <code>0o17</code>.

<img src="img/bases.png" width="620" alt="0xff">

### `255 in base 7`

Convert to any base 2–36 (<code>255 in binary</code>, <code>1011 from binary</code>).

<img src="img/bases-to.png" width="620" alt="255 in base 7">

### `2026 in roman`

Roman numerals both ways (<code>roman MMXXVI</code>).

<img src="img/roman.png" width="620" alt="2026 in roman">

### `192.168.8.0/22`

Subnet calculator: mask, wildcard, broadcast, host range, host count. IPv6 too.

<img src="img/subnet.png" width="620" alt="192.168.8.0/22">

### `2001:db8::/48`

IPv6 prefix.

<img src="img/subnet6.png" width="620" alt="2001:db8::/48">

### `8.8.8.8`

Info about an IP address.

<img src="img/ip-info.png" width="620" alt="8.8.8.8">

### `what is my ip`

Your public IP and user agent (<code>ip</code>, <code>my ip</code>, <code>user agent</code>). The screenshot shows 127.0.0.1 because it was taken on the server itself.

<img src="img/my-ip.png" width="620" alt="what is my ip">

### `http 418`

HTTP status codes with description and MDN link, colour-coded by class. Includes nginx and Cloudflare 52x codes.

<img src="img/http.png" width="620" alt="http 418">

### `522 error`

<img src="img/http-5xx.png" width="620" alt="522 error">

### `chmod 755`

Unix permissions, octal ↔ symbolic (<code>chmod rwxr-x---</code>).

<img src="img/chmod.png" width="620" alt="chmod 755">

### `port 5432`

What usually runs on a port.

<img src="img/port.png" width="620" alt="port 5432">

### `json {"name":"searxng","plugins":["answers","sites"],"ok":true}`

Pretty-prints JSON (or shows the parse error).

<img src="img/json.png" width="620" alt="json {&quot;name&quot;:&quot;searxng&quot;,&quot;plugins&quot;:[&quot;answers&quot;,&quot;sites&quot;],&quot;ok&quot;:true}">

### `eyJhbGciOiJIUzI1NiIsInR5cCI6…  (a pasted JWT)`

Paste a JWT to decode header and payload (the signature is <b>not</b> verified). Never sent to search engines.

<img src="img/jwt.png" width="620" alt="eyJhbGciOiJIUzI1NiIsInR5cCI6…  (a pasted JWT)">

## Text & encoding

### `base64 hello world`

Base64 encode (<code>base64 decode aGVsbG8=</code> to decode, URL-safe variants too).

<img src="img/base64.png" width="620" alt="base64 hello world">

### `url encode a b&c=d/e`

URL encode/decode. Also <code>html escape …</code>, <code>rot13 …</code>, <code>reverse text …</code>.

<img src="img/url-encode.png" width="620" alt="url encode a b&amp;c=d/e">

### `camel case hello big world`

Case conversion: upper, lower, title, snake, kebab, camel, pascal, constant, slug.

<img src="img/case.png" width="620" alt="camel case hello big world">

### `count words The quick brown fox jumps over the lazy dog. Again!`

Characters, words, sentences, bytes and reading time.

<img src="img/count.png" width="620" alt="count words The quick brown fox jumps over the lazy dog. Again!">

### `morse sos help`

Text → Morse with audio playback; Morse → text (<code>morse ... --- ...</code>).

<img src="img/morse.png" width="620" alt="morse sos help">

### `unicode ☃é€`

Unicode details: code point, name, UTF-8 bytes, HTML entity (<code>U+1F600</code>).

<img src="img/unicode.png" width="620" alt="unicode ☃é€">

### `emoji cat`

Emoji search by name; click to copy.

<img src="img/emoji.png" width="620" alt="emoji cat">

## Colour

### `#ff7a59`

Colour card: swatch, shades, harmony colours, HEX/RGB/HSL/CMYK and WCAG contrast. Click anything to copy it.

<img src="img/colour.png" width="620" alt="#ff7a59">

### `rgb(30, 144, 255)`

Also <code>rgb(…)</code>, <code>rgba(…)</code>, <code>hsl(…)</code>, <code>color 3b82f6</code>.

<img src="img/colour-rgb.png" width="620" alt="rgb(30, 144, 255)">

## Personal site ranking

Every result gets a **⋯** button next to *cached*. It offers boost / lower / block for the exact host and for the whole domain:

<img src="img/site-menu.png" width="720" alt="site ranking menu">

**Before and after:** the same search (`rust borrow checker`) with `github.com` boosted and `medium.com` + `youtube.com` blocked. GitHub jumps from 6th to 1st and gets a ★ and a green edge. The blocked sites are gone.

| Before | After |
|---|---|
| <img src="img/ranking-before.png" width="420"> | <img src="img/ranking-after.png" width="420"> |

Search **`sites`** to see and edit your list (▲ boost, ▼ lower, ⊘ block, ✕ forget) or to add a domain by hand. `pinterest.*` means every Pinterest TLD. Everything lives in one cookie in your browser:

<img src="img/sites-card.png" width="620" alt="sites management card">

## Themes

The cards only use SearXNG's own colour variables, so they follow whatever theme is selected (Preferences → *Theme style*). Here's `roll 2d6+3` in the three built-in styles and the ten extra ones from `themes.css`:


| **light** | **dark** | **black** |
|---|---|---|
| <img src="img/themes/theme-light.png" width="280"> | <img src="img/themes/theme-dark.png" width="280"> | <img src="img/themes/theme-black.png" width="280"> |
| **mocha** | **tokyonight** | **gruvbox** |
| <img src="img/themes/theme-mocha.png" width="280"> | <img src="img/themes/theme-tokyonight.png" width="280"> | <img src="img/themes/theme-gruvbox.png" width="280"> |
| **nord** | **dracula** | **rosepine** |
| <img src="img/themes/theme-nord.png" width="280"> | <img src="img/themes/theme-dracula.png" width="280"> | <img src="img/themes/theme-rosepine.png" width="280"> |
| **sakura** | **latte** | **bubblegum** |
| <img src="img/themes/theme-sakura.png" width="280"> | <img src="img/themes/theme-latte.png" width="280"> | <img src="img/themes/theme-bubblegum.png" width="280"> |
| **solarized** |
| <img src="img/themes/theme-solarized.png" width="280"> |


## The `help` card

Search **`help`** (or `tricks`, `instant answers`) on your own instance to get this list with clickable examples:

<img src="img/help.png" width="720" alt="help card">
