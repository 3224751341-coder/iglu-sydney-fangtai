#!/usr/bin/env python3
"""Offline only: rebuild saved evidence. Never fetch, notify, push or deploy."""
import copy
import json
from pathlib import Path
import update_fangtai as app


def main():
    root = Path(__file__).resolve().parent
    snapshot = json.loads((root / 'data_snapshot.json').read_text())
    cities = {key: {'label': value['label'], 'properties': value['properties'],
                    'room_results': {}} for key, value in app.CITIES.items()}
    for key, entry in snapshot.items():
        city, prop, slug = key.split('/', 2)
        if '_room' not in entry:
            raise ValueError(f'Missing raw room evidence: {key}')
        room = copy.deepcopy(entry['_room'])
        app.apply_semester_truth(room, room.get('semesters', []))
        room['_snapshot_replay'] = True
        cities[city]['room_results'].setdefault(prop, []).append(room)
    observed = sorted({entry['_room'].get('scraped_at', '时间未知') for entry in snapshot.values()})
    label = '保存快照 · ' + (observed[0] if len(observed) == 1 else observed[0] + ' 至 ' + observed[-1])
    html = app.build_html(cities, snapshot_label=label)
    (root / 'index.html').write_text(html)
    (root / 'container/public/index.html').write_text(html)
    for city in cities.values():
        for rooms in city['room_results'].values():
            for room in rooms:
                room.pop('_snapshot_replay', None)
    (root / 'data_snapshot.json').write_text(json.dumps(app.build_snapshot(cities), ensure_ascii=False, indent=1))
    print(f'Rendered {len(snapshot)} saved rooms; {sum(len(app.semester_views(r)) for c in cities.values() for rooms in c["room_results"].values() for r in rooms)} semester rows. No network or notifications.')


if __name__ == '__main__':
    main()
