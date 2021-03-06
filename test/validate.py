"""
Validate everything in this repo, such as syntax, structure, etc.
"""
import sys
import os
import glob
import yaml
import jsonschema
import requests
import json
from jsonschema.exceptions import ValidationError

from test.helpers import get_config, wait_for_arangodb

_CONF = get_config()

# JSON schema for vertex and edge collection schemas found in /schema
schema_schema = {
    "type": "object",
    "required": ["name", "type", "schema"],
    "properties": {
        "name": {
            'title': 'Collection name',
            "type": "string",
            "format": r'^[a-z_]+$'
        },
        'type': {
            'type': 'string',
            'enum': ['vertex', 'edge']
        },
        'schema': {'type': 'object'}
    }
}


def validate_json_schemas():
    """Validate the syntax of all the JSON schemas."""
    print('Validating JSON schemas..')
    names = set()  # type: set
    for path in glob.iglob('schemas/**/*.yaml', recursive=True):
        name = os.path.basename(path)
        print(f'  validating {path}..')
        with open(path) as fd:
            data = yaml.safe_load(fd)
        jsonschema.validate(data, schema_schema)
        # Check for any duplicate schema names
        if name in names:
            _fatal('Duplicate schemas for name ' + name)
        else:
            names.add(name)
        # Make sure it can be used as a JSON schema
        # If the schema is invalid, a SchemaError will get raised
        # Otherwise, the schema will work and a ValidationError will get raised (what we want)
        try:
            jsonschema.validate({}, data['schema'])
        except ValidationError:
            pass
        except Exception as err:
            print('=' * 80)
            print('Unable to load schema in ' + path)
            print(str(err))
            exit(1)
        # All schemas must be object types
        if data['schema']['type'] != 'object':
            _fatal('Schemas must be an object. Schema in %s is not an object.' % path)
        required = data['schema'].get('required', [])
        # Edges must require _from and _to while vertices must require _key
        has_edge_fields = ('_from' in required and '_to' in required)
        has_delta_edge_fields = ('from' in required and 'to' in required)
        if data['type'] == 'edge' and data.get('delta') and not has_delta_edge_fields:
            _fatal('Time-travel edge schemas must require "from" and "to" attributes in ' + path)
        elif data['type'] == 'edge' and not data.get('delta') and not has_edge_fields:
            _fatal('Edge schemas must require "_from" and "_to" attributes in ' + path)
        elif data['type'] == 'vertex' and data.get('delta') and 'id' not in required:
            _fatal('Time-travel vertex schemas must require the "id" attribute in ' + path)
        elif data['type'] == 'vertex' and not data.get('delta') and '_key' not in required:
            _fatal('Vertex schemas must require the "_key" attribute in ' + path)
        print(f'✓ {name} is valid.')
    print('..all valid.')


stored_query_schema = {
    'type': 'object',
    'required': ['query', 'name'],
    'properties': {
        'name': {'type': 'string'},
        'params': {'type': 'object'},
        'query_prefix': {'type': 'string'},
        'query': {'type': 'string'}
    }
}


def validate_stored_queries():
    """Validate the structure and syntax of all the queries."""
    print('Validating AQL queries..')
    names = set()  # type: set
    for path in glob.iglob('stored_queries/**/*.yaml', recursive=True):
        print(f'  validating {path}..')
        with open(path) as fd:
            data = yaml.safe_load(fd)
        jsonschema.validate(data, stored_query_schema)
        name = data['name']
        filename = os.path.splitext(os.path.basename(path))[0]
        if name != filename:
            _fatal(f'Name key should match filename: {name} vs {filename}')
        if name in names:
            _fatal(f'Duplicate queries named {name}')
        else:
            names.add(name)
        # Make sure `params` can be used as a JSON schema
        if data.get('params'):
            # Make sure it can be used as a JSON schema
            # If the schema is invalid, a SchemaError will get raised
            # Otherwise, the schema will work and a ValidationError will get raised (what we want)
            try:
                jsonschema.validate({}, data['params'])
            except ValidationError:
                pass
            # Params must be of type 'object'
            if data['params'].get('type') != 'object':
                _fatal("Params schema must have type 'object'")
        query = data.get('query_prefix', '') + ' ' + data['query']
        # Parse the AQL query on arangodb
        url = _CONF['db_url'] + '/_api/query'
        resp = requests.post(url, data=json.dumps({'query': query}), auth=_CONF['db_auth'])
        parsed = resp.json()
        if parsed['error']:
            _fatal(parsed['errorMessage'])
        query_bind_vars = set(parsed['bindVars'])
        params = set(data.get('params', {}).get('properties', {}).keys())
        if params != query_bind_vars:
            _fatal((f"Bind vars are invalid.\n"
                    f"  Extra vars in query: {query_bind_vars - params}.\n"
                    f"  Extra params in schema: {params - query_bind_vars}"))
        print(f'✓ {path} is valid.')
    print('..all valid.')


# JSON schema for arangosearch views found in /views
view_schema = {
    "type": "object",
    "required": ["name", "type"],
    "properties": {
        "name": {
            'title': 'View name',
            "type": "string",
            "format": r'^[a-z_]+$'
        },
        'type': {
            'type': 'string',
            'enum': ['arangosearch']
        }
    }
}


def validate_views():
    """Validate the structure and syntax of arangosearch views"""
    print('Validating views..')
    names = set()  # type: set
    for path in glob.iglob('views/**/*.json', recursive=True):
        print(f'  validating {path}..')
        with open(path) as fd:
            data = json.load(fd)
        jsonschema.validate(data, view_schema)
        name = data['name']
        filename = os.path.splitext(os.path.basename(path))[0]
        if name != filename:
            _fatal(f'Name key should match filename: {name} vs {filename}')
        if name in names:
            _fatal(f'Duplicate queries named {name}')
        else:
            names.add(name)

        print(f'✓ {name} is valid.')
    print('..all valid.')


def _fatal(msg):
    """Fatal error."""
    sys.stderr.write(str(msg) + '\n')
    sys.exit(1)


if __name__ == '__main__':
    wait_for_arangodb()
    validate_json_schemas()
    validate_stored_queries()
    validate_views()
