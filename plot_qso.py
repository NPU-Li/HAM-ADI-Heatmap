"""Render a 365-day ADIF calendar and 12-week band percentages. See README.md."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys

# Optional project-local dependencies; normal pip/venv installs also work.
LOCAL_DEPS = Path(__file__).resolve().parent / '.python_deps'
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))

BAND_COLORS = {
    '80M': '#0000FF', '60M': '#00008B', '40M': '#008000',
    '30M': '#FF69B4', '20M': '#FFFF00', '17M': '#FFC0CB',
    '15M': '#FFA500', '12M': '#DDA0DD', '10M': '#FF0000',
}
TAG = re.compile(r'<([^<>]+)>')


def parse_adif(text: str) -> list[dict[str, str]]:
    """Consume declared field lengths, so comments/newlines are not values."""
    records, record = [], {}
    pos = 0
    while match := TAG.search(text, pos):
        parts = match.group(1).split(':')
        name = parts[0].upper()
        pos = match.end()
        if name == 'EOH':
            record = {}
        elif name == 'EOR':
            if record:
                records.append(record)
            record = {}
        elif len(parts) >= 2:
            if not parts[1].isdigit():
                raise ValueError(f'Invalid field length: {match.group(0)}')
            size = int(parts[1])
            if pos + size > len(text):
                raise ValueError(f'Truncated field: {name}')
            record[name] = text[pos:pos + size]
            pos += size
    if record:
        raise ValueError('Unterminated record: missing <EOR>')
    return records


def dated_records(records):
    result = []
    for index, record in enumerate(records, 1):
        raw = record.get('QSO_DATE', '')
        if not re.fullmatch(r'\d{8}', raw):
            raise ValueError(f'Record {index}: invalid/missing QSO_DATE {raw!r}')
        try:
            day = datetime.strptime(raw, '%Y%m%d').date()
        except ValueError as exc:
            raise ValueError(f'Record {index}: {exc}') from exc
        result.append((day, record))
    if not result:
        raise ValueError('No QSO records found')
    return result


def aggregate(rows, end):
    start = end - timedelta(days=364)
    days = [start + timedelta(days=i) for i in range(365)]
    # Exclude the anchor's current ISO week, even when the anchor is Sunday.
    week_end = end - timedelta(days=end.weekday() + 1)
    week_start = week_end - timedelta(days=83)
    daily = Counter()
    weekly = {week_start + timedelta(days=7 * i): Counter() for i in range(12)}
    excluded = Counter()
    for day, record in rows:
        if start <= day <= end:
            daily[day] += 1
        if week_start <= day <= week_end:
            band = record.get('BAND', '').strip().upper()
            if band in BAND_COLORS:
                weekly[week_start + timedelta(days=7 * ((day - week_start).days // 7))][band] += 1
            else:
                excluded[band or '(missing BAND)'] += 1
    return days, daily, weekly, excluded


def render(days, daily, weekly, out, station):
    os.environ.setdefault('MPLCONFIGDIR', str(out.resolve() / '.mplconfig'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm, LinearSegmentedColormap
    from matplotlib.patches import FancyBboxPatch
    from matplotlib.cm import ScalarMappable

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.titleweight': 'bold', 'svg.fonttype': 'none'})
    subtitle = f'{days[0]} — {days[-1]}  |  UTC  |  {station}'
    maximum = max(daily.values(), default=0)
    levels = max(1, (maximum + 19) // 20)
    spectrum = LinearSegmentedColormap.from_list('qso_spectrum', [
        '#B7EFA1', '#08752C', '#9ADFFF', '#1542B4', '#FFA0A0', '#A50026',
    ])
    colors = ['#FFFFFF'] + [spectrum(i / max(levels - 1, 1))
                              for i in range(levels)]
    fig = plt.figure(figsize=(15, 5.0), facecolor='white')
    fig.text(.055, .91, 'Daily QSO activity', fontsize=22, weight='bold', color='#172b3a')
    fig.text(.055, .85, subtitle, color='#667784')
    fig.text(.945, .91, f'{sum(daily.values()):,} QSOs', ha='right', fontsize=19, weight='bold')
    fig.text(.945, .85, f'{sum(v > 0 for v in daily.values())} active days  •  Peak {maximum}/day',
             ha='right', color='#667784')
    ax = fig.add_axes([.055, .29, .89, .46])
    origin = days[0] - timedelta(days=(days[0].weekday() + 1) % 7)
    for day in days:
        x, y = divmod((day - origin).days, 7)
        n = daily[day]
        level = (n + 19) // 20 if n else 0
        ax.add_patch(FancyBboxPatch((x + .07, y + .07), .86, .86,
                                   boxstyle='round,pad=0,rounding_size=0.12',
                                   facecolor=colors[level],
                                   edgecolor='#238636' if n == 0 else 'white',
                                   linewidth=.65 if n == 0 else .4))
    ticks = [d for d in days if d.day == 1]
    if not ticks or (ticks[0] - days[0]).days >= 10:
        ticks.insert(0, days[0])
    ax.set_xticks([(d - origin).days // 7 + .5 for d in ticks],
                  [d.strftime('%b') for d in ticks])
    ax.xaxis.tick_top()
    ax.set_yticks([1.5, 3.5, 5.5], ['Mon', 'Wed', 'Fri'])
    ax.set_xlim(0, (days[-1] - origin).days // 7 + 1)
    ax.set_ylim(7, 0)
    ax.set_aspect('equal')
    ax.tick_params(length=0, pad=8, colors='#667784')
    for spine in ax.spines.values():
        spine.set_visible(False)
    # Discrete numeric scale: 0; 1–20; 21–40; ... with no capped overflow bin.
    bounds = [-.5, .5] + [20 * i + .5 for i in range(1, levels + 1)]
    if maximum:
        bounds[-1] = maximum + .5
    cmap = ListedColormap(colors)
    cax = fig.add_axes([.40, .16, .545, .028])
    bar = fig.colorbar(ScalarMappable(norm=BoundaryNorm(bounds, cmap.N), cmap=cmap),
                       cax=cax, orientation='horizontal', spacing='uniform',
                       ticks=([0] + [20 * i for i in range(1, levels)] + [maximum])
                       if maximum else [0])
    bar.ax.tick_params(labelsize=7, length=2)
    bar.outline.set_visible(False)
    fig.text(.055, .17, 'QSO/day: 0 · 1–20 · 21–40 · …', color='#667784', fontsize=10)
    fig.text(.055, .07, 'White + green outline: 0 QSOs. Blank cells outside the 365-day window are omitted.',
             color='#667784', fontsize=9)
    save(fig, out, 'daily_qso_heatmap')
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(15, 5), facecolor='white')
    fig.subplots_adjust(left=.055, right=.945, bottom=.23, top=.66)
    fig.text(.055, .91, 'Weekly QSO band distribution', fontsize=22, weight='bold', color='#172b3a')
    weeks = list(weekly)
    week_end = weeks[-1] + timedelta(days=6)
    fig.text(.055, .85, f'{weeks[0]} — {week_end}  |  UTC  |  {station}  |  Last 12 complete ISO weeks', color='#667784')
    totals = [sum(weekly[w].values()) for w in weeks]
    base = [0.] * len(weeks)
    for band, color in BAND_COLORS.items():
        values = [weekly[w][band] / total * 100 if total else 0 for w, total in zip(weeks, totals)]
        ax.bar(range(len(weeks)), values, bottom=base, color=color, label=band.lower(),
               width=.65, edgecolor='white', linewidth=.6)
        base = [b + v for b, v in zip(base, values)]
    for x, total in enumerate(totals):
        ax.annotate(f'n={total:,}' if total else 'No QSO', (x, 100 if total else 0),
                    xytext=(0, 5), textcoords='offset points',
                    ha='center', fontsize=8, color='#172b3a')
    ax.set_xticks(range(len(weeks)),
                  [f'Week {w.isocalendar().week}\n{w:%m/%d}–{w + timedelta(days=6):%m/%d}'
                   for w in weeks], fontsize=8, linespacing=1.8)
    ax.set_ylabel('Band share')
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100], ['0%', '25%', '50%', '75%', '100%'])
    ax.set_axisbelow(True)
    ax.grid(axis='y', color='#e7ebef')
    for side in ['top', 'right', 'left']:
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#d7dde3')
    ax.tick_params(length=0, colors='#526371', pad=8)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper left', bbox_to_anchor=(.05, .80),
               ncol=9, frameon=False, handlelength=1.4, columnspacing=2)
    fig.text(.055, .07, f'80m–10m only  •  {sum(totals):,} QSOs  •  Monday–Sunday (UTC); n = weekly QSO count. Empty weeks have no percentage.',
             color='#667784', fontsize=10)
    save(fig, out, 'weekly_qso_by_band')
    plt.close(fig)


def save(fig, out, name):
    for extension in ('png', 'svg'):
        fig.savefig(out / f'{name}.{extension}', dpi=200, facecolor='white')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='ADIF/ADI file')
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parent / 'config.json')
    parser.add_argument('--end-date', type=date.fromisoformat, help='Last day, YYYY-MM-DD; default: latest QSO')
    parser.add_argument('--output-dir', type=Path, default=Path('output'))
    parser.add_argument('--encoding', default='utf-8-sig')
    args = parser.parse_args()
    try:
        rows = dated_records(parse_adif(args.input.read_text(encoding=args.encoding)))
        config = json.loads(args.config.read_text(encoding='utf-8-sig'))
        if not isinstance(config, dict):
            raise ValueError('Config must be a JSON object')
        anchor = config.get('end_date')
        if anchor is not None and not isinstance(anchor, str):
            raise ValueError('end_date must be YYYY-MM-DD or null')
        end = args.end_date or (date.fromisoformat(anchor) if anchor else max(day for day, _ in rows))
        days, daily, weekly, excluded = aggregate(rows, end)
        stations = sorted({r.get('STATION_CALLSIGN', r.get('APP_LOTW_OWNCALL', 'Unknown')) for _, r in rows})
        args.output_dir.mkdir(parents=True, exist_ok=True)
        render(days, daily, weekly, args.output_dir, ', '.join(stations))
        summary = {
            'source': str(args.input), 'records_read': len(rows), 'timezone': 'UTC',
            'start': str(days[0]), 'end': str(days[-1]), 'days': len(days),
            'daily_total': sum(daily.values()), 'weekly_total': sum(sum(v.values()) for v in weekly.values()),
            'weekly_start': str(min(weekly)), 'weekly_end': str(max(weekly) + timedelta(days=6)),
            'excluded_from_weekly': dict(excluded), 'band_colors': BAND_COLORS,
            'daily': {str(d): daily[d] for d in days},
            'weekly': {str(w): {
                'iso_year': w.isocalendar().year, 'iso_week': w.isocalendar().week,
                'end': str(w + timedelta(days=6)), 'total': sum(counts.values()),
                'counts': {b: counts[b] for b in BAND_COLORS},
                'percentages': {b: counts[b] / sum(counts.values()) * 100 if sum(counts.values()) else None
                                for b in BAND_COLORS},
            } for w, counts in weekly.items()},
        }
        (args.output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Read {len(rows)} QSOs; window {days[0]} to {days[-1]} (365 days, UTC).')
        print(f'Daily total: {summary["daily_total"]}; weekly 80m-10m: {summary["weekly_total"]}.')
        print(f'Excluded weekly bands: {dict(excluded)}')
        print(f'Output: {args.output_dir.resolve()}')
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
