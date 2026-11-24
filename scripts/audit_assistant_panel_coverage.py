"""Inventory registered and unregistered panel mutation routes without calling them."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import app, _required_module
from assistant_commands import COMMANDS, panel_routes, route_for


def main():
    registered = {
        (spec['method'], route_for(spec).path): operation
        for operation, spec in COMMANDS.items() if spec['method'] != 'ENTRY'
    }
    registered.update({
        ('POST', '/tasks'): 'create_task',
        ('POST', '/daily-reports'): 'create_daily_report',
        ('POST', '/integrations/content-calendar'): 'create_content_draft',
        ('POST', '/api/compensation/contract/{salesperson_id}'): 'save_contract',
    })
    rows = []
    for route in panel_routes(app.routes):
        for method in route.methods & {'POST', 'PATCH', 'PUT', 'DELETE'}:
            rows.append({
                'module': _required_module(route.path), 'method': method,
                'path': route.path, 'assistant_operation': registered.get((method, route.path)),
            })
    print(json.dumps({
        'registry_commands': len(COMMANDS),
        'bulk_entry_commands': sorted(name for name, spec in COMMANDS.items() if spec['method'] == 'ENTRY'),
        'routes': sorted(rows, key=lambda row: (row['module'] or '', row['path'], row['method'])),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
